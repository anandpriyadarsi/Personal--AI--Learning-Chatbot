"""Frozen redacted B3 authority observations; never deployment authorization."""
from dataclasses import dataclass
from enum import StrEnum


class AuthorityStatus(StrEnum):
    PASS = 'PASS'
    BLOCKED = 'BLOCKED'
    INVALID = 'INVALID'
    UNVERIFIABLE = 'UNVERIFIABLE'


@dataclass(frozen=True)
class ProjectionInspection:
    store: str
    version: int | None
    structure_status: AuthorityStatus
    identity_status: AuthorityStatus
    freshness_status: AuthorityStatus
    identity_mismatches: int | None = None
    watermark_available: bool = False
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class B3AuthorityManifest:
    backend: str
    control_status: AuthorityStatus
    ledger_status: AuthorityStatus
    ledger: tuple[tuple[int, str, str], ...]
    schema_status: AuthorityStatus
    schema_sha256: str
    foreign_key_schema_sha256: str
    missing_tables: tuple[str, ...]
    integrity_ok: bool
    foreign_key_violations: int
    identity_status: AuthorityStatus
    identity_anomalies: tuple[tuple[str, int | None], ...]
    relationship_counts: tuple[tuple[str, int], ...]
    projections: tuple[ProjectionInspection, ...]
    total_changes: int
    mapping_snapshot_status: AuthorityStatus = AuthorityStatus.UNVERIFIABLE
    independence_snapshot_status: AuthorityStatus = AuthorityStatus.UNVERIFIABLE
    production_authority: AuthorityStatus = AuthorityStatus.BLOCKED
    contract_version: str = 'anvaya.b3-authority.v1'
    warnings: tuple[str, ...] = ('historical_attribution_unavailable', 'projection_watermark_unavailable')
