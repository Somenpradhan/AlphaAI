"""
db.py
-----
Thin Firestore wrapper.

Schema
------
Collection : users
Document   : {user_id}
Fields     : tasks   -> list[dict]   {id, title, time, urgency, created_at}
             events  -> list[dict]   {id, title, time, created_at}
             notes   -> list[str]

All writes use merge=True so partial updates never destroy sibling fields.
All reads return an empty list/dict when the document is missing.
"""

import os
import logging
import uuid
import socket
import json
from pathlib import Path
from datetime import datetime, timezone

from google.cloud import firestore
from dotenv import load_dotenv

load_dotenv()

import urllib.request

logger = logging.getLogger(__name__)

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "demo-project")

LOCAL_DB_FILE = Path(__file__).parent.parent / "local_db.json"


def _is_emulator_reachable(host_port: str) -> bool:
    try:
        parts = host_port.split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 8080
        # Quick socket check with a 0.5s timeout
        with socket.create_connection((host, port), timeout=0.5):
            pass

        # Verify that host:port is actually a Firestore Emulator.
        # Firestore Emulator responds with JSON containing {"gcloudFirestore": true} on HTTP GET /
        url = f"http://{host}:{port}/"
        req = urllib.request.Request(url, headers={"User-Agent": "Firestore-Checker"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            return "gcloudFirestore" in content
    except Exception:
        return False


emulator_host = os.getenv("FIRESTORE_EMULATOR_HOST")
_use_local_storage = False
_db = None

if os.getenv("USE_LOCAL_DB", "").lower() in ("true", "1"):
    _use_local_storage = True
    logger.info("Using local JSON file storage as requested by USE_LOCAL_DB.")
elif emulator_host:
    if not _is_emulator_reachable(emulator_host):
        _use_local_storage = True
        logger.warning(
            "FIRESTORE_EMULATOR_HOST (%s) is not reachable or not a Firestore Emulator. Falling back to local JSON file storage (%s).",
            emulator_host,
            LOCAL_DB_FILE,
        )
else:
    # No emulator host specified; try Firestore client but fall back to local storage if it fails
    pass

if not _use_local_storage:
    try:
        _db = firestore.Client(project=PROJECT_ID)
    except Exception as exc:
        logger.warning("Firestore init failed (%s); falling back to local JSON file storage.", exc)
        _use_local_storage = True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ref(user_id: str):
    if _db is None:
        raise RuntimeError("Firestore Client is not initialized.")
    return _db.collection("users").document(user_id)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_id() -> str:
    return str(uuid.uuid4())[:8]


# ---------------------------------------------------------------------------
# Local File Database Helpers
# ---------------------------------------------------------------------------

def _load_local_db() -> dict:
    if LOCAL_DB_FILE.exists():
        try:
            with open(LOCAL_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Error reading local DB file: %s", e)
    return {}


def _save_local_db(data: dict) -> None:
    try:
        with open(LOCAL_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error("Error writing to local DB file: %s", e)


def _load_key_local(user_id: str, key: str) -> list:
    data = _load_local_db()
    return data.get(user_id, {}).get(key, [])


def _save_key_local(user_id: str, key: str, value) -> None:
    data = _load_local_db()
    if user_id not in data:
        data[user_id] = {}
    data[user_id][key] = value
    _save_local_db(data)


# ---------------------------------------------------------------------------
# Generic load / save (kept for backward compat with r.py / test scripts)
# ---------------------------------------------------------------------------

def load(user_id: str, key: str) -> list:
    global _use_local_storage
    if _use_local_storage or _db is None:
        return _load_key_local(user_id, key)
    try:
        doc = _ref(user_id).get()
        if doc.exists:
            return doc.to_dict().get(key, [])
        return []
    except Exception as e:
        logger.warning("Firestore load failed (%s); falling back to local storage.", e)
        _use_local_storage = True
        return _load_key_local(user_id, key)


def save(user_id: str, key: str, value) -> None:
    global _use_local_storage
    print("=" * 50)
    print("SAVE CALLED")
    print("User:", user_id)
    print("Key:", key)
    print("Value:", value)

    logger.info("SAVE user=%s key=%s", user_id, key)

    if _use_local_storage or _db is None:
        _save_key_local(user_id, key, value)
        print("[OK] SAVE SUCCESS (Local File Storage)")
        return

    try:
        _ref(user_id).set({key: value}, merge=True)
        print("[OK] SAVE SUCCESS (Firestore)")
    except Exception as e:
        print("[FAILED] FIRESTORE SAVE FAILED, falling back to local file storage")
        logger.warning("Firestore save failed (%s); falling back to local file storage.", e)
        _use_local_storage = True
        _save_key_local(user_id, key, value)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def get_tasks(user_id: str) -> list[dict]:
    return load(user_id, "tasks")


def add_task(user_id: str, title: str, time: str, urgency: str) -> dict:
    task = {
        "id": make_id(),
        "title": title,
        "time": time,
        "urgency": urgency,
        "created_at": _now(),
    }
    tasks = get_tasks(user_id)
    tasks.append(task)
    save(user_id, "tasks", tasks)
    return task


def edit_task(user_id: str, task_id: str, **kwargs) -> dict | None:
    tasks = get_tasks(user_id)
    for t in tasks:
        if t.get("id") == task_id:
            t.update(kwargs)
            save(user_id, "tasks", tasks)
            return t
    return None


def delete_task(user_id: str, task_id: str) -> bool:
    tasks = get_tasks(user_id)
    new_tasks = [t for t in tasks if t.get("id") != task_id]
    if len(new_tasks) == len(tasks):
        return False
    save(user_id, "tasks", new_tasks)
    return True


# ---------------------------------------------------------------------------
# Events (meetings / study sessions)
# ---------------------------------------------------------------------------

def get_events(user_id: str) -> list[dict]:
    return load(user_id, "events")


def add_event(user_id: str, title: str, time: str, urgency: str) -> dict:
    event = {
        "id": make_id(),
        "title": title,
        "time": time,
        "urgency": urgency,
        "created_at": _now(),
    }
    events = get_events(user_id)
    events.append(event)
    save(user_id, "events", events)
    return event


def edit_event(user_id: str, event_id: str, **kwargs) -> dict | None:
    events = get_events(user_id)
    for e in events:
        if e.get("id") == event_id:
            e.update(kwargs)
            save(user_id, "events", events)
            return e
    return None


def delete_event(user_id: str, event_id: str) -> bool:
    events = get_events(user_id)
    new_events = [e for e in events if e.get("id") != event_id]
    if len(new_events) == len(events):
        return False
    save(user_id, "events", new_events)
    return True


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

def get_notes(user_id: str) -> list[str]:
    return load(user_id, "notes")


def add_note(user_id: str, note: str) -> str:
    notes = get_notes(user_id)
    notes.append(note)
    save(user_id, "notes", notes)
    return note


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def get_all_times(user_id: str) -> list[str]:
    """Return every scheduled time (normalized strings) across tasks + events."""
    times: list[str] = []
    for item in get_tasks(user_id) + get_events(user_id):
        t = item.get("time")
        if t:
            times.append(t.strip().upper())
    return times


def get_item_at_time(user_id: str, time: str | None, exclude_id: str | None = None) -> dict | None:
    """
    Return the task/event scheduled at the given time.

    Returns:
        {
            "type": "task" | "event",
            "id": "...",
            "title": "...",
            "time": "...",
            "urgency": "...",
            "created_at": "..."
        }

    Returns None if nothing exists or if time is empty.
    """
    if not time:
        return None

    normalized = time.strip().upper()

    for task in get_tasks(user_id):
        if exclude_id and task.get("id") == exclude_id:
            continue
        if task.get("time", "").strip().upper() == normalized:
            return {
                "type": "task",
                **task,
            }

    for event in get_events(user_id):
        if exclude_id and event.get("id") == exclude_id:
            continue
        if event.get("time", "").strip().upper() == normalized:
            return {
                "type": "event",
                **event,
            }

    return None


def check_conflict(user_id: str, time: str | None, exclude_id: str | None = None) -> dict | None:
    """
    Return the conflicting task/event if one exists.
    Otherwise return None.
    """
    return get_item_at_time(user_id, time, exclude_id=exclude_id)