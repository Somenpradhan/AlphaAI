"""
utils.py
--------
Pure utility functions: time normalization, urgency detection, plan generation.
No side effects, no I/O — easy to unit-test in isolation.
"""

import re


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

_12H = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.IGNORECASE)
_24H = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_KEYWORDS = {
    "morning": "9:00 AM",
    "noon": "12:00 PM",
    "afternoon": "2:00 PM",
    "evening": "7:00 PM",
    "night": "9:00 PM",
    "midnight": "12:00 AM",
}


def normalize_time(text: str | None) -> str | None:
    """
    Convert any recognizable time expression to canonical 'H:MM AM/PM' form.

    Examples
    --------
    '7pm'     -> '7:00 PM'
    '7 PM'    -> '7:00 PM'
    '7:30pm'  -> '7:30 PM'
    '18:00'   -> '6:00 PM'
    'morning' -> '9:00 AM'
    Returns None when no time is found.
    """
    if not text:
        return None

    text_lower = text.lower().strip()

    # keyword first
    for kw, canonical in _KEYWORDS.items():
        if kw in text_lower:
            return canonical

    m = _12H.search(text)
    if m:
        hour = int(m.group(1))
        mins = m.group(2) or "00"
        period = m.group(3).upper()
        return f"{hour}:{mins} {period}"

    m24 = _24H.search(text)
    if m24:
        hour = int(m24.group(1))
        mins = m24.group(2)
        period = "AM" if hour < 12 else "PM"
        hour_12 = hour % 12
        if hour_12 == 0:
            hour_12 = 12
        return f"{hour_12}:{mins} {period}"

    return None


def assign_time_based_on_urgency(urgency: str | None) -> str:
    """
    Return a default time string based on urgency level.
    high   -> '9:00 AM'
    medium -> '2:00 PM'
    low    -> '5:00 PM'
    """
    u = (urgency or "").lower()
    if u == "high":
        return "9:00 AM"
    elif u == "medium":
        return "2:00 PM"
    return "5:00 PM"


def detect_urgency(text: str) -> str:
    t = text.lower()

    high = (
        "urgent", "asap", "immediately", "right now",
        "deadline", "exam", "submission", "final",
        "interview", "today evening", "before"
    )

    medium = (
        "today", "tomorrow", "soon",
        "meeting", "assignment", "project",
        "this week"
    )

    if any(w in t for w in high):
        return "high"

    if any(w in t for w in medium):
        return "medium"

    return "low"

# ---------------------------------------------------------------------------
# Intent / plan generation
# ---------------------------------------------------------------------------

def generate_plan(prompt: str) -> list[str]:
    """
    Lightweight keyword router.  Returns an ordered list of action tokens.
    The Planner agent uses this to decide which tool to call.
    """
    p = prompt.lower()

    if any(x in p for x in ("plan my day", "daily plan", "what do i have",
                             "show schedule", "show tasks", "schedule today",
                             "today's plan")):
        return ["daily_plan"]

    steps: list[str] = []

    if "note" in p:
        steps.append("save_note")

    if "meeting" in p or "call" in p:
        if "delete" in p or "cancel" in p or "remove" in p:
            steps.append("delete_event")
        elif "edit" in p or "update" in p or "move" in p or "reschedule" in p:
            steps.append("edit_event")
        else:
            steps.append("schedule_meeting")

    if "study" in p:
        steps.append("schedule_study")

    if "task" in p or "remind" in p or "todo" in p:
        if "delete" in p or "remove" in p or "done" in p or "complete" in p:
            steps.append("delete_task")
        elif "edit" in p or "update" in p or "change" in p:
            steps.append("edit_task")
        else:
            steps.append("create_task")

    return steps or ["create_task"]

URGENCY_ORDER = {
    "low": 1,
    "medium": 2,
    "high": 3,
}

def compare_urgency(current: str, incoming: str) -> int:
    """
    Returns:
      1  -> incoming is higher
      0  -> equal
     -1  -> incoming is lower
    """
    a = URGENCY_ORDER.get(current, 1)
    b = URGENCY_ORDER.get(incoming, 1)

    if b > a:
        return 1
    elif b == a:
        return 0
    return -1