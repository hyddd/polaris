from src.tools.notes import NoteTool


def test_note_list(tmp_data_dir):
    tool = NoteTool(notes_dir=str(tmp_data_dir / "notes"), archive_dir=str(tmp_data_dir / "notes" / "archive"))
    result = tool._run(action="list")
    assert "PRD v2 讨论" in result


def test_note_read(tmp_data_dir):
    tool = NoteTool(notes_dir=str(tmp_data_dir / "notes"), archive_dir=str(tmp_data_dir / "notes" / "archive"))
    result = tool._run(action="read", filename="prd-v2-discussion.md")
    assert "RBAC" in result


def test_note_create(tmp_data_dir):
    tool = NoteTool(notes_dir=str(tmp_data_dir / "notes"), archive_dir=str(tmp_data_dir / "notes" / "archive"))
    result = tool._run(action="create", title="测试", content="内容", tags=["test"])
    assert "已记录" in result


def test_note_archive(tmp_data_dir):
    tool = NoteTool(notes_dir=str(tmp_data_dir / "notes"), archive_dir=str(tmp_data_dir / "notes" / "archive"))
    tool._run(action="archive", filename="prd-v2-discussion.md")
    assert not (tmp_data_dir / "notes" / "prd-v2-discussion.md").exists()
    assert (tmp_data_dir / "notes" / "archive" / "prd-v2-discussion.md").exists()
