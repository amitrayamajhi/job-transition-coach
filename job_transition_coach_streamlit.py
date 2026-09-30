"""
Simple Streamlit app to help plan a job transition.

This app tracks tasks, courses, portfolio items, job applications,
visa/finance preparations, and freeform notes. It also displays a
countdown to a fixed target date (August 30, 2025).

Data is persisted in a local JSON file (`job_coach_data.json`) in the
same directory as the script. When first run, the file is created with
empty lists for each category.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List

import streamlit as st


# File used for data persistence. It lives next to this script.
DATA_FILE = os.path.join(os.path.dirname(__file__), "job_coach_data.json")


def _default_data() -> Dict[str, List[Dict[str, Any]]]:
    """Return a fresh data structure with empty lists for all categories."""
    return {
        "tasks": [],
        "courses": [],
        "portfolio": [],
        "applications": [],
        "visa_finance": [],
        "notes": "",
    }


def load_data() -> Dict[str, Any]:
    """Load data from DATA_FILE or return default data if file is missing or corrupt."""
    if not os.path.exists(DATA_FILE):
        return _default_data()
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Ensure all keys exist
        default = _default_data()
        for key in default:
            data.setdefault(key, default[key])
        return data
    except Exception:
        return _default_data()


def save_data(data: Dict[str, Any]) -> None:
    """Persist data to DATA_FILE as JSON."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def days_left(target_date: datetime) -> int:
    """Compute days remaining until target_date. Negative values are clamped to zero."""
    today = datetime.now()
    delta = target_date - today
    return max(delta.days, 0)


def render_checklist(category: str, data: Dict[str, Any]) -> None:
    """Render a checklist for a given category (e.g. 'tasks', 'courses', etc.).

    Allows adding new items and marking existing ones as complete.
    Items are stored as dicts with 'text' and 'done' keys.
    """
    items: List[Dict[str, Any]] = data.get(category, [])
    st.subheader(f"Manage {category.replace('_', ' ').title()}")
    # Input for new item
    # A form with clear_on_submit empties the box after adding, so the same
    # text is not re-added on every rerun.
    with st.form(key=f"form_{category}", clear_on_submit=True):
        new_item = st.text_input(f"Add a new {category[:-1]}:")
        submitted = st.form_submit_button("Add")
    if submitted and new_item.strip():
        items.append({"text": new_item.strip(), "done": False})
        data[category] = items
        save_data(data)
        st.rerun()

    # Display items with checkboxes
    for i, item in enumerate(items):
        col1, col2 = st.columns([0.8, 0.2])
        with col1:
            checked = st.checkbox(item["text"], value=item["done"], key=f"chk_{category}_{i}")
        with col2:
            delete = st.button("Remove", key=f"del_{category}_{i}")
        # Update state based on user interactions
        if checked != item["done"]:
            item["done"] = checked
            save_data(data)
        if delete:
            items.pop(i)
            data[category] = items
            save_data(data)
            st.rerun()


def main() -> None:
    """Main entry point of the Streamlit app."""
    st.set_page_config(page_title="Job Transition Coach", layout="wide")
    target = datetime(2025, 8, 30)
    remaining = days_left(target)
    st.title("Job Transition Coach")
    st.write(
        f"\n**Days left until August 30, 2025:** `{remaining}` day{'s' if remaining != 1 else ''}."
    )

    data = load_data()

    # Tabs for categories
    tabs = st.tabs([
        "Dashboard",
        "Tasks",
        "Courses",
        "Portfolio",
        "Applications",
        "Visa & Finance",
        "Notes",
    ])

    # Dashboard: show summary counts and quick actions
    with tabs[0]:
        st.subheader("Overview")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Tasks", sum(not item.get("done") for item in data.get("tasks", [])))
        col2.metric(
            "Courses", sum(not item.get("done") for item in data.get("courses", []))
        )
        col3.metric(
            "Portfolio", len(data.get("portfolio", []))
        )
        col4.metric(
            "Applications", len(data.get("applications", []))
        )
        st.write("\nUse the tabs above to manage each section.")

    # Tasks
    with tabs[1]:
        render_checklist("tasks", data)

    # Courses
    with tabs[2]:
        render_checklist("courses", data)

    # Portfolio
    with tabs[3]:
        render_checklist("portfolio", data)

    # Applications
    with tabs[4]:
        render_checklist("applications", data)

    # Visa & Finance
    with tabs[5]:
        render_checklist("visa_finance", data)

    # Notes
    with tabs[6]:
        st.subheader("Notes")
        notes = st.text_area("Enter notes here:", value=data.get("notes", ""))
        if notes != data.get("notes", ""):
            data["notes"] = notes
            save_data(data)


if __name__ == "__main__":
    main()