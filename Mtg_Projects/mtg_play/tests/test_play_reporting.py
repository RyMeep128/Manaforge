"""Play report allowlisting: reports never serialize deck or engine payloads."""

import json
from mtg_play.reporting import PlayReport
from mtg_play.presentation import SETUP_CAUSES


def test_report_exports_only_bounded_fixed_metadata_and_error_codes():
    report = PlayReport(SETUP_CAUSES)
    report.format = "commander"
    report.accept(
        {
            "compatibility": {
                "manaforge_version": "0.5.23-alpha.1",
                "adapter_version": "0.2.1-alpha.1",
                "engine_version": "1.4.62-V1",
                "protocol_version": 1,
                "artifact_manifest_sha256": "a" * 64,
                "credentials": "PRIVATE",
            },
            "lifecycle": [
                {
                    "stage": "deck_resolution",
                    "state": "failed",
                    "elapsed_ms": 12.5,
                    "code": "PLAY_DECK_RESOLUTION_FAILED",
                    "deck": "PRIVATE",
                }
            ]
            * 200,
            "failure": {
                "operation": "start",
                "code": "PLAY_DECK_RESOLUTION_FAILED",
                "cause": "PYTHON_NAME_ERROR",
                "exception": "PRIVATE",
            },
            "hand": "PRIVATE",
            "workspace": "PRIVATE",
            "opponent_deck": "PRIVATE",
        }
    )
    snapshot = report.snapshot(active=False, closing=False, busy=False)
    assert len(snapshot["lifecycle"]) == 128
    assert snapshot["compatibility"]["engine_version"] == "1.4.62-V1"
    assert snapshot["failure"]["cause"] == "PYTHON_NAME_ERROR"
    assert "PRIVATE" not in json.dumps(snapshot)
    snapshot["lifecycle"].clear()
    assert (
        len(report.snapshot(active=False, closing=False, busy=False)["lifecycle"])
        == 128
    )


def test_malformed_or_private_payloads_do_not_become_feedback_data():
    report = PlayReport(SETUP_CAUSES)
    report.format = {}
    report.accept(
        {
            "compatibility": {
                "engine_version": "PRIVATE",
                "protocol_version": True,
                "artifact_manifest_sha256": "PRIVATE",
            },
            "lifecycle": [
                {"stage": "PRIVATE", "state": "failed", "elapsed_ms": 1},
                {"stage": "deck_resolution", "state": [], "elapsed_ms": 1},
                {
                    "stage": "deck_resolution",
                    "state": "failed",
                    "elapsed_ms": float("nan"),
                },
                {
                    "stage": "deck_resolution",
                    "state": "failed",
                    "elapsed_ms": 1,
                    "code": "PRIVATE",
                },
            ],
            "failure": {"operation": "start", "code": "PRIVATE", "cause": "PRIVATE"},
        }
    )
    snapshot = report.snapshot(active=False, closing=False, busy=False)
    assert not snapshot["lifecycle"] and not snapshot["compatibility"]
    assert snapshot["format"] is None and "PRIVATE" not in json.dumps(snapshot)
