from langchain_core.messages import HumanMessage, AIMessage
from src.memory.store import MemoryManager


def test_memory_add_and_retrieve():
    mm = MemoryManager()
    mm.add_message(HumanMessage(content="今天有什么安排"))
    mm.add_message(AIMessage(content="你今天有3个会议"))
    history = mm.get_history()
    assert len(history) == 2
    assert history[0].content == "今天有什么安排"


def test_memory_no_window_limit():
    mm = MemoryManager()
    for i in range(20):
        mm.add_message(HumanMessage(content=f"msg{i}"))
    history = mm.get_history()
    assert len(history) == 20
    assert history[0].content == "msg0"
    assert history[-1].content == "msg19"


def test_memory_load_profile(tmp_data_dir):
    mm = MemoryManager(profile_path=str(tmp_data_dir / "user_profile.json"))
    profile = mm.get_profile()
    assert profile["name"] == "TestUser"


def test_memory_update_profile(tmp_data_dir):
    mm = MemoryManager(profile_path=str(tmp_data_dir / "user_profile.json"))
    mm.update_profile({"preferred_working_hours": "10:00-19:00"})
    profile = mm.get_profile()
    assert profile["preferred_working_hours"] == "10:00-19:00"
