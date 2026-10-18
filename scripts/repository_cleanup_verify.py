"""Read-only Git-tree checks for the October 2026 ANVAYA documentation cleanup.

Runs without project dependencies on Windows and Ubuntu. This is NOT an app test.
"""
import json
import subprocess
from pathlib import Path

BASE_SHA = "ce2e4e06175f76778f114a85f7552160aeb08a99"
ROOT = Path(__file__).resolve().parents[1]

def git(*args):
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True,
        capture_output=True, text=True, encoding="utf-8",
    )
    return result.stdout.strip()

def main():
    manifest_path = ROOT / "docs" / "maintenance" / "archive-manifest.json"
    records = json.loads(manifest_path.read_text(encoding="utf-8"))["renames"]
    assert len(records) == 78, f"Unexpected archived report count: {len(records)}"
    unique_old = set()
    unique_new = set()
    for record in records:
        old, new, recorded_sha = record["original"], record["archive"], record["sha"]
        assert old not in unique_old and new not in unique_new, "Duplicate archive path"
        unique_old.add(old); unique_new.add(new)
        assert old.startswith(("PHASE3_", "PHASE4_", "PHASE5_", "PHASE6_", "PHASE7_"))
        assert new.startswith("docs/archive/phase") and new.endswith("/" + old)
        assert not (ROOT / old).exists(), f"Obsolete root path still present: {old}"
        assert (ROOT / new).is_file(), f"Archived report absent: {new}"
        base_sha = git("rev-parse", BASE_SHA + ":" + old)
        current_sha = git("rev-parse", "HEAD:" + new)
        assert recorded_sha == base_sha == current_sha, f"Content mismatch: {old}"
    allowed_additions = {
        "docs/README.md",
        "docs/archive/README.md",
        "docs/maintenance/archive-manifest.json",
        "docs/maintenance/repository-cleanup-2026-10.md",
        ".github/workflows/repository-cleanup.yml",
        "scripts/repository_cleanup_verify.py",
    }
    changes = git("diff", "--name-only", "--no-renames", BASE_SHA, "HEAD").splitlines()
    modified = set(changes) - unique_old - unique_new - allowed_additions
    assert not modified, f"Unapproved changes beyond archived documentation: {sorted(modified)}"
    assert all((ROOT / x).is_file() for x in [
        "phase7_web.py", "requirements.txt", "pytest.ini",
        ".github/workflows/assessment-studio.yml",
        ".github/workflows/learning-studio.yml",
        "personal_learning_assistant/ui/web/routes.py",
        "tests/test_architecture_characterization.py",
    ])
    try:
        git("diff", "--check", BASE_SHA, "HEAD")
    except subprocess.CalledProcessError as error:
        print("Whitespace check STDOUT:", error.stdout)
        print("Whitespace check STDERR:", error.stderr)
        raise
    print(f"PASS: {len(records)} byte-identical documentation moves; "
          f"{len(changes)} changed paths within allowlist; "
          "no application, academic, CI or test source was modified.")

if __name__ == "__main__":
    main()
