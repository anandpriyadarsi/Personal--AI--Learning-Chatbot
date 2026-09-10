import os

from knowledge import BASE_DIR, retrieve_best_chunks
from semantic_retrieval import load_semantic_index, semantic_search

KEYWORD_TOP_K = 10
SEMANTIC_TOP_K = 10
FINAL_TOP_K = 5
RRF_K = 60


def make_result_key(file_path, text):
    normalized_text = " ".join(text.split())
    return (file_path, normalized_text)


def reciprocal_rank_score(rank):
    return 1 / (RRF_K + rank)


def looks_like_toc_or_index(text):
    text_lower = text.lower()
    toc_markers = [
        "table of contents",
        "contents",
        "chapter",
        "page",
        "scope boundary",
    ]

    dotted_lines = text.count("....") + text.count(" . . . ")
    marker_hits = sum(1 for marker in toc_markers if marker in text_lower)

    return dotted_lines >= 2 or marker_hits >= 3


def hybrid_search(query, semantic_chunks, final_top_k=FINAL_TOP_K):
    keyword_results = retrieve_best_chunks(query, top_k=KEYWORD_TOP_K)
    semantic_results = semantic_search(query, semantic_chunks, top_k=SEMANTIC_TOP_K)

    combined = {}

    for rank, result in enumerate(keyword_results, start=1):
        key = make_result_key(result["file"], result["text"])

        if key not in combined:
            combined[key] = {
                "file": result["file"],
                "text": result["text"],
                "page": result.get("page"),
                "keyword_score": None,
                "semantic_score": None,
                "keyword_rank": None,
                "semantic_rank": None,
                "hybrid_score": 0.0,
            }

        combined[key]["keyword_score"] = result["score"]
        combined[key]["keyword_rank"] = rank
        combined[key]["hybrid_score"] += reciprocal_rank_score(rank)

    for rank, result in enumerate(semantic_results, start=1):
        key = make_result_key(result["file"], result["text"])

        if key not in combined:
            combined[key] = {
                "file": result["file"],
                "text": result["text"],
                "page": None,
                "keyword_score": None,
                "semantic_score": None,
                "keyword_rank": None,
                "semantic_rank": None,
                "hybrid_score": 0.0,
            }

        combined[key]["semantic_score"] = result["score"]
        combined[key]["semantic_rank"] = rank
        combined[key]["hybrid_score"] += reciprocal_rank_score(rank)

    for result in combined.values():
        if result["keyword_rank"] is not None and result["semantic_rank"] is not None:
            result["hybrid_score"] += 0.02

        if looks_like_toc_or_index(result["text"]):
            result["hybrid_score"] *= 0.65

    ranked_results = sorted(
        combined.values(),
        key=lambda item: item["hybrid_score"],
        reverse=True,
    )

    return ranked_results[:final_top_k]


def show_hybrid_results(query, semantic_chunks):
    results = hybrid_search(query, semantic_chunks, final_top_k=FINAL_TOP_K)

    if not results:
        print(f'\nNo relevant information found for "{query}".')
        return

    print("\n========== HYBRID RETRIEVAL V3.5 ==========")
    print("\nCombining keyword + semantic retrieval...")

    for number, result in enumerate(results, start=1):
        relative_path = os.path.relpath(result["file"], BASE_DIR)

        print("\n" + "=" * 72)
        print(f"Result {number}")
        print(f"Source        : {relative_path}")

        if result["page"] is not None:
            print(f"Page          : {result['page']}")

        if result["keyword_rank"] is not None:
            print(f"Keyword rank  : {result['keyword_rank']}")

        if result["semantic_rank"] is not None:
            print(f"Semantic rank : {result['semantic_rank']}")

        if result["semantic_score"] is not None:
            print(f"Similarity    : {result['semantic_score']:.3f}")

        print(f"Hybrid score  : {result['hybrid_score']:.4f}")
        print("=" * 72)
        print(result["text"])
        print("-" * 72)


def hybrid_search_loop(semantic_chunks):
    while True:
        query = input("\nAsk something (or type back): ").strip()

        if query.lower() == "back":
            break

        if not query:
            continue

        show_hybrid_results(query, semantic_chunks)


def main():
    print("\n========== HYBRID RETRIEVAL V3.5 ==========")
    print("\nLoading saved semantic index...")

    semantic_chunks = load_semantic_index()

    if semantic_chunks is None:
        print("\nNo saved semantic index found.")
        print("Run semantic_retrieval.py and build the index first.")
        return

    print("\nHybrid retrieval is ready.")
    print("\nV2 keyword retrieval + V3 semantic retrieval")

    hybrid_search_loop(semantic_chunks)


if __name__ == "__main__":
    main()
