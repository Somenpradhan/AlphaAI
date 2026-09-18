"""
tools.py
--------
All deterministic tool functions called by the Planner agent.

Every tool:
  1. Performs its operation via db.py
  2. Writes the result to tool_context.state["last_result"]
  3. Returns the same dict (so ADK includes it in the tool-use turn)

The state write is what allows the Formatter agent (next in the
SequentialAgent chain) to read the result without parsing conversation
history.

No LLM calls live inside these functions — they are pure Python.
"""

from google.adk.tools.tool_context import ToolContext

from .db import (
    add_task, edit_task as db_edit_task, delete_task as db_delete_task,
    get_tasks,
    add_event, edit_event as db_edit_event, delete_event as db_delete_event,
    get_events,
    add_note, get_notes,
    check_conflict,
)
from .utils import (
    normalize_time,
    detect_urgency,
    assign_time_based_on_urgency,
)

USER_ID = "default_user"


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _write(tool_context: ToolContext, result: dict) -> dict:
    """Write result to state and return it."""
    tool_context.state["last_result"] = result
    return result


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def tool_create_task(
    tool_context: ToolContext,
    title: str,
    time: str | None = None,
    urgency: str | None = None,
) -> dict:
    """
    Create a new task and persist it to Firestore.

    Parameters
    ----------
    title   : short description of the task
    time    : optional time string (any format); normalized internally
    urgency : 'high' | 'medium' | 'low' — inferred from title if omitted
    """
    resolved_urgency = urgency or detect_urgency(title)
    nt = normalize_time(time) if time else None
    resolved_time = nt or assign_time_based_on_urgency(resolved_urgency)

    conflict = check_conflict(USER_ID, resolved_time)

    if conflict:
        return _write(
            tool_context,
            {
                "status": "conflict",
                "conflict": conflict,
                "message": f"{conflict['title']} already exists at {resolved_time}.",
            },
        )

    task = add_task(USER_ID, title, resolved_time, resolved_urgency)
    return _write(tool_context, {
        "status": "success",
        "action": "task_created",
        "task": task,
    })


def tool_edit_task(
    tool_context: ToolContext,
    task_id: str,
    title: str | None = None,
    time: str | None = None,
    urgency: str | None = None,
) -> dict:
    """Edit an existing task by its ID."""
    updates: dict = {}
    if title:
        updates["title"] = title
    if urgency:
        updates["urgency"] = urgency
    if time:
        nt = normalize_time(time)
        target_time = nt or time
        if target_time and check_conflict(USER_ID, target_time, exclude_id=task_id):
            return _write(tool_context, {
                "status": "conflict",
                "conflicting_time": target_time,
                "message": f"Something is already scheduled at {target_time}.",
            })
        updates["time"] = target_time

    updated = db_edit_task(USER_ID, task_id, **updates)
    if updated is None:
        return _write(tool_context, {
            "status": "error",
            "message": f"No task found with ID {task_id}.",
        })
    return _write(tool_context, {
        "status": "success",
        "action": "task_updated",
        "task": updated,
    })


def tool_delete_task(
    tool_context: ToolContext,
    task_id: str,
) -> dict:
    """Delete a task by its ID."""
    ok = db_delete_task(USER_ID, task_id)
    if not ok:
        return _write(tool_context, {
            "status": "error",
            "message": f"No task found with ID {task_id}.",
        })
    return _write(tool_context, {
        "status": "success",
        "action": "task_deleted",
        "task_id": task_id,
    })


# ---------------------------------------------------------------------------
# Events (meetings / study sessions)
# ---------------------------------------------------------------------------

def tool_schedule_event(
    tool_context: ToolContext,
    title: str,
    time: str | None = None,
    event_type: str = "meeting",
    urgency: str | None = None,

) -> dict:
    """
    Schedule a meeting or study session.

    Parameters
    ----------
    title      : event description
    time       : time string (any format); defaults to '10:00 AM' if omitted
    event_type : 'meeting' | 'study'
    """
    resolved_time = (normalize_time(time) if time else None) or "10:00 AM"
    resolved_urgency = urgency or detect_urgency(title)
    conflict = check_conflict(USER_ID, resolved_time)

    if conflict:
        return _write(
            tool_context,
            {
                "status": "conflict",
                "conflict": conflict,
                "message": f"{conflict['title']} already exists at {resolved_time}.",
            },
        )
    

    event = add_event(
        USER_ID,
        title,
        resolved_time,
        resolved_urgency,
    )
    return _write(tool_context, {
        "status": "success",
        "action": f"{event_type}_scheduled",
        "event": event,
    })


def tool_edit_event(
    tool_context: ToolContext,
    event_id: str,
    title: str | None = None,
    time: str | None = None,
    urgency: str | None = None,
) -> dict:
    """Edit an existing event (meeting / study session) by its ID."""
    updates: dict = {}
    if title:
        updates["title"] = title
    if time:
        nt = normalize_time(time)
        target_time = nt or time
        if target_time and check_conflict(USER_ID, target_time, exclude_id=event_id):
            return _write(tool_context, {
                "status": "conflict",
                "conflicting_time": target_time,
                "message": f"Something is already scheduled at {target_time}.",
            })
        updates["time"] = target_time

    updated = db_edit_event(USER_ID, event_id, **updates)
    if updated is None:
        return _write(tool_context, {
            "status": "error",
            "message": f"No event found with ID {event_id}.",
        })
    return _write(tool_context, {
        "status": "success",
        "action": "event_updated",
        "event": updated,
    })


def tool_delete_event(
    tool_context: ToolContext,
    event_id: str,
) -> dict:
    """Delete an event by its ID."""
    ok = db_delete_event(USER_ID, event_id)
    if not ok:
        return _write(tool_context, {
            "status": "error",
            "message": f"No event found with ID {event_id}.",
        })
    return _write(tool_context, {
        "status": "success",
        "action": "event_deleted",
        "event_id": event_id,
    })


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

def tool_save_note(
    tool_context: ToolContext,
    note: str,
) -> dict:
    """Save a free-form note."""
    saved = add_note(USER_ID, note)
    return _write(tool_context, {
        "status": "success",
        "action": "note_saved",
        "note": saved,
    })


# ---------------------------------------------------------------------------
# Daily plan
# ---------------------------------------------------------------------------

def tool_daily_plan(
    tool_context: ToolContext,
) -> dict:
    """Return all tasks, events, and notes sorted by time."""
    tasks  = sorted(get_tasks(USER_ID),  key=lambda x: x.get("time", ""))
    events = sorted(get_events(USER_ID), key=lambda x: x.get("time", ""))
    notes  = get_notes(USER_ID)

    return _write(tool_context, {
        "status": "success",
        "action": "daily_plan",
        "tasks":  tasks,
        "events": events,
        "notes":  notes,
    })


# ---------------------------------------------------------------------------
# Public list (imported by agent.py)
# ---------------------------------------------------------------------------

ALL_TOOLS = [
    tool_create_task,
    tool_edit_task,
    tool_delete_task,
    tool_schedule_event,
    tool_edit_event,
    tool_delete_event,
    tool_save_note,
    tool_daily_plan,
]