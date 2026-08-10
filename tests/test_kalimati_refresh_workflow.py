"""Static contract for the weekly Kalimati GitHub Actions job."""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(".github/workflows/ingest.yml")


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_kalimati_has_one_weekly_schedule_and_a_manual_dispatch() -> None:
    text = _text()
    assert 'cron: "17 2 * * 2"' in text
    assert "github.event.schedule == '17 2 * * 2'" in text
    assert "options: [both, world-bank, nrb-bfs, kalimati]" in text
    assert "github.event.inputs.job == 'kalimati'" in text

    cron = re.search(r'cron: "(17 2 \* \* 2)"', text)
    assert cron is not None
    minute, hour, day_of_month, month, weekday = cron.group(1).split()
    assert (minute, hour) == ("17", "2")
    assert day_of_month == month == "*"
    assert weekday != "*"  # one weekday, not a daily schedule


def test_kalimati_job_uses_the_polite_idempotent_loader() -> None:
    text = _text()
    assert "make kalimati-official PY=python" in text
    assert "rows_loaded=${loaded:-unknown}" in text
    assert "weekly-kalimati-refresh" in text
    assert "cancel-in-progress: false" in text


def test_a_failed_refresh_opens_or_updates_a_labelled_issue() -> None:
    text = _text()
    assert "issues: write" in text
    assert "if: steps.refresh.outputs.exit_code != '0'" in text
    assert "github.rest.issues.createLabel" in text
    assert "github.rest.issues.createComment" in text
    assert "github.rest.issues.create" in text
    assert "Weekly Kalimati price refresh failed" in text


def test_the_run_reports_before_after_dates_rows_and_runtime() -> None:
    text = _text()
    assert "Read portal freshness before the refresh" in text
    assert "Read portal freshness after the refresh" in text
    assert "Rows loaded:" in text
    assert "Runtime:" in text
    assert "Portal data date:" in text
    assert "Official Kalimati check date:" in text
