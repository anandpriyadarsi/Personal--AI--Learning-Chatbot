"""Read-only scanner for Phase 3 legacy structured-data sources.

The scanner never creates, rewrites, normalizes, or repairs source files. It
hashes raw bytes first, then performs best-effort JSON/version inspection so a
later importer can make explicit decisions from a reproducible manifest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple, Union


PathLike = Union[str, Path]
SOURCE_TYPE_LEGACY_JSON = "legacy_json"
MANIFEST_VERSION = 1

STATUS_VALID_JSON = "valid_json"
STATUS_EMPTY = "empty"
STATUS_MISSING = "missing"
STATUS_INVALID_JSON = "invalid_json"
STATUS_NOT_FILE = "not_file"
STATUS_SYMLINK = "symlink"


@dataclass(frozen=True)
class LegacySourceSpec:
    filename: str
    required: bool = True
    allow_empty: bool = False
    source_type: str = SOURCE_TYPE_LEGACY_JSON

    @property
    def canonical_path(self) -> str:
        return "data/{}".format(self.filename)


LEGACY_SOURCE_SPECS: Tuple[LegacySourceSpec, ...] = (
    LegacySourceSpec("notes.json"),
    LegacySourceSpec("resources.json", allow_empty=True),
    LegacySourceSpec("courses.json"),
    LegacySourceSpec("learning_memory.json"),
    LegacySourceSpec("course_progress_history.json"),
    LegacySourceSpec("weekly_study_plans.json"),
    LegacySourceSpec("multi_course_weekly_plans.json"),
    LegacySourceSpec("assessments.json"),
    LegacySourceSpec("assessment_workspace.json"),
    LegacySourceSpec("obsidian_config.json"),
    LegacySourceSpec("intelligent_study_plans.json", required=False),
    LegacySourceSpec("semester_grade_config.json", required=False),
)


@dataclass(frozen=True)
class LegacySourceSnapshot:
    physical_path: Path
    canonical_path: str
    source_type: str
    required: bool
    allow_empty: bool
    status: str
    source_hash: str
    byte_count: int
    source_version: str
    json_kind: str
    issue: str

    @property
    def importable(self) -> bool:
        return self.status == STATUS_VALID_JSON

    def to_manifest_entry(self) -> Dict[str, Any]:
        """Return portable metadata without leaking machine-specific paths."""
        return {
            "path": self.canonical_path,
            "source_type": self.source_type,
            "required": self.required,
            "allow_empty": self.allow_empty,
            "status": self.status,
            "source_hash": self.source_hash,
            "byte_count": self.byte_count,
            "source_version": self.source_version,
            "json_kind": self.json_kind,
            "issue": self.issue,
        }


@dataclass(frozen=True)
class LegacySourceManifest:
    sources: Tuple[LegacySourceSnapshot, ...]
    unexpected_json_paths: Tuple[str, ...]
    manifest_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest_version": MANIFEST_VERSION,
            "manifest_hash": self.manifest_hash,
            "sources": [source.to_manifest_entry() for source in self.sources],
            "unexpected_json_paths": list(self.unexpected_json_paths),
        }


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_kind(value: Any) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "scalar"


def _source_version(value: Any) -> str:
    if not isinstance(value, dict) or "version" not in value:
        return ""

    version = value.get("version")
    if version is None or isinstance(version, (dict, list)):
        return ""
    if isinstance(version, bool):
        return "true" if version else "false"
    return str(version)


def _scan_one(data_directory: Path, spec: LegacySourceSpec) -> LegacySourceSnapshot:
    path = data_directory / spec.filename

    if path.is_symlink():
        return LegacySourceSnapshot(
            physical_path=path,
            canonical_path=spec.canonical_path,
            source_type=spec.source_type,
            required=spec.required,
            allow_empty=spec.allow_empty,
            status=STATUS_SYMLINK,
            source_hash="",
            byte_count=0,
            source_version="",
            json_kind="",
            issue="legacy source is a symlink and was not followed",
        )

    if not path.exists():
        issue = (
            "required legacy source is missing"
            if spec.required
            else "optional legacy source is absent"
        )
        return LegacySourceSnapshot(
            physical_path=path,
            canonical_path=spec.canonical_path,
            source_type=spec.source_type,
            required=spec.required,
            allow_empty=spec.allow_empty,
            status=STATUS_MISSING,
            source_hash="",
            byte_count=0,
            source_version="",
            json_kind="",
            issue=issue,
        )

    if not path.is_file():
        return LegacySourceSnapshot(
            physical_path=path,
            canonical_path=spec.canonical_path,
            source_type=spec.source_type,
            required=spec.required,
            allow_empty=spec.allow_empty,
            status=STATUS_NOT_FILE,
            source_hash="",
            byte_count=0,
            source_version="",
            json_kind="",
            issue="legacy source exists but is not a regular file",
        )

    raw = path.read_bytes()
    digest = _sha256(raw)

    if not raw:
        issue = "" if spec.allow_empty else "legacy source is unexpectedly empty"
        return LegacySourceSnapshot(
            physical_path=path,
            canonical_path=spec.canonical_path,
            source_type=spec.source_type,
            required=spec.required,
            allow_empty=spec.allow_empty,
            status=STATUS_EMPTY,
            source_hash=digest,
            byte_count=0,
            source_version="",
            json_kind="empty",
            issue=issue,
        )

    try:
        decoded = raw.decode("utf-8-sig")
        parsed = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return LegacySourceSnapshot(
            physical_path=path,
            canonical_path=spec.canonical_path,
            source_type=spec.source_type,
            required=spec.required,
            allow_empty=spec.allow_empty,
            status=STATUS_INVALID_JSON,
            source_hash=digest,
            byte_count=len(raw),
            source_version="",
            json_kind="invalid",
            issue="{}: {}".format(type(exc).__name__, str(exc)),
        )

    return LegacySourceSnapshot(
        physical_path=path,
        canonical_path=spec.canonical_path,
        source_type=spec.source_type,
        required=spec.required,
        allow_empty=spec.allow_empty,
        status=STATUS_VALID_JSON,
        source_hash=digest,
        byte_count=len(raw),
        source_version=_source_version(parsed),
        json_kind=_json_kind(parsed),
        issue="",
    )


def _manifest_payload(
    sources: Iterable[LegacySourceSnapshot],
    unexpected_json_paths: Iterable[str],
) -> Dict[str, Any]:
    return {
        "manifest_version": MANIFEST_VERSION,
        "sources": [source.to_manifest_entry() for source in sources],
        "unexpected_json_paths": list(unexpected_json_paths),
    }


def _manifest_hash(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256(encoded)


def scan_legacy_sources(
    data_directory: PathLike,
    *,
    specs: Tuple[LegacySourceSpec, ...] = LEGACY_SOURCE_SPECS,
) -> LegacySourceManifest:
    """Build a deterministic, read-only manifest of expected legacy stores."""
    root = Path(data_directory)

    if root.exists() and not root.is_dir():
        raise NotADirectoryError(str(root))

    sources = tuple(_scan_one(root, spec) for spec in specs)
    expected_names = {spec.filename for spec in specs}

    unexpected = (
        tuple(
            "data/{}".format(path.name)
            for path in sorted(root.glob("*.json"), key=lambda item: item.name.lower())
            if path.name not in expected_names and path.is_file()
        )
        if root.is_dir()
        else ()
    )

    payload = _manifest_payload(sources, unexpected)
    return LegacySourceManifest(
        sources=sources,
        unexpected_json_paths=unexpected,
        manifest_hash=_manifest_hash(payload),
    )
