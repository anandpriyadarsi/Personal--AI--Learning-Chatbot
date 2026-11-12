"""Static guard for Actions artifact retention and storage-sensitive policy."""
from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class ActionsStoragePolicyTests(unittest.TestCase):
    def test_every_upload_has_bounded_retention(self) -> None:
        uploads = 0
        for workflow in sorted(WORKFLOWS.glob("*.yml")):
            lines = workflow.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                if "uses: actions/upload-artifact@v4" not in line:
                    continue
                uploads += 1
                indent = len(line) - len(line.lstrip())
                end = index + 1
                while end < len(lines):
                    item = lines[end]
                    item_indent = len(item) - len(item.lstrip())
                    if item_indent <= indent and re.match(
                        r"\s*- (?:uses|name|run|id):", item
                    ):
                        break
                    end += 1
                step = "\n".join(lines[index + 1 : end])
                matches = re.findall(r"(?m)^\s+retention-days:\s*(\d+)\s*$", step)
                self.assertEqual(
                    len(matches), 1, f"{workflow.name}:{index + 1}: missing retention"
                )
                days = int(matches[0])
                self.assertGreaterEqual(days, 1)
                self.assertLessEqual(days, 7, f"{workflow.name}: excessive retention")
        self.assertGreater(uploads, 20)

    def test_bulky_architecture_images_are_failure_only(self) -> None:
        content = (WORKFLOWS / "architecture-validation.yml").read_text(encoding="utf-8")
        success, failure = content.split(
            "      - name: Preserve large browser screenshots and logs only on failure", 1
        )
        self.assertIn("      - name: Preserve compact development reports", success)
        self.assertNotIn("/run-*/screenshots/*", success)
        self.assertNotIn("/run-*/*.log", success)
        self.assertIn("if: failure()", failure.split("  acceptance:", 1)[0])
        self.assertIn("/run-*/screenshots/*", failure)

    def test_benchmark_not_automatically_started_after_every_architecture_run(self) -> None:
        content = (WORKFLOWS / "verification-benchmark.yml").read_text(encoding="utf-8")
        self.assertNotIn("  workflow_run:", content)
        self.assertIn("architecture_run_id:", content)

    def test_release_does_not_duplicate_apk_in_actions_artifacts(self) -> None:
        content = (WORKFLOWS / "unified-android-release.yml").read_text(
            encoding="utf-8"
        )
        actions_step = content.split("      - uses: actions/upload-artifact@v4")[-1]
        self.assertIn("release-assets/BUILD.json", actions_step)
        self.assertNotIn("path: release-assets/*", actions_step)
        self.assertNotIn("release-assets/ANVAYA-Unified-Latest.apk", actions_step)


if __name__ == "__main__":
    unittest.main()
