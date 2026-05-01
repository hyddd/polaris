# Session Storage Refactor Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor session storage from single `sessions.json` to individual files per session in `data/sessions/` directory.

**Architecture:** Each session stored as `data/sessions/{session_id}.json`. Active session ID stored in `data/sessions/active.txt`. Migrate old `sessions.json` on first load.

**Tech Stack:** Python pathlib, json

---

## File Structure

```
data/sessions/
├── active.txt              # Active session ID
├── sess_abc12345.json      # Session 1
├── sess_def67890.json      # Session 2
└── ...
```

---

### Task 1: Refactor SessionManager

**Files:**
- Modify: `src/session/manager.py`

- [ ] **Step 1: Update storage paths**

Replace `PERSIST_FILE` with directory-based storage:

```python
class SessionManager:
    SESSIONS_DIR = DATA_DIR / "sessions"
    ACTIVE_FILE = SESSIONS_DIR / "active.txt"
```

- [ ] **Step 2: Refactor save() method**

```python
def save(self):
    self.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    # Save each session individually
    for session in self._sessions.values():
        path = self.SESSIONS_DIR / f"{session.session_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)
    # Save active session ID
    if self._active_id:
        self.ACTIVE_FILE.write_text(self._active_id, encoding="utf-8")
```

- [ ] **Step 3: Refactor _load() method**

```python
def _load(self):
    if not self.SESSIONS_DIR.exists():
        # Migrate from old format or create default
        old_file = DATA_DIR / "sessions.json"
        if old_file.exists():
            self._migrate_from_old(old_file)
        else:
            self.create(name="默认", source_channel="system")
        return

    # Load active session ID
    if self.ACTIVE_FILE.exists():
        self._active_id = self.ACTIVE_FILE.read_text(encoding="utf-8").strip()

    # Load all session files
    for path in self.SESSIONS_DIR.glob("sess_*.json"):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            session = Session.from_dict(data)
            self._sessions[session.session_id] = session
        except Exception:
            continue

    # Validate active session exists
    if self._active_id not in self._sessions:
        self._active_id = next(iter(self._sessions)) if self._sessions else None

    # Ensure at least one session
    if not self._sessions:
        self.create(name="默认", source_channel="system")
```

- [ ] **Step 4: Add migration method**

```python
def _migrate_from_old(self, old_file: Path):
    """Migrate from single sessions.json to individual files."""
    try:
        with open(old_file, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        self.create(name="默认", source_channel="system")
        return

    self.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    for sdata in data.get("sessions", []):
        session = Session.from_dict(sdata)
        self._sessions[session.session_id] = session
        path = self.SESSIONS_DIR / f"{session.session_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sdata, f, ensure_ascii=False, indent=2)

    active = data.get("active_session")
    if active and active in self._sessions:
        self._active_id = active
    elif self._sessions:
        self._active_id = next(iter(self._sessions))

    if self._active_id:
        self.ACTIVE_FILE.write_text(self._active_id, encoding="utf-8")

    # Rename old file as backup
    old_file.rename(old_file.with_suffix(".json.bak"))
```

- [ ] **Step 5: Update delete() to remove file**

```python
def delete(self, session_id: str) -> bool:
    if session_id not in self._sessions:
        return False
    if len(self._sessions) <= 1:
        return False
    del self._sessions[session_id]
    # Delete session file
    path = self.SESSIONS_DIR / f"{session_id}.json"
    path.unlink(missing_ok=True)
    if self._active_id == session_id:
        self._active_id = next(iter(self._sessions))
    self.save()
    return True
```

- [ ] **Step 6: Run tests**

```bash
./venv/bin/python -m pytest tests/ -q
```

- [ ] **Step 7: Commit**

```bash
git add src/session/manager.py
git commit -m "refactor: session 存储改为独立文件 — data/sessions/{id}.json"
```
