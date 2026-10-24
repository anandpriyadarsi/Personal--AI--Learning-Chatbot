"""Safe, device-local adapter for the UC103N Vedic Schools Work distribution.

The uploaded ZIP is always treated as inert *data*: Python in its tools/
directory is never imported, run or extracted. Registration must exist in
this exact Android private source registry before an authored module can be
staged. This is intentionally a narrow importer for the verified Work format,
not a generic converter for arbitrary PDF/ZIP inputs.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
from urllib.parse import quote
import zipfile

from .archive import decode_bundle, decode_json, read_zip
from .authoring import preflight
from .coverage import build_coverage, block_text, digest, normalized, validate_coverage
from .sources import RegisteredSources
from .validation import require

SOURCE_SHA = "5454ccc3e1d9410be85dbb9de926106ae04b2da8fab1ef8fad71b3a5f2f027b7"
TEMPLATE = "canonical_templates/module.v2.UNBOUND-NOT-IMPORTABLE.json"
ORIGINAL = "sources/Vedic_Schools_Source.pdf"
DIAGRAMS = "metadata/diagram_specs.json"
CANDIDATES = "metadata/source_location_candidates.json"
REQUIRED = (TEMPLATE, ORIGINAL, DIAGRAMS, CANDIDATES)
EVIDENCE_PAGES = (3, 5, 8, 9, 10, 14, 15, 19, 21, 22)


def is_vedic_authoring_archive(files):
    return TEMPLATE in files


def _json_bytes(obj):
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def _registered_source(source, *, database, roots, requested_id):
    """Find an *existing* exact-byte PDF in the app's actual registry."""
    db_path = Path(database).resolve()
    digest = hashlib.sha256(source).hexdigest()
    require(digest == SOURCE_SHA, "Vedic Work ZIP does not contain the exact original professor PDF.")
    with closing(sqlite3.connect(
        "file:" + quote(db_path.as_posix(), safe="/:") + "?mode=ro", uri=True
    )) as conn:
        matches = [
            row[0] for row in conn.execute(
                "SELECT id FROM knowledge_documents WHERE content_hash=? "
                "AND mime_type='application/pdf' ORDER BY id",
                (digest,),
            ).fetchall()
        ]
    requested_id = str(requested_id or "").strip()
    if requested_id:
        require(requested_id in matches,
                "The selected source ID is not registered for this original professor PDF.")
        source_id = requested_id
    else:
        require(len(matches) == 1,
                "Upload the original professor PDF to Library first. If several identical "
                "registered sources exist, enter the exact source ID displayed by Library.")
        source_id = matches[0]
    require(RegisteredSources(db_path, roots)(source_id) == source,
            "Registered PDF bytes differ from the uploaded original. No study content was imported.")
    return source_id


def _coverage(module, source, assets, diagram_specs, source_candidates):
    result = build_coverage(
        module, source, reviewer="Alex automated exact-revision inventory",
        method=("Fresh original text inventory; source location candidates revalidated "
                "against the original PDF and current teaching quotes. Unresolved "
                "historical and instructor claims remain flagged."),
    )
    require(source_candidates.get("source_sha256") == hashlib.sha256(source).hexdigest(),
            "Source-location candidates were prepared against a different PDF.")
    prior = {entry["element_id"]: entry for entry in source_candidates["candidates"]}
    fresh = {entry["id"]: entry for entry in result["inventory"]}
    sections = {section["id"]: section for section in module["sections"]}
    for entry in result["coverage"]:
        if entry["state"] == "mapped":
            continue
        candidate = prior.get(entry["element_id"])
        if candidate is None:
            continue
        element = fresh[entry["element_id"]]
        require(
            candidate["page"] == element["page"] and
            normalized(candidate["text"]) == normalized(element["text"]),
            "Source location candidate is stale; review the actual professor PDF.",
        )
        review = candidate["review"]
        if review["state"] == "excluded":
            require(element["page"] == 1 and not review["mappings"],
                    "Only title-page metadata may be excluded.")
            entry.update(state="excluded", reason=review["reason"], mappings=[])
            continue
        for target in review["mappings"]:
            section = sections.get(target["section_id"])
            require(section is not None and
                    0 <= target["block_index"] < len(section["blocks"]),
                    "Learning block referenced by source review is unavailable.")
            block = section["blocks"][target["block_index"]]
            require(element["page"] in block["pages"] and
                    target["quote"] in block_text(block),
                    "Learning block no longer supports the quoted source location.")
        entry.update(state="mapped", mappings=review["mappings"])
        entry.pop("reason", None)

    result["review"]["reviewed_at"] = "2026-10-24T00:00:00+00:00"
    require(len(diagram_specs) == len(EVIDENCE_PAGES),
            "Vedic Work diagram inventory differs from the reviewed package.")
    for spec, page in zip(diagram_specs, EVIDENCE_PAGES):
        section = next((s for s in module["sections"] if s["id"] == spec["topic_id"]), None)
        require(section is not None, "Vedic diagram topic is unavailable.")
        index = next((i for i, block in enumerate(section["blocks"])
                      if block["kind"] == "graph"), None)
        require(index is not None, "Vedic diagram teaching block is missing.")
        graph = section["blocks"][index]
        preview = module["pages"][page - 1]["preview"]
        require(preview in assets, "Reviewed source-page preview is missing.")
        result["inventory"].append({
            "id": "visual-" + spec["id"], "page": page,
            "kind": "diagram_relationship", "text": spec["alt"],
            "locator": {"rect": [0, 0, 960, 540]},
            "visual_evidence": {
                "reviewer": "Alex source comparison 2026-10-24",
                "method": ("Source preview versus authored graph labels and edges. "
                           "Teaching map, not verbatim transcription."),
                "preview_sha256": hashlib.sha256(assets[preview]).hexdigest(),
            },
        })
        result["coverage"].append({
            "element_id": "visual-" + spec["id"],
            "state": "mapped",
            "mappings": [{
                "section_id": section["id"],
                "block_index": index, "quote": graph["alt"],
            }],
        })
        require(graph["alt"] in block_text(graph),
                "Vedic diagram no longer matches authored teaching content.")
    result["review"]["inventory_digest"] = digest(result["inventory"])
    for page in (10, 17, 19, 20):
        item = module["pages"][page - 1]
        result["unresolved"].append({
            "id": "source-issue-p" + str(page), "pages": [page],
            "snippet": item["text"][:400],
            "issue": " ".join(item["review_flags"]),
            "next_action": ("Ask the instructor to clarify; preserve the original "
                            "and do not treat the disputed claim as settled."),
        })
    return validate_coverage(result, module, source, assets)


