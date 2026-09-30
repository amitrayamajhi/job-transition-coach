import json
from datetime import date, datetime

import pytest

from job_coach import storage

TODAY = date(2026, 1, 1)


def test_default_data_has_every_section():
    data = storage.default_data(TODAY)
    assert data["settings"] == {"target_date": "2026-04-01", "goal": ""}
    for category in storage.CHECKLIST_CATEGORIES:
        assert data[category] == []
    assert data["applications"] == []
    assert data["notes"] == ""


def test_load_missing_file_returns_defaults(tmp_path):
    data = storage.load_data(str(tmp_path / "missing.json"))
    assert data["tasks"] == []


def test_load_corrupt_file_returns_defaults(tmp_path):
    path = tmp_path / "data.json"
    path.write_text("{not json", encoding="utf-8")
    assert storage.load_data(str(path))["tasks"] == []


def test_save_then_load_round_trips(tmp_path):
    path = str(tmp_path / "data.json")
    data = storage.default_data(TODAY)
    data["settings"]["goal"] = "Data analyst in Dubai"
    data["tasks"].append({"id": "a1", "text": "Update CV", "done": True})
    data["applications"].append(
        {
            "id": "b2",
            "company": "Acme",
            "role": "Analyst",
            "link": "https://example.com/job",
            "date_applied": "2026-01-02",
            "status": "Interview",
            "notes": "Ünïcode ok",
        }
    )
    data["notes"] = "Remember to follow up"

    storage.save_data(data, path)

    assert storage.load_data(path) == data
    assert not (tmp_path / "data.json.tmp").exists()


def test_normalize_upgrades_files_from_the_first_version():
    # Shape written by the original job_transition_coach_streamlit.py.
    old = {
        "tasks": [{"text": "Update CV", "done": True}],
        "courses": [],
        "portfolio": [],
        "applications": [{"text": "Acme - Analyst", "done": False}],
        "visa_finance": [],
        "notes": "hello",
    }
    data = storage.normalize(old, TODAY)

    assert data["tasks"][0]["text"] == "Update CV"
    assert data["tasks"][0]["done"] is True
    assert data["tasks"][0]["id"]
    assert data["applications"][0]["company"] == "Acme - Analyst"
    assert data["applications"][0]["status"] == "Applied"
    assert data["notes"] == "hello"
    assert data["settings"]["target_date"] == "2026-04-01"


def test_normalize_drops_bad_items_and_fixes_bad_values():
    data = storage.normalize(
        {
            "settings": {"target_date": "not a date", "goal": None},
            "tasks": ["  plain string  ", {"text": "   "}, 42, None],
            "applications": [
                {"company": "", "role": ""},
                {"company": "Acme", "status": "Ghosted", "date_applied": "garbage"},
            ],
            "notes": 123,
        },
        TODAY,
    )
    assert [t["text"] for t in data["tasks"]] == ["plain string"]
    assert len(data["applications"]) == 1
    assert data["applications"][0]["status"] == "Applied"
    assert data["applications"][0]["date_applied"] == ""
    assert data["settings"] == {"target_date": "2026-04-01", "goal": ""}
    assert data["notes"] == ""


@pytest.mark.parametrize(
    "value, expected",
    [
        (date(2026, 3, 4), "2026-03-04"),
        (datetime(2026, 3, 4, 15, 30), "2026-03-04"),
        ("2026-03-04T10:00:00", "2026-03-04"),
    ],
)
def test_application_dates_accept_dates_datetimes_and_strings(value, expected):
    data = storage.normalize({"applications": [{"company": "Acme", "date_applied": value}]})
    assert data["applications"][0]["date_applied"] == expected


def test_normalize_non_dict_returns_defaults():
    assert storage.normalize([1, 2, 3], TODAY) == storage.default_data(TODAY)


def test_from_json_rejects_invalid_json():
    with pytest.raises(ValueError):
        storage.from_json("nope")


def test_to_json_from_json_round_trip():
    data = storage.normalize({"tasks": [{"text": "x"}]}, TODAY)
    assert storage.from_json(storage.to_json(data)) == data
    assert json.loads(storage.to_json(data))["tasks"][0]["text"] == "x"


def test_applications_to_csv():
    csv_text = storage.applications_to_csv(
        [
            {
                "id": "1",
                "company": "Acme, Inc",
                "role": "Analyst",
                "link": "",
                "date_applied": "",
                "status": "Offer",
                "notes": "",
            }
        ]
    )
    lines = csv_text.strip().splitlines()
    assert lines[0] == "company,role,link,date_applied,status,notes"
    assert lines[1] == '"Acme, Inc",Analyst,,,Offer,'


@pytest.mark.parametrize(
    "target, expected",
    [(date(2026, 1, 11), 10), (date(2026, 1, 1), 0), (date(2025, 12, 1), 0)],
)
def test_days_left_is_clamped_at_zero(target, expected):
    assert storage.days_left(target, TODAY) == expected


def test_checklist_progress():
    items = [{"done": True}, {"done": False}, {"done": True}]
    assert storage.checklist_progress(items) == (2, 3)
    assert storage.checklist_progress([]) == (0, 0)


def test_status_counts_includes_every_status_in_order():
    counts = storage.status_counts(
        [{"status": "Offer"}, {"status": "Offer"}, {"status": "Applied"}]
    )
    assert list(counts) == storage.APPLICATION_STATUSES
    assert counts["Offer"] == 2
    assert counts["Applied"] == 1
    assert counts["Interview"] == 0
