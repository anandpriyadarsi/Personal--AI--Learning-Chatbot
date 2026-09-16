"""Static Canonical Runtime + Consumer Inventory for Phase 7.1."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from personal_learning_assistant.phase7.canonical_runtime_catalog import (
    KNOWN_CANDIDATES,
    CandidateSpec,
    family_candidate,
)


_ALLOWED_STATUSES = {
    "active_consumer",
    "compatibility_required",
    "observation_required",
    "archive_candidate",
    "retirement_candidate",
    "permanent_source_evidence",
    "derived_disposable",
    "unknown",
}

_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".phase5_retrieval",
    ".phase7",
    "node_modules",
}

_DATA_LITERAL_RE = re.compile(
    r"""(?ix)
    (?:
        [A-Za-z0-9_.\\/\-]+
        (?:
            \.json|\.(?:sqlite|sqlite3|db)|\.md|\.txt|\.pdf|\.pptx|\.srt|\.vtt
        )
    )
    """
)

_WRITE_METHODS = {
    "write_text",
    "write_bytes",
    "write",
    "writelines",
    "dump",
    "dumps",
    "replace",
    "rename",
    "unlink",
    "mkdir",
    "touch",
}
_READ_METHODS = {
    "read_text",
    "read_bytes",
    "read",
    "readlines",
    "load",
    "loads",
    "exists",
    "is_file",
}


@dataclass(frozen=True)
class SourceFacts:
    path: str
    module: str
    imports: Tuple[str, ...]
    dynamic_imports: Tuple[str, ...]
    feature_targets: Tuple[str, ...]
    data_literals: Tuple[str, ...]
    read_signal_count: int
    write_signal_count: int
    parse_error: str = ""


@dataclass(frozen=True)
class InventoryItem:
    path: str
    module: str
    component_kind: str
    replacement: str
    status: str
    policy: str
    note: str
    runtime_consumers: Tuple[str, ...]
    test_consumers: Tuple[str, ...]
    dynamic_menu_consumers: Tuple[str, ...]
    data_literals: Tuple[str, ...]
    read_signal_count: int
    write_signal_count: int
    parse_error: str


def _module_name(root: Path, path: Path) -> str:
    rel = path.relative_to(root).as_posix()
    if rel.endswith("/__init__.py"):
        rel = rel[: -len("/__init__.py")]
    elif rel.endswith(".py"):
        rel = rel[:-3]
    return rel.replace("/", ".")


def _iter_python_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            continue
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        yield path


def _resolve_relative(module: str, current_module: str, level: int) -> str:
    if level <= 0:
        return module
    parts = current_module.split(".")
    if current_module.endswith(".__init__"):
        parts = parts[:-1]
    base = parts[:-level] if level <= len(parts) else []
    if module:
        base.extend(module.split("."))
    return ".".join(part for part in base if part)


class _FactVisitor(ast.NodeVisitor):
    def __init__(self, current_module: str):
        self.current_module = current_module
        self.imports: Set[str] = set()
        self.dynamic_imports: Set[str] = set()
        self.feature_targets: Set[str] = set()
        self.read_signal_count = 0
        self.write_signal_count = 0

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = _resolve_relative(
            node.module or "",
            self.current_module,
            int(node.level or 0),
        )
        if module:
            self.imports.add(module)
        self.generic_visit(node)

    def visit_Call(self, node):
        name = ""
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr

        if name in {"import_module", "__import__"} and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                self.dynamic_imports.add(first.value)

        if name in _WRITE_METHODS:
            self.write_signal_count += 1
        if name in _READ_METHODS:
            self.read_signal_count += 1

        if name == "open":
            mode = None
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                mode = node.args[1].value
            for keyword in node.keywords:
                if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                    mode = keyword.value.value
            if isinstance(mode, str) and any(flag in mode for flag in ("w", "a", "x", "+")):
                self.write_signal_count += 1
            else:
                self.read_signal_count += 1
        self.generic_visit(node)

    def visit_Assign(self, node):
        # main.py keeps dynamic feature modules in FEATURE_ACTIONS.  These are
        # runtime consumers even though there is no normal import statement.
        target_names = {
            target.id
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        if "FEATURE_ACTIONS" in target_names and isinstance(node.value, ast.Dict):
            for value in node.value.values:
                if isinstance(value, (ast.Tuple, ast.List)) and value.elts:
                    first = value.elts[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        self.feature_targets.add(first.value)
        self.generic_visit(node)


def _facts_for_file(root: Path, path: Path) -> SourceFacts:
    rel = path.relative_to(root).as_posix()
    module = _module_name(root, path)
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = path.read_text(encoding="utf-8", errors="replace")

    parse_error = ""
    visitor = _FactVisitor(module)
    try:
        tree = ast.parse(raw, filename=rel)
        visitor.visit(tree)
    except SyntaxError as error:
        parse_error = "{}:{}: {}".format(
            error.__class__.__name__,
            error.lineno or 0,
            error.msg,
        )

    literals = tuple(sorted(set(_DATA_LITERAL_RE.findall(raw))))
    return SourceFacts(
        path=rel,
        module=module,
        imports=tuple(sorted(visitor.imports)),
        dynamic_imports=tuple(sorted(visitor.dynamic_imports)),
        feature_targets=tuple(sorted(visitor.feature_targets)),
        data_literals=literals,
        read_signal_count=visitor.read_signal_count,
        write_signal_count=visitor.write_signal_count,
        parse_error=parse_error,
    )


def _candidate_specs(root: Path, facts: Sequence[SourceFacts]) -> Tuple[CandidateSpec, ...]:
    by_path: Dict[str, CandidateSpec] = {
        spec.path.replace("\\", "/"): spec
        for spec in KNOWN_CANDIDATES
        if (root / spec.path).is_file()
    }
    for fact in facts:
        generated = family_candidate(fact.path)
        if generated is not None:
            by_path.setdefault(generated.path, generated)
    return tuple(by_path[path] for path in sorted(by_path))


def _matches_import(imported: str, target_module: str) -> bool:
    return (
        imported == target_module
        or imported.startswith(target_module + ".")
        or target_module.startswith(imported + ".")
    )


def _status(spec: CandidateSpec, runtime_consumers: Sequence[str]) -> str:
    if spec.policy == "permanent":
        return "permanent_source_evidence"
    if spec.policy == "derived":
        return "derived_disposable"
    if spec.policy == "compatibility":
        return "compatibility_required"
    if runtime_consumers:
        return "active_consumer"
    # Absence of a static consumer is not retirement proof.  Phase 7.4 runtime
    # observation is required before anything can become a retirement candidate.
    return "observation_required"


def build_inventory(project_root) -> dict:
    root = Path(project_root).resolve()
    facts = tuple(_facts_for_file(root, path) for path in _iter_python_files(root))
    fact_by_path = {fact.path: fact for fact in facts}

    specs = _candidate_specs(root, facts)
    items: List[InventoryItem] = []

    for spec in specs:
        target_fact = fact_by_path.get(spec.path)
        if target_fact is None:
            continue
        runtime_consumers: Set[str] = set()
        test_consumers: Set[str] = set()
        dynamic_menu_consumers: Set[str] = set()

        for consumer in facts:
            if consumer.path == spec.path:
                continue
            imported = any(
                _matches_import(name, target_fact.module)
                for name in consumer.imports + consumer.dynamic_imports
            )
            menu_target = target_fact.module in consumer.feature_targets
            if not imported and not menu_target:
                continue

            if consumer.path.startswith("tests/"):
                test_consumers.add(consumer.path)
            else:
                runtime_consumers.add(consumer.path)
            if menu_target:
                dynamic_menu_consumers.add(consumer.path)

        item_status = _status(spec, sorted(runtime_consumers))
        if item_status not in _ALLOWED_STATUSES:
            raise RuntimeError("invalid inventory status {}".format(item_status))

        items.append(
            InventoryItem(
                path=spec.path,
                module=target_fact.module,
                component_kind=spec.component_kind,
                replacement=spec.replacement,
                status=item_status,
                policy=spec.policy,
                note=spec.note,
                runtime_consumers=tuple(sorted(runtime_consumers)),
                test_consumers=tuple(sorted(test_consumers)),
                dynamic_menu_consumers=tuple(sorted(dynamic_menu_consumers)),
                data_literals=target_fact.data_literals,
                read_signal_count=target_fact.read_signal_count,
                write_signal_count=target_fact.write_signal_count,
                parse_error=target_fact.parse_error,
            )
        )

    status_counts: Dict[str, int] = {}
    kind_counts: Dict[str, int] = {}
    for item in items:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1
        kind_counts[item.component_kind] = kind_counts.get(item.component_kind, 0) + 1

    parse_errors = tuple(
        {"path": fact.path, "error": fact.parse_error}
        for fact in facts
        if fact.parse_error
    )

    payload = {
        "schema_version": 1,
        "analysis_kind": "static_consumer_inventory",
        "project_root_identity": ".",
        "canonical_runtime": {
            "structured_authority": "data/learning_assistant.db",
            "authority_control": ".phase4_authority.json",
            "note_body_authority": "configured Markdown/Obsidian vault",
            "source_authority": "registered source files",
            "retrieval_artifact": ".phase5_retrieval (derived/rebuildable)",
            "tutor_workspace": "phase6_tutor_workspace.py",
            "academic_agent": "phase6_academic_agent.py",
        },
        "limitations": (
            "Static imports/dynamic FEATURE_ACTIONS cannot prove a component unused.",
            "Runtime use via subprocess, user scripts, plugins, reflection, or external callers may be invisible.",
            "write/read signal counts are syntactic hints, not proof of authority ownership.",
            "No Phase 7.1 item is safe to delete solely because static runtime consumers are zero.",
        ),
        "summary": {
            "python_file_count": len(facts),
            "candidate_count": len(items),
            "status_counts": dict(sorted(status_counts.items())),
            "component_kind_counts": dict(sorted(kind_counts.items())),
            "parse_error_count": len(parse_errors),
            "retirement_candidate_count": sum(
                1 for item in items if item.status == "retirement_candidate"
            ),
        },
        "items": [asdict(item) for item in items],
        "parse_errors": parse_errors,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    payload["inventory_sha256"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    return payload


def render_markdown(report: dict) -> str:
    lines = [
        "# Phase 7.1 Canonical Runtime + Consumer Inventory",
        "",
        "Inventory SHA-256: `{}`".format(report["inventory_sha256"]),
        "",
        "## Summary",
        "",
        "- Python files scanned: {}".format(report["summary"]["python_file_count"]),
        "- Candidate components: {}".format(report["summary"]["candidate_count"]),
        "- Parse errors: {}".format(report["summary"]["parse_error_count"]),
        "- Static retirement candidates: {}".format(
            report["summary"]["retirement_candidate_count"]
        ),
        "",
        "> Static absence is not retirement proof. Phase 7.4 runtime observation is required.",
        "",
        "## Candidates",
        "",
        "| Component | Status | Kind | Runtime consumers | Tests | Replacement |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for item in report["items"]:
        lines.append(
            "| `{}` | `{}` | `{}` | {} | {} | {} |".format(
                item["path"],
                item["status"],
                item["component_kind"],
                len(item["runtime_consumers"]),
                len(item["test_consumers"]),
                str(item["replacement"]).replace("|", "\\|"),
            )
        )
    lines.extend(["", "## Canonical runtime", ""])
    for key, value in report["canonical_runtime"].items():
        lines.append("- **{}:** `{}`".format(key.replace("_", " "), value))
    lines.extend(["", "## Limitations", ""])
    for value in report["limitations"]:
        lines.append("- {}".format(value))
    return "\n".join(lines) + "\n"
