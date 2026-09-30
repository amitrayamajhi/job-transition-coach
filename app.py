"""Job Transition Coach: a Streamlit app for planning a career move.

Run locally with:

    streamlit run app.py

Data is saved to ``job_coach_data.json`` next to this file (override with the
``JOB_COACH_DATA_FILE`` environment variable). Set ``JOB_COACH_DEMO=1`` to keep
data only in the browser session instead, which is what a public deployment
should use so visitors never see each other's data.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from job_coach import storage

DATA_FILE = os.environ.get(
    "JOB_COACH_DATA_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "job_coach_data.json"),
)
DEMO_MODE = os.environ.get("JOB_COACH_DEMO", "").lower() in {"1", "true", "yes"}

APPS_BASE_KEY = "apps_base"
APPS_EDITOR_KEY = "apps_editor"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def get_data() -> dict[str, Any]:
    """Return this session's data, loading it from disk on first use."""
    if "data" not in st.session_state:
        st.session_state.data = (
            storage.default_data() if DEMO_MODE else storage.load_data(DATA_FILE)
        )
    return st.session_state.data


def persist() -> None:
    """Save the session's data to disk, unless running in demo mode."""
    if not DEMO_MODE:
        storage.save_data(st.session_state.data, DATA_FILE)


def replace_data(new_data: dict[str, Any]) -> None:
    """Swap in a whole new dataset (import or reset) and redraw."""
    st.session_state.data = new_data
    # The applications editor keeps its own edit state; drop it so it
    # starts again from the new data.
    st.session_state.pop(APPS_BASE_KEY, None)
    st.session_state.pop(APPS_EDITOR_KEY, None)
    persist()
    st.rerun()


# ---------------------------------------------------------------------------
# Sidebar: settings and data
# ---------------------------------------------------------------------------


def render_sidebar(data: dict[str, Any]) -> None:
    settings = data["settings"]
    with st.sidebar:
        st.header("Your plan")
        goal = st.text_input(
            "Goal",
            value=settings["goal"],
            placeholder="e.g. Land a data analyst role in Dubai",
        )
        target = st.date_input("Target date", value=date.fromisoformat(settings["target_date"]))
        if goal != settings["goal"] or target.isoformat() != settings["target_date"]:
            settings["goal"] = goal
            settings["target_date"] = target.isoformat()
            persist()

        st.divider()
        st.header("Your data")
        if DEMO_MODE:
            st.info("Demo mode: your data lives only in this browser tab. Export it to keep it.")
        st.download_button(
            "Export everything (JSON)",
            data=storage.to_json(data),
            file_name="job_coach_data.json",
            mime="application/json",
            width="stretch",
        )
        st.download_button(
            "Export applications (CSV)",
            data=storage.applications_to_csv(data["applications"]),
            file_name="applications.csv",
            mime="text/csv",
            width="stretch",
        )

        uploaded = st.file_uploader("Import a JSON export", type="json")
        if uploaded is not None and st.button("Replace my data with this file", width="stretch"):
            try:
                replace_data(storage.from_json(uploaded.getvalue()))
            except ValueError:
                st.error("That file isn't a valid Job Transition Coach export.")

        with st.expander("Reset"):
            confirm = st.checkbox("I understand this deletes everything")
            if st.button("Delete all data", disabled=not confirm, type="primary"):
                replace_data(storage.default_data())


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------


def render_dashboard(data: dict[str, Any]) -> None:
    settings = data["settings"]
    target = date.fromisoformat(settings["target_date"])
    remaining = storage.days_left(target)
    counts = storage.status_counts(data["applications"])
    open_tasks = [t for t in data["tasks"] if not t["done"]]

    if settings["goal"]:
        st.subheader(f"🎯 {settings['goal']}")
    st.caption(f"Target date: {target:%d %B %Y}")

    cols = st.columns(5)
    cols[0].metric("Days left", remaining)
    cols[1].metric("Open tasks", len(open_tasks))
    cols[2].metric("Active applications", counts["Applied"] + counts["Interview"])
    cols[3].metric("Interviews", counts["Interview"])
    cols[4].metric("Offers", counts["Offer"])

    left, right = st.columns(2)
    with left:
        st.markdown("#### Progress")
        for category, label in storage.CHECKLIST_CATEGORIES.items():
            done, total = storage.checklist_progress(data[category])
            st.progress(
                done / total if total else 0.0,
                text=f"{label}: {done}/{total} done" if total else f"{label}: nothing yet",
            )
    with right:
        st.markdown("#### Application pipeline")
        if data["applications"]:
            st.bar_chart(pd.Series(counts, name="Applications"), horizontal=True, sort=False)
        else:
            st.caption("No applications yet. Add them in the Applications tab.")

    st.markdown("#### Next up")
    if open_tasks:
        for task in open_tasks[:5]:
            st.markdown(f"- {task['text']}")
    else:
        st.caption("No open tasks.")


