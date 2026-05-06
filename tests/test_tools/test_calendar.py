import pytest
from src.tools.calendar import CalendarTool
from src.domains.calendar import get_calendar_domain, set_calendar_domain
from src.domains.calendar.domain import CalendarDomain
from src.domains.calendar.store import CalendarStore


@pytest.fixture(autouse=True)
def setup_domain(tmp_data_dir):
    """初始化 CalendarDomain 供测试使用。"""
    store = CalendarStore(str(tmp_data_dir / "calendar.json"))
    domain = CalendarDomain(store)
    set_calendar_domain(domain)
    yield
    set_calendar_domain(None)


def test_calendar_list(tmp_data_dir):
    tool = CalendarTool(data_file=str(tmp_data_dir / "calendar.json"))
    result = tool._run(action="list", date="2026-05-03")
    assert "晨会" in result


def test_calendar_create(tmp_data_dir):
    tool = CalendarTool(data_file=str(tmp_data_dir / "calendar.json"))
    result = tool._run(action="create", date="2026-05-05", time="14:00", title="测试会议")
    assert "已添加" in result


def test_calendar_search(tmp_data_dir):
    tool = CalendarTool(data_file=str(tmp_data_dir / "calendar.json"))
    result = tool._run(action="search", keyword="产品评审")
    assert "产品评审" in result


def test_calendar_delete(tmp_data_dir):
    tool = CalendarTool(data_file=str(tmp_data_dir / "calendar.json"))
    result = tool._run(action="delete", event_id="evt-1")
    assert "删除" in result.lower() or "取消" in result.lower()
