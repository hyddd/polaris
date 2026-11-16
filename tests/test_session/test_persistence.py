"""③ 会话持久化：原子写入、并发写、损坏文件不再被静默丢弃。"""
import json
import logging
import os
import threading

import pytest
from langchain_core.messages import AIMessage, HumanMessage

import src.core.storage.atomic as atomic_mod
import src.session.manager as manager_mod


def _path(sid):
    return manager_mod.SESSIONS_DIR / f"{sid}.json"


def _fresh_manager():
    return manager_mod.SessionManager()


def test_crash_during_write_keeps_previous_file_intact(session_mgr, monkeypatch):
    """写到一半失败（模拟进程被杀 / 磁盘满）：旧文件仍完整可读。

    旧代码 open(path, "w") 先清空再写，中途失败只剩半截文件。
    """
    s = session_mgr.active_session("admin")
    s.memory.add_message(HumanMessage(content="第一版"))
    session_mgr.save_session(s.session_id)

    s.memory.add_message(AIMessage(content="第二版" * 1000))

    def boom(*a, **kw):
        raise OSError("disk full")
    # 只撤销这一个补丁；monkeypatch.undo() 会把 fixture 里的会话目录补丁一起撤掉
    with monkeypatch.context() as m:
        m.setattr(atomic_mod.os, "replace", boom)
        with pytest.raises(OSError):
            session_mgr.save_session(s.session_id)

    data = json.loads(_path(s.session_id).read_text(encoding="utf-8"))
    assert [m["content"] for m in data["messages"]] == ["第一版"]


def test_concurrent_saves_never_expose_broken_json(session_mgr):
    """多线程同时写同一个会话（QQ 线程 + 主线程），读者任何时刻读到的都是合法 JSON。"""
    s = session_mgr.active_session("admin")
    session_mgr.save_session(s.session_id)
    stop = threading.Event()
    bad_reads = []

    def writer(tag):
        for i in range(60):
            s.memory.add_message(HumanMessage(content=f"{tag}-{i}" * 50))
            session_mgr.save_session(s.session_id)

    def touch_loop():
        for _ in range(60):
            session_mgr.switch(s.session_id, "qq:x")   # _touch 也会写盘

    def reader():
        while not stop.is_set():
            try:
                json.loads(_path(s.session_id).read_text(encoding="utf-8"))
            except FileNotFoundError:
                pass
            except json.JSONDecodeError as e:
                bad_reads.append(str(e))

    r = threading.Thread(target=reader)
    r.start()
    ws = [threading.Thread(target=writer, args=(t,)) for t in "abc"] + [threading.Thread(target=touch_loop)]
    for w in ws:
        w.start()
    for w in ws:
        w.join(timeout=30)
    stop.set()
    r.join(timeout=5)

    assert bad_reads == []
    data = json.loads(_path(s.session_id).read_text(encoding="utf-8"))
    assert len(data["messages"]) == 180


def test_corrupt_file_recovered_from_backup(session_mgr, caplog):
    s = session_mgr.active_session("admin")
    s.memory.add_message(HumanMessage(content="v1"))
    session_mgr.save_session(s.session_id)
    s.memory.add_message(HumanMessage(content="v2"))
    session_mgr.save_session(s.session_id)       # .bak 里是 v1
    _path(s.session_id).write_text('{"id": "trunc', encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="polaris.session"):
        mgr = _fresh_manager()

    recovered = mgr.get(s.session_id)
    assert recovered is not None
    assert [m.content for m in recovered.memory.get_messages()] == ["v1"]
    assert "已从备份恢复" in caplog.text
    # 主文件已用恢复内容重写，坏文件保留待查
    assert json.loads(_path(s.session_id).read_text(encoding="utf-8"))["id"] == s.session_id
    assert list(manager_mod.SESSIONS_DIR.glob(f"{s.session_id}.json.corrupt-*"))


def test_corrupt_file_without_backup_is_quarantined_and_logged(session_mgr, caplog):
    """旧代码 except: continue，会话无声无息消失；现在要报错，并把坏文件留着。"""
    s = session_mgr.create(name="会坏的")
    _path(s.session_id).write_text("not json", encoding="utf-8")
    _path(s.session_id).with_suffix(".json.bak").unlink(missing_ok=True)

    with caplog.at_level(logging.ERROR, logger="polaris.session"):
        mgr = _fresh_manager()

    assert mgr.get(s.session_id) is None
    assert "会话文件损坏" in caplog.text
    kept = list(manager_mod.SESSIONS_DIR.glob(f"{s.session_id}.json.corrupt-*"))
    assert kept and kept[0].read_text(encoding="utf-8") == "not json"


def test_switch_only_rewrites_touched_session(session_mgr):
    """_touch 以前调 save() 重写全部会话文件；现在只写被切换的那个。"""
    a = session_mgr.active_session("admin")
    b = session_mgr.create(name="B")
    before = os.stat(_path(a.session_id)).st_mtime_ns
    os.utime(_path(a.session_id), ns=(before - 10**9, before - 10**9))
    before = os.stat(_path(a.session_id)).st_mtime_ns

    session_mgr.switch(b.session_id, "admin")

    assert os.stat(_path(a.session_id)).st_mtime_ns == before


def test_delete_removes_backup_too(session_mgr):
    s = session_mgr.create(name="要删的")
    session_mgr.save_session(s.session_id)   # 产生 .bak
    bak = _path(s.session_id).with_suffix(".json.bak")
    assert bak.exists()
    assert session_mgr.delete(s.session_id)
    assert not _path(s.session_id).exists() and not bak.exists()


def test_record_message_uses_given_session(session_mgr):
    a = session_mgr.active_session("admin")
    b = session_mgr.create(name="B")
    session_mgr.switch(b.session_id, "admin")
    session_mgr.record_message("u", "a", "admin", session_id=a.session_id)
    assert a.metadata["message_count"] == 2
    assert b.metadata.get("message_count", 0) == 0
