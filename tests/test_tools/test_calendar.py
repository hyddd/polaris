import json
from src.tools.calendar import GoogleCalendarTool


def test_calendar_list(tmp_data_dir):
    tool = GoogleCalendarTool(data_file=str(tmp_data_dir / "calendar.json"), use_mock=True)
    result = tool._run("list 2026-05-03")
    assert "晨会" in result


def test_calendar_create(tmp_data_dir):
    tool = GoogleCalendarTool(data_file=str(tmp_data_dir / "calendar.json"), use_mock=True)
    result = tool._run('create {"date":"2026-05-05","time":"14:00","title":"测试会议"}')
    assert "已添加" in result


def test_calendar_search(tmp_data_dir):
    tool = GoogleCalendarTool(data_file=str(tmp_data_dir / "calendar.json"), use_mock=True)
    assert "产品评审" in tool._run("search 产品评审")


def test_calendar_delete(tmp_data_dir):
    tool = GoogleCalendarTool(data_file=str(tmp_data_dir / "calendar.json"), use_mock=True)
    result = tool._run("delete evt-1")
    assert "删除" in result.lower() or "取消" in result.lower()
