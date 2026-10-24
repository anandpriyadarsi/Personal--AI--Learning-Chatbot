"""Read-only repository inventory. Generates candidate lists, never deletes files.

Use: python scripts/repository_hygiene_report.py --output path/to/report.json
This report is advisory: unreferenced files can still be needed externally.
"""
import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".py", ".ps1", ".md", ".rst", ".txt", ".json", ".toml", ".ini",
    ".yml", ".yaml", ".js", ".cjs", ".html", ".css", ".sh", ".sql",
}
SKIP_REFERENCE_PREFIXES = ("docs/archive/",)
SIZE_THRESHOLD = 1_000_000


def git_bytes(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout


def tracked_paths():
    raw = git_bytes("ls-files", "-z")
    return sorted(p.decode("utf-8", "replace") for p in raw.split(b"\0") if p)


def blob_duplicates():
    seen = defaultdict(list)
    for entry in git_bytes("ls-files", "--stage", "-z").split(b"\0"):
        if not entry or b"\t" not in entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        bits = metadata.split()
        if len(bits) != 3 or bits[-1] != b"0":
            continue
        seen[bits[1].decode("ascii")].append(path.decode("utf-8", "replace"))
    return [paths for paths in seen.values() if len(paths) > 1]


def build_report():
    paths = tracked_paths()
    root_docs = sorted(p for p in paths if "/" not in p and p.endswith(".md"))
    references = defaultdict(set)
    regex = None
    if root_docs:
        # One pass per file instead of a full re-read for every document name.
        regex = re.compile("|".join(re.escape(name) for name in
                                    sorted(root_docs, key=len, reverse=True)))
    for p in paths:
        file = ROOT / p
        if p.startswith(SKIP_REFERENCE_PREFIXES) or file.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if not file.is_file():
            continue
        content = file.read_text(encoding="utf-8", errors="replace")
        if regex is None:
            continue
        for match in regex.finditer(content):
            name = match.group(0)
            if p != name:
                references[name].add(p)

    largest = []
    for p in paths:
        file = ROOT / p
        if file.is_file():
            size = file.stat().st_size
            if size >= SIZE_THRESHOLD:
                largest.append({"path": p, "bytes": size})
    largest.sort(key=lambda item: item["bytes"], reverse=True)
    return {
        "disclaimer": (
            "Read-only classification. Missing tracked references is not evidence "
            "that a file is safe to delete or move."
        ),
        "tracked_file_count": len(paths),
        "root_file_count": sum("/" not in p for p in paths),
        "root_markdown_count": len(root_docs),
        "root_markdown_without_tracked_text_reference": sorted(
            p for p in root_docs if not references[p]
        ),
        "root_markdown_references": {
            p: sorted(references[p]) for p in root_docs if references[p]
        },
        "duplicate_blob_path_groups": blob_duplicates(),
        "tracked_backup_paths": sorted(
            p for p in paths if p.startswith(("backup/", "backups/"))
        ),
        "large_tracked_files": largest,
        "manual_review_required": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Write JSON report (otherwise print to stdout)")
    args = parser.parse_args()
    report = json.dumps(build_report(), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        dest = Path(args.output)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(report, encoding="utf-8")
        print(f"Inventory written to {dest}")
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