def render_checklist(category: str, label: str, data: dict[str, Any]) -> None:
    items: list[dict[str, Any]] = data[category]

    with st.form(key=f"add_{category}", clear_on_submit=True):
        col_input, col_button = st.columns([0.85, 0.15], vertical_alignment="bottom")
        text = col_input.text_input(f"Add to {label}")
        added = col_button.form_submit_button("Add", width="stretch")
    if added and text.strip():
        items.append({"id": storage.new_id(), "text": text.strip(), "done": False})
        persist()
        st.rerun()

    if not items:
        st.caption("Nothing here yet.")
        return

    done, total = storage.checklist_progress(items)
    st.progress(done / total, text=f"{done}/{total} done")

    for item in items:
        col_check, col_remove = st.columns([0.85, 0.15])
        # Keys use the item's id, not its position, so removing one item
        # never shifts the ticks onto its neighbours.
        checked = col_check.checkbox(item["text"], value=item["done"], key=f"chk_{item['id']}")
        if checked != item["done"]:
            item["done"] = checked
            persist()
        if col_remove.button("Remove", key=f"del_{item['id']}", width="stretch"):
            items.remove(item)
            persist()
            st.rerun()

    if done and st.button("Clear completed", key=f"clear_{category}"):
        data[category] = [i for i in items if not i["done"]]
        persist()
        st.rerun()


def _applications_frame(applications: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(applications, columns=["id", *storage.APPLICATION_FIELDS])
    frame["date_applied"] = pd.to_datetime(frame["date_applied"], errors="coerce").dt.date
    return frame


def _without_ids(applications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in a.items() if k != "id"} for a in applications]


def render_applications(data: dict[str, Any]) -> None:
    st.caption(
        "Add a row per application. Click a cell to edit it; "
        "select rows and press Delete to remove them."
    )
    # The editor must get the same starting frame on every rerun, otherwise
    # it re-applies its pending edits on top of already-saved data.
    if APPS_BASE_KEY not in st.session_state:
        st.session_state[APPS_BASE_KEY] = _applications_frame(data["applications"])

    edited = st.data_editor(
        st.session_state[APPS_BASE_KEY],
        key=APPS_EDITOR_KEY,
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        column_order=storage.APPLICATION_FIELDS,
        column_config={
            "company": st.column_config.TextColumn("Company", required=True),
            "role": st.column_config.TextColumn("Role"),
            "link": st.column_config.LinkColumn("Job link"),
            "date_applied": st.column_config.DateColumn("Applied on", format="DD MMM YYYY"),
            "status": st.column_config.SelectboxColumn(
                "Status", options=storage.APPLICATION_STATUSES, default="Applied", required=True
            ),
            "notes": st.column_config.TextColumn("Notes", width="large"),
        },
    )

    records = edited.astype(object).where(edited.notna(), None).to_dict("records")
    applications = storage.normalize({"applications": records})["applications"]
    if _without_ids(applications) != _without_ids(data["applications"]):
        data["applications"] = applications
        persist()


def render_notes(data: dict[str, Any]) -> None:
    notes = st.text_area(
        "Notes",
        value=data["notes"],
        height=400,
        placeholder="Interview prep, contacts, salary research…",
        label_visibility="collapsed",
    )
    if notes != data["notes"]:
        data["notes"] = notes
        persist()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="Job Transition Coach", page_icon="🧭", layout="wide")
    data = get_data()
    render_sidebar(data)

    st.title("🧭 Job Transition Coach")

    labels = storage.CHECKLIST_CATEGORIES
    tabs = st.tabs(
        [
            "Dashboard",
            labels["tasks"],
            "Applications",
            labels["courses"],
            labels["portfolio"],
            labels["visa_finance"],
            "Notes",
        ]
    )
    with tabs[0]:
        render_dashboard(data)
    with tabs[1]:
        render_checklist("tasks", labels["tasks"], data)
    with tabs[2]:
        render_applications(data)
    with tabs[3]:
        render_checklist("courses", labels["courses"], data)
    with tabs[4]:
        render_checklist("portfolio", labels["portfolio"], data)
    with tabs[5]:
        render_checklist("visa_finance", labels["visa_finance"], data)
    with tabs[6]:
        render_notes(data)


if __name__ == "__main__":
    main()
