"""Command-owned source manifest; no source bytes or host paths in identities.

The existing scanner remains the parser/graph authority. Config's atomic save and
backup lifecycle owns this small derived projection; reads never write it.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import uuid

from personal_learning_assistant.domain.obsidian_vault_models import VaultNoteFingerprint, VaultScanIssue, VaultScanResult, NoteLinkIntent


def build_manifest(scan, previous=None, *, connection_id=None):
    previous = previous or {}
    connection_id = str(uuid.UUID(connection_id or previous.get("connection_id") or str(uuid.uuid4())))
    prior = {row["relative_path"]: row for row in previous.get("items", [])}
    items = []
    counts = {}
    for note in scan.notes:
        if note.assistant_id:
            counts[note.assistant_id] = counts.get(note.assistant_id, 0) + 1
    for note in scan.notes:
        row = asdict(note)
        # The manifest is portable and must not retain absolute original roots.
        row["absolute_path"] = ""
        row["frontmatter_extra"] = {}
        old = prior.get(note.relative_path, {})
        row["id"] = old.get("id") or str(uuid.uuid4())
        if old.get('legacy_reference'):
            row['legacy_reference'] = dict(old['legacy_reference'])
        row["state"] = "conflict" if counts.get(note.assistant_id, 0) > 1 else "available"
        row["versions"] = list(dict.fromkeys(old.get("versions", []) + [note.source_hash]))
        items.append(row)
    present = {row["relative_path"] for row in items}
    for path, row in prior.items():
        if path not in present:
            items.append({**row, "state": "missing"})
    return {"connection_id": connection_id, "revision": int(previous.get("revision", 0)) + 1,
            "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "manifest_hash": scan.manifest_hash, "vault_name": scan.vault_name,
            "items": items, "aliases": previous.get("aliases", []),
            "issues": [asdict(issue) for issue in scan.issues], "ignored_symlinks": scan.ignored_symlinks}


def manifest_scan(manifest):
    notes = []
    for row in manifest["items"]:
        if row.get("state") == "missing":
            continue
        payload = {key: row[key] for key in VaultNoteFingerprint.__dataclass_fields__}
        payload["links"] = tuple(NoteLinkIntent(**link) for link in payload["links"])
        payload["tags"] = tuple(payload["tags"])
        notes.append(VaultNoteFingerprint(**payload))
    return VaultScanResult("obsidian-vault", manifest["vault_name"], "", tuple(notes),
                           tuple(VaultScanIssue(**issue) for issue in manifest.get("issues", [])),
                           manifest.get("ignored_symlinks", 0), manifest["manifest_hash"])
