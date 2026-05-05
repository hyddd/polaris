"""Atomic file write with backup."""
import os
import tempfile
from pathlib import Path
import shutil


def _atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Atomic file write with backup.

    Strategy:
      1. Write new content to a temp file in the same directory.
      2. If original exists, create .bak backup.
      3. os.replace() temp -> original (atomic on POSIX).
      4. On any failure, attempt to restore from backup.

    Raises the original exception after restore attempt.
    """
    path = Path(path)
    dir_fd = path.parent
    backup = path.with_suffix(path.suffix + ".bak")
    tmp_fd = None
    tmp_path = None

    try:
        # Step 1: write to temp file in same directory (same filesystem for rename)
        tmp_fd = tempfile.NamedTemporaryFile(
            mode="w", encoding=encoding, dir=dir_fd,
            suffix=".tmp", delete=False,
        )
        tmp_path = Path(tmp_fd.name)
        tmp_fd.write(content)
        tmp_fd.flush()
        os.fsync(tmp_fd.fileno())  # ensure data hits disk
        tmp_fd.close()
        tmp_fd = None

        # Step 2: backup existing file
        if path.exists():
            shutil.copy2(path, backup)

        # Step 3: atomic rename
        os.replace(str(tmp_path), str(path))
        tmp_path = None  # rename succeeded, don't clean up

    except Exception:
        # Attempt restore from backup if original was overwritten or corrupted
        if backup.exists() and (not path.exists() or path.read_text(encoding=encoding) != content):
            try:
                shutil.copy2(backup, path)
            except Exception:
                pass  # best-effort restore
        raise
    finally:
        # Clean up temp file if rename didn't happen
        if tmp_fd is not None:
            tmp_fd.close()
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
