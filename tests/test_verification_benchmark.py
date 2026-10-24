"""Offline, reproducible regression tests for GitHub Actions benchmark evidence."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verification_benchmark.py"
SPEC = importlib.util.spec_from_file_location("verification_benchmark", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def job(name, started="2026-10-23T01:00:00Z", ended="2026-10-23T01:12:00Z",
        step_name="Full validator (no deselections)", step_result="success"):
    steps = []
    if not name.startswith("Cross-platform"):
        steps.append({
            "name": step_name,
            "started_at": started,
            "completed_at": ended,
            "conclusion": step_result,
        })
    return {
        "name": name, "status": "completed", "conclusion": "success",
        "started_at": started, "completed_at": ended, "steps": steps,
    }


def full_jobs(minutes=12):
    end = f"2026-10-23T01:{minutes:02}:00Z"
    return {"jobs": [
        job("Synthetic development (ubuntu-latest)", ended=end),
        job("Synthetic development (windows-latest)", ended=end),
        job("Cross-platform development acceptance", ended=f"2026-10-23T01:{minutes+1:02}:00Z"),
    ]}


class BenchmarkTests(unittest.TestCase):
    def test_full_cross_platform_time_and_steps(self):
        result = MODULE.inspect(full_jobs(), "architecture")
        self.assertEqual(result["wall_seconds"], 780)
        self.assertEqual(result["jobs"][0]["target_step_seconds"], 720)
        self.assertEqual(result["jobs"][2]["target_step_result"], "not-applicable")

    def test_faster_delta_is_positive_saved(self):
        old = MODULE.inspect(full_jobs(12), "architecture")
        new = MODULE.inspect(full_jobs(8), "architecture")
        result = MODULE.comparison(old, new, before_run="https://example.org/old",
                                   after_run="https://example.org/new")
        self.assertEqual(result["time_saved_seconds"], 240)
        self.assertEqual(result["change_seconds"], -240)
        self.assertEqual(result["relative_change_percent"], 30.8)

    def test_slower_run_does_not_claim_savings(self):
        old = MODULE.inspect(full_jobs(8), "architecture")
        new = MODULE.inspect(full_jobs(12), "architecture")
        result = MODULE.comparison(old, new, before_run="old", after_run="new")
        self.assertLess(result["time_saved_seconds"], 0)
        self.assertIn("OBSERVATIONAL_ONLY", result["claim"])

    def test_missing_windows_is_invalid(self):
        data = full_jobs()
        data["jobs"] = [j for j in data["jobs"] if "windows" not in j["name"]]
        with self.assertRaises(MODULE.InvalidEvidence):
            MODULE.inspect(data, "architecture")

    def test_duplicate_windows_is_invalid(self):
        data = full_jobs()
        data["jobs"].append(data["jobs"][1])
        with self.assertRaises(MODULE.InvalidEvidence):
            MODULE.inspect(data, "architecture")

    def test_failed_job_is_rejected(self):
        data = full_jobs()
        data["jobs"][1]["conclusion"] = "failure"
        with self.assertRaises(MODULE.InvalidEvidence):
            MODULE.inspect(data, "architecture")

    def test_running_job_is_rejected(self):
        data = full_jobs()
        data["jobs"][1]["status"] = "in_progress"
        with self.assertRaises(MODULE.InvalidEvidence):
            MODULE.inspect(data, "architecture")

    def test_missing_timestamp_is_rejected(self):
        data = full_jobs()
        data["jobs"][0]["completed_at"] = None
        with self.assertRaises(MODULE.InvalidEvidence):
            MODULE.inspect(data, "architecture")

    def test_negative_duration_is_rejected(self):
        with self.assertRaises(MODULE.InvalidEvidence):
            MODULE.seconds("2026-10-23T05:00:00Z", "2026-10-23T04:00:00Z")

    def test_timezone_normalization(self):
        self.assertEqual(
            MODULE.seconds("2026-10-23T06:30:00+05:30", "2026-10-23T01:10:00Z"),
            600,
        )

    def test_ui_optimized_step_skipped(self):
        data = {"jobs": [
            job("UI V2 (ubuntu-latest)", step_name="Full regression suite", step_result="skipped"),
            job("UI V2 (windows-latest)", step_name="Full regression suite", step_result="skipped"),
        ]}
        inspected = MODULE.inspect(data, "ui")
        self.assertIsNone(inspected["jobs"][0]["target_step_seconds"])
        self.assertEqual(inspected["jobs"][0]["target_step_result"], "skipped")

    def test_uncertified_full_step_is_rejected(self):
        data = full_jobs()
        data["jobs"][0]["steps"][0]["conclusion"] = "failure"
        with self.assertRaises(MODULE.InvalidEvidence):
            MODULE.inspect(data, "architecture")

    def test_fast_single_job(self):
        data = {"jobs": [
            job("Change-aware Python and JavaScript smoke", ended="2026-10-23T01:00:29Z",
                step_name="Change-aware fast feedback (not merge acceptance)"),
        ]}
        summary = MODULE.inspect(data, "fast")
        self.assertEqual(summary["wall_seconds"], 29)

    def test_no_evidence_cannot_be_compared(self):
        with self.assertRaises(MODULE.InvalidEvidence):
            MODULE.inspect({}, "architecture")

    def test_complete_cli_writes_machine_readable_and_markdown(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            before = root / "before.json"
            after = root / "after.json"
            before.write_text(json.dumps(full_jobs(12)), encoding="utf-8")
            after.write_text(json.dumps(full_jobs(8)), encoding="utf-8")
            outfile = root / "result.json"
            markdown = root / "result.md"
            code = MODULE.main([
                "--before", str(before), "--after", str(after),
                "--group", "architecture", "--before-run", "old",
                "--after-run", "new", "--output", str(outfile),
                "--markdown", str(markdown),
            ])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(outfile.read_text())["time_saved_seconds"], 240)
            self.assertIn("observational", markdown.read_text().lower())

    def test_invalid_cli_does_not_write_fake_result(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            missing = root / "missing.json"
            outfile = root / "result.json"
            code = MODULE.main([
                "--before", str(missing), "--after", str(missing),
                "--group", "architecture", "--before-run", "old",
                "--after-run", "new", "--output", str(outfile),
            ])
            self.assertEqual(code, 2)
            self.assertFalse(outfile.exists())



class FinalRepairTests(unittest.TestCase):
    def test_skipped_authoritative_steps_are_rejected(self):
        for group, data in [('architecture', full_jobs()), ('fast', {'jobs': [
            job('Change-aware Python and JavaScript smoke',
                step_name='Change-aware fast feedback (not merge acceptance)')]})]:
            data['jobs'][0]['steps'][0]['conclusion'] = 'skipped'
            with self.assertRaises(MODULE.InvalidEvidence):
                MODULE.inspect(data, group)

    def test_subsecond_negative_duration_is_rejected(self):
        with self.assertRaises(MODULE.InvalidEvidence):
            MODULE.seconds('2026-10-23T01:00:00.9Z', '2026-10-23T01:00:00.1Z')

    def test_mixed_source_or_run_identity_is_rejected(self):
        for field in ('head_sha', 'run_id'):
            data = full_jobs()
            for item in data['jobs']:
                item.update(head_sha='a' * 40, run_id=123)
            data['jobs'][1][field] = 'b' * 40 if field == 'head_sha' else 456
            with self.assertRaises(MODULE.InvalidEvidence):
                MODULE.inspect(data, 'architecture')

    def test_missing_identity_in_one_job_is_rejected(self):
        data = full_jobs()
        data['jobs'][0]['head_sha'] = 'a' * 40
        with self.assertRaises(MODULE.InvalidEvidence):
            MODULE.inspect(data, 'architecture')

    def test_metadata_records_queue_elapsed_and_critical_path(self):
        data = full_jobs()
        for item in data['jobs']:
            item.update(head_sha='a' * 40, run_id=123,
                        created_at='2026-10-23T00:59:50Z')
        # Add a real dependency-install step; validator timing is separate.
        data['jobs'][0]['steps'].append({
            'name': 'Install tracked test dependencies', 'conclusion': 'success',
            'started_at': '2026-10-23T01:00:00Z',
            'completed_at': '2026-10-23T01:00:20Z'})
        meta = {'id': 123, 'head_sha': 'a' * 40,
                'status': 'completed', 'conclusion': 'success',
                'created_at': '2026-10-23T00:59:00Z'}
        result = MODULE.inspect(data, 'architecture', run_response=meta)
        self.assertEqual(result['initial_queue_seconds'], 60)
        self.assertEqual(result['elapsed_from_created_seconds'], 840)
        self.assertEqual(result['source_sha'], 'a' * 40)
        self.assertEqual(result['critical_path_job'], 'Synthetic development (ubuntu-latest)')
        self.assertEqual(result['jobs'][0]['queue_seconds'], 10)
        self.assertEqual(result['jobs'][0]['steps'][-1]['seconds'], 20)

    def test_metadata_must_match_successful_job_identity(self):
        for field, value in [('id', 456), ('head_sha', 'b' * 40),
                             ('conclusion', 'failure')]:
            data = full_jobs()
            for item in data['jobs']:
                item.update(head_sha='a' * 40, run_id=123)
            meta = {'id': 123, 'head_sha': 'a' * 40,
                    'status': 'completed', 'conclusion': 'success',
                    'created_at': '2026-10-23T00:59:00Z'}
            meta[field] = value
            with self.assertRaises(MODULE.InvalidEvidence):
                MODULE.inspect(data, 'architecture', run_response=meta)

    def test_step_outside_job_time_is_rejected(self):
        data = full_jobs()
        data['jobs'][0]['steps'][0]['completed_at'] = '2026-10-23T02:00:00Z'
        with self.assertRaises(MODULE.InvalidEvidence):
            MODULE.inspect(data, 'architecture')


if __name__ == "__main__":
    unittest.main()
