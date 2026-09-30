"""Data model, persistence and small helpers for Job Transition Coach.

Nothing in this module imports Streamlit, so it can be unit-tested directly.

The data is a single JSON-serialisable dict:

    {
        "settings": {"target_date": "2026-12-31", "goal": "..."},
        "tasks": [{"id": "...", "text": "...", "done": false}, ...],
        "courses": [...],
        "portfolio": [...],
        "visa_finance": [...],
        "applications": [
            {"id": "...", "company": "...", "role": "...", "link": "...",
             "date_applied": "2026-09-30", "status": "Applied", "notes": "..."},
        ],
        "notes": "free text",
    }
"""

from __future__ import annotations

import csv
import io
import json
import os
import uuid
from datetime import date, timedelta
from typing import Any

CHECKLIST_CATEGORIES: dict[str, str] = {
    "tasks": "Tasks",
    "courses": "Courses",
    "portfolio": "Portfolio",
    "visa_finance": "Visa & Finance",
}

APPLICATION_STATUSES: list[str] = [
    "Wishlist",
    "Applied",
    "Interview",
    "Offer",
    "Rejected",
    "Withdrawn",
]

APPLICATION_FIELDS: list[str] = [
    "company",
    "role",
    "link",
    "date_applied",
    "status",
    "notes",
]

DEFAULT_TARGET_DAYS = 90


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def default_data(today: date | None = None) -> dict[str, Any]:
    """Return a fresh, empty data structure."""
    today = today or date.today()
    return {
        "settings": {
            "target_date": (today + timedelta(days=DEFAULT_TARGET_DAYS)).isoformat(),
            "goal": "",
        },
        **{category: [] for category in CHECKLIST_CATEGORIES},
        "applications": [],
        "notes": "",
    }


def _normalize_checklist_item(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        item = {"text": item}
    if not isinstance(item, dict):
        return None
    text = str(item.get("text", "")).strip()
    if not text:
        return None
    return {
        "id": str(item.get("id") or new_id()),
        "text": text,
        "done": bool(item.get("done", False)),
    }


def _normalize_application(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    # Files from the original single-checklist version stored applications
    # as {"text", "done"}; keep the text as the company name.
    if "company" not in item and "text" in item:
        item = {"company": item["text"], "status": "Applied"}
    app = {field: str(item.get(field) or "").strip() for field in APPLICATION_FIELDS}
    if not (app["company"] or app["role"]):
        return None
    if app["status"] not in APPLICATION_STATUSES:
        app["status"] = "Applied"
    app["date_applied"] = _normalize_date(app["date_applied"]) or ""
    app["id"] = str(item.get("id") or new_id())
    return app


def _normalize_date(value: Any) -> str | None:
    # datetime and pandas Timestamp are date subclasses; NaT becomes "NaT"
    # and fails to parse below, which is what we want.
    if isinstance(value, date):
        value = value.isoformat()
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


def normalize(data: Any, today: date | None = None) -> dict[str, Any]:
    """Coerce loaded or imported data into the current shape.

    Missing keys get defaults, malformed items are dropped, and files written
    by older versions are upgraded.
    """
    result = default_data(today)
    if not isinstance(data, dict):
        return result

    settings = data.get("settings")
    if isinstance(settings, dict):
        target = _normalize_date(settings.get("target_date"))
        if target:
            result["settings"]["target_date"] = target
        result["settings"]["goal"] = str(settings.get("goal") or "")

    for category in CHECKLIST_CATEGORIES:
        items = data.get(category)
        if isinstance(items, list):
            result[category] = [n for n in (_normalize_checklist_item(i) for i in items) if n]

    apps = data.get("applications")
    if isinstance(apps, list):
        result["applications"] = [n for n in (_normalize_application(a) for a in apps) if n]

    if isinstance(data.get("notes"), str):
        result["notes"] = data["notes"]
    return result


def load_data(path: str) -> dict[str, Any]:
    """Load data from ``path``, or return defaults if it is missing or corrupt."""
    if not os.path.exists(path):
        return default_data()
    try:
        with open(path, encoding="utf-8") as f:
            return normalize(json.load(f))
    except (OSError, ValueError):
        return default_data()


def save_data(data: dict[str, Any], path: str) -> None:
    """Write ``data`` to ``path`` atomically, so a crash never leaves half a file."""
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(to_json(data))
    os.replace(tmp_path, path)


def to_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def from_json(text: str | bytes) -> dict[str, Any]:
    """Parse an exported file. Raises ValueError if it is not valid JSON."""
    return normalize(json.loads(text))


def applications_to_csv(applications: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=APPLICATION_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(applications)
    return buffer.getvalue()


def days_left(target: date, today: date | None = None) -> int:
    """Days from ``today`` until ``target``, clamped at zero."""
    today = today or date.today()
    return max((target - today).days, 0)


def checklist_progress(items: list[dict[str, Any]]) -> tuple[int, int]:
    """Return ``(done, total)`` for a checklist."""
    return sum(1 for i in items if i.get("done")), len(items)


def status_counts(applications: list[dict[str, Any]]) -> dict[str, int]:
    """Count applications per status, in pipeline order, including zeros."""
    counts = dict.fromkeys(APPLICATION_STATUSES, 0)
    for app in applications:
        counts[app.get("status", "Applied")] = counts.get(app.get("status", "Applied"), 0) + 1
    return counts
