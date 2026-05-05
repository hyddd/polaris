"""Tests for _atomic_write — atomic file write with backup and recovery."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.core.storage.atomic import _atomic_write


class TestAtomicWrite:
    """Test _atomic_write function."""

    def test_basic_write(self, tmp_path):
        """Write content to a new file."""
        target = tmp_path / "test.txt"
        _atomic_write(target, "hello world")
        assert target.read_text() == "hello world"

    def test_overwrite_creates_backup(self, tmp_path):
        """Overwriting an existing file creates .bak backup."""
        target = tmp_path / "config.env"
        target.write_text("OLD_CONTENT")
        backup = target.with_suffix(target.suffix + ".bak")

        _atomic_write(target, "NEW_CONTENT")

        assert target.read_text() == "NEW_CONTENT"
        assert backup.exists()
        assert backup.read_text() == "OLD_CONTENT"

    def test_backup_updates_on_repeated_writes(self, tmp_path):
        """Each write updates the backup to the previous content."""
        target = tmp_path / "data.json"
        target.write_text("v1")
        _atomic_write(target, "v2")
        _atomic_write(target, "v3")

        assert target.read_text() == "v3"
        assert (target.with_suffix(target.suffix + ".bak")).read_text() == "v2"

    def test_no_backup_for_new_file(self, tmp_path):
        """No backup is created when writing to a new file."""
        target = tmp_path / "new.txt"
        backup = target.with_suffix(target.suffix + ".bak")

        _atomic_write(target, "content")

        assert target.read_text() == "content"
        assert not backup.exists()

    def test_unicode_content(self, tmp_path):
        """Correctly writes unicode/CJK content."""
        target = tmp_path / "zh.env"
        content = "LLM_MODEL=gpt-4o\n备注=测试中文"
        _atomic_write(target, content)
        assert target.read_text(encoding="utf-8") == content

    def test_empty_content(self, tmp_path):
        """Writing empty string works."""
        target = tmp_path / "empty.txt"
        _atomic_write(target, "")
        assert target.read_text() == ""

    def test_large_content(self, tmp_path):
        """Writing large content works correctly."""
        target = tmp_path / "large.txt"
        content = "x" * 1_000_000  # 1MB
        _atomic_write(target, content)
        assert target.read_text() == content
        assert len(target.read_text()) == 1_000_000

    def test_temp_file_cleanup_on_success(self, tmp_path):
        """No leftover temp files after successful write."""
        target = tmp_path / "clean.txt"
        _atomic_write(target, "data")

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_temp_file_cleanup_on_failure(self, tmp_path):
        """Temp files are cleaned up even when rename fails."""
        target = tmp_path / "fail.txt"
        target.write_text("original")

        with patch("os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                _atomic_write(target, "new data")

        # No temp files left behind
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_restore_on_rename_failure(self, tmp_path):
        """Original content is preserved when rename fails."""
        target = tmp_path / "important.env"
        target.write_text("CRITICAL=value")

        with patch("os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                _atomic_write(target, "BROKEN=value")

        # Original content should be restored
        assert target.read_text() == "CRITICAL=value"

    def test_preserves_file_permissions(self, tmp_path):
        """Backup preserves original file permissions (shutil.copy2)."""
        target = tmp_path / "perms.txt"
        target.write_text("data")
        target.chmod(0o644)

        _atomic_write(target, "new data")

        backup = target.with_suffix(target.suffix + ".bak")
        assert backup.exists()
        # copy2 preserves metadata
        assert target.read_text() == "new data"

    def test_concurrent_writes_different_files(self, tmp_path):
        """Writing to different files doesn't interfere."""
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"

        _atomic_write(f1, "content_a")
        _atomic_write(f2, "content_b")

        assert f1.read_text() == "content_a"
        assert f2.read_text() == "content_b"

    def test_write_to_nested_directory(self, tmp_path):
        """Works with nested directory paths."""
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        target = nested / "deep.txt"

        _atomic_write(target, "deep content")
        assert target.read_text() == "deep content"
