"""CalendarDomain 单元测试。"""

import re

import pytest

from src.domains.calendar.store import CalendarStore
from src.domains.calendar.domain import CalendarDomain


@pytest.fixture
def domain(tmp_path):
    store = CalendarStore(str(tmp_path / "calendar.json"))
    return CalendarDomain(store)


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------


def test_create_event(domain):
    event = domain.create_event("2026-05-01", "团队周会", time="10:00", duration=30,
                                attendees=["Alice", "Bob"])
    assert event.title == "团队周会"
    assert event.date == "2026-05-01"
    assert event.time == "10:00"
    assert event.duration == 30
    assert event.attendees == ["Alice", "Bob"]


def test_list_events(domain):
    domain.create_event("2026-05-01", "事件A")
    domain.create_event("2026-05-01", "事件B")
    domain.create_event("2026-05-02", "事件C")
    events = domain.list_events()
    assert len(events) == 3


def test_list_events_by_date(domain):
    domain.create_event("2026-05-01", "事件A")
    domain.create_event("2026-05-02", "事件B")
    domain.create_event("2026-05-01", "事件C")
    events = domain.list_events(date="2026-05-01")
    assert len(events) == 2
    assert all(e.date == "2026-05-01" for e in events)


def test_search_events(domain):
    domain.create_event("2026-05-01", "团队周会")
    domain.create_event("2026-05-02", "产品评审")
    domain.create_event("2026-05-03", "周会总结")
    results = domain.search("周会")
    assert len(results) == 2
    # search 返回 (date, CalendarEvent) 元组
    titles = [r[1].title for r in results]
    assert "团队周会" in titles
    assert "周会总结" in titles


def test_update_event(domain):
    event = domain.create_event("2026-05-01", "原标题", time="09:00")
    updated = domain.update_event(event.id, {"title": "新标题", "time": "14:00"})
    assert updated is not None
    assert updated.title == "新标题"
    assert updated.time == "14:00"
    assert updated.date == "2026-05-01"


def test_update_event_move_date(domain):
    event = domain.create_event("2026-05-01", "移动测试")
    updated = domain.update_event(event.id, {}, date="2026-05-02")
    assert updated is not None
    assert updated.date == "2026-05-02"
    # 原日期已无事件
    assert len(domain.list_events(date="2026-05-01")) == 0
    # 新日期有事件
    events = domain.list_events(date="2026-05-02")
    assert len(events) == 1
    assert events[0].id == event.id


def test_delete_event(domain):
    event = domain.create_event("2026-05-01", "待删除")
    assert domain.delete_event(event.id) is True
    assert domain.get_event(event.id) is None


def test_delete_nonexistent(domain):
    assert domain.delete_event("evt-nonexist") is False


def test_event_id_format(domain):
    event = domain.create_event("2026-05-01", "ID测试")
    assert re.match(r"^evt-[0-9a-f]{8}$", event.id)