def bind_vedic_work_zip(raw, *, database, roots, requested_source_id=""):
    """Validate a portable Work ZIP and produce a staged-ready canonical bundle.

    Does not write to the registry, modify courses, publish or execute ZIP tools.
    The caller owns the standard Learning Studio stage/review/publish path.
    """
    files = read_zip(raw, pilot=True)
    require(all(item in files for item in REQUIRED),
            "Vedic Work ZIP is incomplete; original PDF or module template is missing.")
    module = decode_json(files[TEMPLATE])
    require(module.get("schema") == "anvaya.learning-module.v2" and
            module.get("source", {}).get("source_id") is None,
            "Only an unbound V2 authored Work template can use source binding.")
    source_info = module["source"]
    require(source_info.get("sha256") == SOURCE_SHA and
            source_info.get("page_count") == 23,
            "This package must reference the original 23-page professor PDF.")
    source = files[ORIGINAL]
    require(source.startswith(b"%PDF-") and len(source) <= 20_000_000,
            "The original Vedic PDF is invalid or oversized.")
    source_id = _registered_source(
        source, database=database, roots=roots, requested_id=requested_source_id
    )
    module["source"]["source_id"] = source_id
    module = decode_json(_json_bytes(module))
    assets = {
        name: data for name, data in files.items()
        if name.startswith("assets/") and
        len(name.split("/")) == 2 and
        Path(name).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
    }
    require(assets and len(assets) <= 100, "Vedic Work raster assets are missing or excessive.")
    require(all(len(data) <= 2_000_000 for data in assets.values()),
            "A Vedic Work raster asset exceeds 2 MB.")
    specs = json.loads(files[DIAGRAMS].decode("utf-8"))
    require(isinstance(specs, list), "Vedic Work diagram inventory is invalid.")
    candidates = decode_json(files[CANDIDATES])
    coverage = _coverage(module, source, assets, specs, candidates)
    report = preflight(module, source, assets, {"available": False, "courses": []},
                       source_id=source_id, coverage=coverage)
    require(report["valid"], "Vedic source-bound learning package failed canonical preflight.")
    # Also verify the exact serialized canonical ZIP accepted by the normal importer.
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, contents in sorted({
            "module.json": _json_bytes(module),
            "coverage.json": _json_bytes(coverage),
            **assets,
        }.items()):
            z.writestr(name, contents)
    parsed, parsed_assets, parsed_coverage = decode_bundle(stream.getvalue(), "module.zip")
    require(parsed == module and parsed_assets == assets and parsed_coverage == coverage,
            "Canonical Vedic ZIP roundtrip did not match the reviewed input.")
    require(RegisteredSources(database, roots)(source_id) == source,
            "Registered original PDF changed during source binding; retry.")
    return parsed, parsed_assets, parsed_coverage
