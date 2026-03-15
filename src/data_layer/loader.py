import json
import re
import yaml
from pathlib import Path
from datetime import date


def load_json(path: Path) -> dict | list:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_calendar_events(path: Path, target_date: str | None = None) -> list[dict]:
    data = load_json(path)
    if not isinstance(data, list):
        return []
    if target_date:
        return [ev for day in data if day.get("date") == target_date for ev in day.get("events", [])]
    return [ev for day in data for ev in day.get("events", [])]


def save_calendar_event(path: Path, date_str: str, event: dict) -> None:
    data = load_json(path)
    if not isinstance(data, list):
        data = []
    for day in data:
        if day.get("date") == date_str:
            day.setdefault("events", []).append(event)
            save_json(path, data)
            return
    data.append({"date": date_str, "events": [event]})
    save_json(path, data)


def load_todos(path: Path) -> list[dict]:
    data = load_json(path)
    return data if isinstance(data, list) else []


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
    frontmatter = yaml.dump(metadata, allow_unicode=True, default_flow_style=False).strip()
    return f"---\n{frontmatter}\n---\n\n{body}\n"


def load_notes(notes_dir: Path) -> list[dict]:
    results = []
    if not notes_dir.exists():
        return results
    for md_file in notes_dir.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        meta, body = parse_note_frontmatter(content)
        results.append({"path": str(md_file), "filename": md_file.name, "metadata": meta, "content": body})
    return results


def save_note(notes_dir: Path, title: str, body: str, tags: list[str] | None = None) -> Path:
    notes_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w\s-]", "", title).strip().lower().replace(" ", "-")
    filename = f"{slug}.md"
    filepath = notes_dir / filename
    metadata = {"title": title, "tags": tags or [], "date": date.today().isoformat()}
    content = format_note_file(metadata, body)
    filepath.write_text(content, encoding="utf-8")
    return filepath


def archive_note(filepath: Path, archive_dir: Path) -> bool:
    if not filepath.exists():
        return False
    archive_dir.mkdir(parents=True, exist_ok=True)
    filepath.rename(archive_dir / filepath.name)
    return True
