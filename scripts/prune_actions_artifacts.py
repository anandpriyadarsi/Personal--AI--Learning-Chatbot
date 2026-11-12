"""Bounded, release-safe pruning of GitHub Actions artifacts.

Runs only inside ANVAYA's maintenance GitHub Actions workflow. Never deletes
source code, releases, packages, caches, or artifacts in other repositories.
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO = "anandpriyadarsi/Personal--AI--Learning-Chatbot"
MAX_DELETE = 450
MIN_AGE_DAYS = 2
PROTECTED = re.compile(
    r"apk|release|backup|private|certification|provenance|snapshot|"
    r"signed|migration|shared-android-build|anvaya-android-test",
    re.IGNORECASE,
)
API_ROOT = "https://api.github.com"

def api(path: str, method: str = "GET") -> dict:
    token = os.environ["GH_TOKEN"]
    request = Request(
        API_ROOT + path,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ANVAYA-Actions-storage-cleanup",
        },
    )
    for attempt in range(4):
        try:
            with urlopen(request, timeout=25) as response:
                data = response.read()
                return json.loads(data) if data else {}
        except HTTPError as exc:
            if exc.code in (403, 429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(min(2 ** attempt * 5, 40))
                continue
            raise RuntimeError(f"GitHub API {method} {path}: HTTP {exc.code}") from exc
        except URLError as exc:
            if attempt < 3:
                time.sleep(2 ** attempt * 3)
                continue
            raise RuntimeError(f"GitHub API {method} {path}: {exc}") from exc
    raise AssertionError("unreachable")

def candidate(artifact: dict, cutoff: datetime) -> bool:
    name = artifact.get("name", "")
    if artifact.get("expired", False) or PROTECTED.search(name):
        return False
    if not artifact.get("id") or not artifact.get("created_at"):
        return False
    created = datetime.fromisoformat(artifact["created_at"].replace("Z", "+00:00"))
    return created < cutoff

def fetch_artifacts() -> list[dict]:
    """Snapshot pages before deleting so pagination cannot shift mid-cleanup."""
    artifacts: list[dict] = []
    for page in range(1, 100):
        result = api(f"/repos/{REPO}/actions/artifacts?per_page=100&page={page}")
        batch = result.get("artifacts", [])
        artifacts.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise RuntimeError("Too many pages; refusing incomplete inventory")
    return artifacts

def summary(msg: str) -> None:
    print(msg, flush=True)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as out:
            out.write(msg + "\n")

def disable_cleanup_workflow(reason: str) -> None:
    """Stop further scheduled cleanup after completion or safety deadline."""
    summary("- Disabling scheduled cleanup: " + reason)
    api(f"/repos/{REPO}/actions/workflows/actions-storage-cleanup.yml/disable", method="PUT")


def main() -> int:
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        raise RuntimeError("Repository guard failed: not ANVAYA")
    dry_run = os.environ.get("DRY_RUN", "false").strip().lower() == "true"
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule" and datetime.now(timezone.utc) >= datetime(2026, 11, 17, tzinfo=timezone.utc):
        disable_cleanup_workflow("safety cutoff date reached")
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=MIN_AGE_DAYS)
    all_artifacts = fetch_artifacts()
    eligible = [a for a in all_artifacts if candidate(a, cutoff)]
    eligible.sort(
        key=lambda a: (int(a.get("size_in_bytes") or 0), a["created_at"]),
        reverse=True,
    )
    selected = eligible[:MAX_DELETE]
    total_bytes = sum(int(a.get("size_in_bytes") or 0) for a in selected)
    summary("## ANVAYA emergency Actions cleanup")
    summary(f"- Mode: **{'DRY RUN' if dry_run else 'DELETE'}**")
    summary(f"- Inventory: {len(all_artifacts)}; eligible: {len(eligible)}; protected/recent/expired: {len(all_artifacts) - len(eligible)}")
    summary(f"- Selected: {len(selected)} artifacts, totaling {total_bytes / 1024**2:,.1f} MiB")
    summary("- Protected by name: APKs, releases, backups, private fixtures, signing and certification evidence")
    summary("- No GitHub Releases, source files, workflow runs or academic records are deleted")
    for artifact in selected[:12]:
        summary(f"  - {artifact['name']}: {int(artifact.get('size_in_bytes') or 0) / 1024**2:.1f} MiB")
    if dry_run:
        summary("No changes made in dry-run mode.")
        return 0
    if not selected:
        disable_cleanup_workflow("no eligible old routine artifacts remain")
        return 0
    deleted = 0
    freed_bytes = 0
    errors = 0
    for artifact in selected:
        try:
            api(f"/repos/{REPO}/actions/artifacts/{artifact['id']}", method="DELETE")
        except RuntimeError as exc:
            errors += 1
            print(f"::warning::{exc}", flush=True)
            if errors >= 5:
                summary("Stopped after five deletion errors.")
                break
            continue
        deleted += 1
        freed_bytes += int(artifact.get("size_in_bytes") or 0)
        if deleted % 25 == 0:
            print(f"Deleted {deleted}/{len(selected)} artifacts", flush=True)
        time.sleep(0.12)
    summary(f"- **Deleted {deleted} artifacts, totaling {freed_bytes / 1024**2:,.1f} MiB**")
    summary(f"- Remaining candidates in snapshot: {max(0, len(eligible) - deleted)}")
    summary("- Billing figures can lag 6–12 hours; accrued usage is not reduced retroactively.")
    if errors:
        summary(f"- Deletion errors: {errors} (see job logs)")
        return 1
    if len(eligible) <= deleted:
        disable_cleanup_workflow("all eligible old routine artifacts were deleted")
    return 0

if __name__ == "__main__":
    sys.exit(main())
