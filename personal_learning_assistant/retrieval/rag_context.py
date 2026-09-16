"""Source-grounded RAG context assembly. No LLM call occurs here.

The full locator remains available on RetrievalHit. The assembled prompt context
uses a compact provenance projection so retrieval evidence is readable and the
context budget is spent on knowledge text rather than repeated metadata.
"""

from __future__ import annotations

from personal_learning_assistant.domain.retrieval_models import RAGContext


def _source_label(hit, number):
    locator = dict(hit.locator or {})
    parts = ["S{}".format(number)]
    if locator.get("lecture_number"):
        parts.append("MIT L{}".format(locator["lecture_number"]))
    if hit.page_number is not None:
        parts.append("p.{}".format(hit.page_number))
    if locator.get("topic"):
        parts.append(str(locator["topic"]))
    elif locator.get("section"):
        parts.append(str(locator["section"]))
    return " | ".join(parts)


def _text(value):
    return str(value).strip() if value is not None else ""


def _compact_provenance(hit):
    locator = dict(hit.locator or {})
    source = locator.get("source")
    source = source if isinstance(source, dict) else {}

    lines = [
        "chunk_id={}".format(hit.chunk_id),
        "document_id={}".format(hit.document_id),
    ]

    for key, label in (
        ("package_chunk_id", "package_chunk_id"),
        ("lecture_title", "lecture_title"),
        ("topic", "topic"),
        ("source_url", "source_url"),
    ):
        value = _text(locator.get(key))
        if value:
            lines.append("{}={}".format(label, value))

    provider = _text(source.get("provider"))
    if provider:
        lines.append("source_provider={}".format(provider))
    kind = _text(source.get("kind"))
    if kind:
        lines.append("source_kind={}".format(kind))

    local_topics = tuple(str(item) for item in locator.get("local_topic_ids", ()) if str(item))
    if local_topics:
        lines.append("local_topic_ids={}".format(",".join(local_topics)))

    ranks = []
    if hit.lexical_rank is not None:
        ranks.append("lexical_rank={}".format(hit.lexical_rank))
    if hit.semantic_rank is not None:
        ranks.append("semantic_rank={}".format(hit.semantic_rank))
    if ranks:
        ranks.append("score={:.6f}".format(hit.score))
        lines.append("retrieval={}".format(",".join(ranks)))

    return "\n".join(lines)


def assemble_context(query, hits, *, max_chars=12000):
    blocks = []
    accepted = []
    total = 0

    for number, hit in enumerate(hits, 1):
        label = _source_label(hit, number)
        block = "[{}]\n{}\n\n{}".format(
            label,
            _compact_provenance(hit),
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
