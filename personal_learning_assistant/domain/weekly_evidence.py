"""Honest operational evidence; effort and completion never imply mastery."""
from dataclasses import asdict, dataclass
from typing import Any

POLICY_VERSION = 'pao-weekly-v1'

@dataclass(frozen=True)
class Metric:
    value: Any
    unit: str
    status: str
    scope: dict
    as_of: str
    numerator: int | None = None
    denominator: int | None = None
    source_refs: tuple = ()
    policy_version: str = POLICY_VERSION
    exclusions: tuple = ()

    def to_dict(self):
        return asdict(self)
