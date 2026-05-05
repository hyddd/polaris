"""Notes domain utilities — frontmatter parsing and formatting."""

import re
import yaml
from datetime import date
from pathlib import Path


def parse_note_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown note. Returns (metadata, body)."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if match:
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        return meta, match.group(2).strip()
    return {}, content.strip()


def format_note_file(metadata: dict, body: str) -> str:
    """Format metadata and body into a markdown file with YAML frontmatter."""
    frontmatter = yaml.dump(metadata, allow_unicode=True, default_flow_style=False).strip()
    return f"---\n{frontmatter}\n---\n\n{body}\n"


def load_notes(notes_dir: Path) -> list[dict]:
    """Load all notes from a directory."""
    results = []
    if not notes_dir.exists():
        return results
    for md_file in notes_dir.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        meta, body = parse_note_frontmatter(content)
        results.append({"path": str(md_file), "filename": md_file.name, "metadata": meta, "content": body})
    return results


def save_note(notes_dir: Path, title: str, body: str, tags: list[str] | None = None) -> Path:
    """Save a note to the notes directory."""
    notes_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w\s-]", "", title).strip().lower().replace(" ", "-")
    filename = f"{slug}.md"
    filepath = notes_dir / filename
    metadata = {"title": title, "tags": tags or [], "date": date.today().isoformat()}
    content = format_note_file(metadata, body)
    filepath.write_text(content, encoding="utf-8")
    return filepath


def archive_note(filepath: Path, archive_dir: Path) -> bool:
    """Archive a note to the archive directory."""
    if not filepath.exists():
        return False
    archive_dir.mkdir(parents=True, exist_ok=True)
    filepath.rename(archive_dir / filepath.name)
    return True
