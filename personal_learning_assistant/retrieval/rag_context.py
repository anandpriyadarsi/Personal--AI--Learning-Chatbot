"""Source-grounded RAG context assembly. No LLM call occurs here."""

from __future__ import annotations

import json

from personal_learning_assistant.domain.retrieval_models import RAGContext


def _source_label(hit, number):
    locator = dict(hit.locator or {})
    parts = ["S{}".format(number)]
    if locator.get("lecture_number"):
        parts.append("MIT L{}".format(locator["lecture_number"]))
    if hit.page_number is not None:
        parts.append("p.{}".format(hit.page_number))
    if locator.get("section"):
        parts.append(str(locator["section"]))
    return " | ".join(parts)


def assemble_context(query, hits, *, max_chars=12000):
    blocks = []
    accepted = []
    total = 0
    for number, hit in enumerate(hits, 1):
        label = _source_label(hit, number)
        locator_json = json.dumps(
            hit.locator,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        block = "[{}]\nchunk_id={}\ndocument_id={}\nlocator={}\n{}".format(
            label,
            hit.chunk_id,
            hit.document_id,
            locator_json,
            hit.text.strip(),
        )
        extra = len(block) + (2 if blocks else 0)
        if blocks and total + extra > int(max_chars):
            break
        if not blocks and len(block) > int(max_chars):
            block = block[: int(max_chars)]
            extra = len(block)
        blocks.append(block)
        accepted.append(hit)
        total += extra

    context = "\n\n".join(blocks)
    return RAGContext(
        query=str(query),
        context_text=context,
        hits=tuple(accepted),
        total_characters=len(context),
        source_count=len(accepted),
    )
