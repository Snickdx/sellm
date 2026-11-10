"""Exit-interview transcript bands must land in distinct score ranges per scenario."""

from __future__ import annotations

import pytest

from app.examiner.scorer import score_session
from tests.fixtures.exit_transcripts.bands_loader import (
    REQUIRED_COMPETENCIES,
    build_band_bundle,
    list_scenario_slugs,
    load_bands,
)

SCENARIOS = list_scenario_slugs()


@pytest.mark.parametrize("scenario_slug", SCENARIOS)
@pytest.mark.parametrize("band_key", ["low", "mid", "high"])
def test_band_scores_land_in_expected_range(scenario_slug: str, band_key: str):
    bundle, _plan, meta = build_band_bundle(scenario_slug, band_key)
    lo, hi = meta["expected_score_range"]
    reports = score_session(
        bundle,
        meta["repository_sha"],
        scenario_slug=meta["scenario_slug"],
    )
    assert len(reports) == 1
    comps = reports[0]["competencies"]
    assert len(comps) == 5
    for row in comps:
        assert row["score"] is not None, row
        assert lo <= row["score"] <= hi, (
            f"{scenario_slug}/{band_key}/{row['name']}: score={row['score']} "
            f"not in [{lo},{hi}]; rationale={row.get('rationale')}"
        )


@pytest.mark.parametrize("scenario_slug", SCENARIOS)
def test_bands_are_ordered_low_lt_mid_lt_high(scenario_slug: str):
    averages: dict[str, float] = {}
    for band_key in ("low", "mid", "high"):
        bundle, _plan, meta = build_band_bundle(scenario_slug, band_key)
        reports = score_session(
            bundle,
            meta["repository_sha"],
            scenario_slug=meta["scenario_slug"],
        )
        scores = [c["score"] for c in reports[0]["competencies"] if c["score"] is not None]
        averages[band_key] = sum(scores) / len(scores)
    assert averages["low"] < averages["mid"] < averages["high"], averages


@pytest.mark.parametrize("scenario_slug", SCENARIOS)
def test_fixture_covers_all_competencies(scenario_slug: str):
    fixture = load_bands(scenario_slug)
    for band_key, band in fixture["bands"].items():
        assert set(band["answers"]) == REQUIRED_COMPETENCIES, f"{scenario_slug}/{band_key}"


def test_all_seven_scenarios_have_bands():
    assert set(SCENARIOS) == {
        "job-board",
        "library",
        "uwi-connect",
        "thesis-tracker",
        "student-accommodation",
        "ta-allocations",
        "career-advising",
    }
