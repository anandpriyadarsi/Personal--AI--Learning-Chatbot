import os
import pickle
import numpy as np

from fastembed import TextEmbedding

from knowledge import (
    find_documents,
    read_document,
    split_into_chunks,
    BASE_DIR
)


MODEL_NAME = "BAAI/bge-small-en-v1.5"

INDEX_DIR = os.path.join(
    BASE_DIR,
    "semantic_index"
)

INDEX_FILE = os.path.join(
    INDEX_DIR,
    "semantic_index.pkl"
)

BATCH_SIZE = 32
INDEX_VERSION = 2

embedding_model = TextEmbedding(
    model_name=MODEL_NAME
)


# --------------------------------------------------
# Similarity
# --------------------------------------------------

def cosine_similarity(
    vector_a,
    vector_b
):
    vector_a = np.asarray(
        vector_a,
        dtype=np.float32
    )

    vector_b = np.asarray(
        vector_b,
        dtype=np.float32
    )

    denominator = (
        np.linalg.norm(vector_a)
        * np.linalg.norm(vector_b)
    )

    if denominator == 0:
        return 0.0

    return float(
        np.dot(vector_a, vector_b)
        / denominator
    )


# --------------------------------------------------
# Document signatures
# --------------------------------------------------

def get_document_signature(file_path):
    """
    Detect whether a document changed without reading
    and embedding it again.
    """

    try:
        stat = os.stat(file_path)

        return {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns
        }

    except OSError:
        return None


def get_current_documents():
    """
    Return:
    {
        absolute_file_path: {
            "size": ...,
            "mtime_ns": ...
        }
    }
    """

    current = {}

    for file_path in find_documents():
        signature = get_document_signature(
            file_path
        )

        if signature is not None:
            current[file_path] = signature

    return current


# --------------------------------------------------
# Build chunks for one document
# --------------------------------------------------

def build_document_chunks(
    file_path
):
    content = read_document(
        file_path
    )

    if content.startswith("["):
        print(
            f"\nSkipped unreadable document: "
            f"{os.path.basename(file_path)}"
        )
        return []

    chunks = split_into_chunks(
        content,
        chunk_size=900
    )

    return [
        {
            "file": file_path,
            "text": chunk
        }
        for chunk in chunks
    ]


# --------------------------------------------------
# Embeddings
# --------------------------------------------------

def create_embeddings(
    chunks_data,
    label=None
):
    total = len(chunks_data)

    if total == 0:
        return chunks_data

    if label:
        print(
            f"\nEmbedding: {label}"
        )

    print(
        f"Creating embeddings for "
        f"{total} chunk(s)..."
    )

    for start in range(
        0,
        total,
        BATCH_SIZE
    ):
        end = min(
            start + BATCH_SIZE,
            total
        )

        batch_items = (
            chunks_data[start:end]
        )

        batch_texts = [
            item["text"]
            for item in batch_items
        ]

        batch_embeddings = list(
            embedding_model.embed(
                batch_texts
            )
        )

        for item, embedding in zip(
            batch_items,
            batch_embeddings
        ):
            item["embedding"] = (
                np.asarray(
                    embedding,
                    dtype=np.float32
                )
            )

        print(
            f"Embedded {end}/{total}",
            end="\r"
        )

    print(
        f"\nFinished {total} chunk(s)."
    )

    return chunks_data


# --------------------------------------------------
# Index payload
# --------------------------------------------------

def empty_index_payload():
    return {
        "index_version": INDEX_VERSION,
        "model_name": MODEL_NAME,
        "documents": {}
    }


def save_index_payload(
    payload
):
    os.makedirs(
        INDEX_DIR,
        exist_ok=True
    )

    with open(
        INDEX_FILE,
        "wb"
    ) as file:
        pickle.dump(
            payload,
            file,
            protocol=pickle.HIGHEST_PROTOCOL
        )


def read_index_payload():
    if not os.path.exists(
        INDEX_FILE
    ):
        return None

    try:
        with open(
            INDEX_FILE,
            "rb"
        ) as file:
            payload = pickle.load(
                file
            )

        if not isinstance(
            payload,
            dict
        ):
            return None

        return payload

    except (
        OSError,
        EOFError,
        pickle.UnpicklingError
    ) as error:
        print(
            f"\nCould not load "
            f"semantic index: {error}"
        )

        return None


def flatten_chunks(
    payload
):
    chunks_data = []

    documents = payload.get(
        "documents",
        {}
    )

    for document_data in (
        documents.values()
    ):
        chunks_data.extend(
            document_data.get(
                "chunks",
                []
            )
        )

    return chunks_data


# --------------------------------------------------
# Full rebuild
# --------------------------------------------------

def build_and_save_index():
    print(
        "\n========== FULL SEMANTIC INDEX BUILD =========="
    )

    current_documents = (
        get_current_documents()
    )

    if not current_documents:
        print(
            "\nNo readable documents found."
        )
        return None

    payload = (
        empty_index_payload()
    )

    total_documents = len(
        current_documents
    )

    print(
        f"\nDocuments found: "
        f"{total_documents}"
    )

    for number, (
        file_path,
        signature
    ) in enumerate(
        current_documents.items(),
        start=1
    ):
        name = os.path.basename(
            file_path
        )

        print(
            f"\n[{number}/{total_documents}] "
            f"{name}"
        )

        chunks = (
            build_document_chunks(
                file_path
            )
        )

        chunks = (
            create_embeddings(
                chunks,
                label=name
            )
        )

        payload[
            "documents"
        ][file_path] = {
            "signature": signature,
            "chunks": chunks
        }

    save_index_payload(
        payload
    )

    chunks_data = flatten_chunks(
        payload
    )

    print(
        "\nSemantic index rebuilt successfully."
    )

    print(
        f"Indexed chunks: "
        f"{len(chunks_data)}"
    )

    return chunks_data


# --------------------------------------------------
# Automatic incremental synchronization
# --------------------------------------------------

def sync_semantic_index():
    """
    Automatically:
    - reuse unchanged documents
    - embed only new/changed documents
    - remove deleted documents
    """

    current_documents = (
        get_current_documents()
    )

    if not current_documents:
        print(
            "\nNo knowledge documents found."
        )
        return None

    payload = (
        read_index_payload()
    )

    # Old V3/V3.1 index or incompatible model:
    # rebuild once into V5.1 structure.
    if (
        payload is None
        or payload.get(
            "index_version"
        ) != INDEX_VERSION
        or payload.get(
            "model_name"
        ) != MODEL_NAME
        or "documents" not in payload
    ):
        print(
            "\nSemantic index is missing "
            "or uses an older format."
        )

        print(
            "A one-time V5.1 rebuild "
            "is required."
        )

        return build_and_save_index()

    indexed_documents = payload[
        "documents"
    ]

    current_paths = set(
        current_documents
    )

    indexed_paths = set(
        indexed_documents
    )

    new_paths = (
        current_paths
        - indexed_paths
    )

    deleted_paths = (
        indexed_paths
        - current_paths
    )

    changed_paths = set()

    for file_path in (
        current_paths
        & indexed_paths
    ):
        saved_signature = (
            indexed_documents[
                file_path
            ].get(
                "signature"
            )
        )

        current_signature = (
            current_documents[
                file_path
            ]
        )

        if (
            saved_signature
            != current_signature
        ):
            changed_paths.add(
                file_path
            )

    if (
        not new_paths
        and not changed_paths
        and not deleted_paths
    ):
        chunks_data = (
            flatten_chunks(
                payload
            )
        )

        print(
            f"\nSemantic index is up to date "
            f"({len(chunks_data)} chunks)."
        )

        return chunks_data

    print(
        "\nKnowledge library changes detected."
    )

    print(
        f"New: {len(new_paths)} | "
        f"Changed: {len(changed_paths)} | "
        f"Deleted: {len(deleted_paths)}"
    )

    # Remove deleted documents
    for file_path in deleted_paths:
        indexed_documents.pop(
            file_path,
            None
        )

        print(
            f"Removed from index: "
            f"{os.path.basename(file_path)}"
        )

    # Rebuild only new/changed docs
    paths_to_update = sorted(
        new_paths
        | changed_paths
    )

    total_updates = len(
        paths_to_update
    )

    for number, file_path in enumerate(
        paths_to_update,
        start=1
    ):
        name = os.path.basename(
            file_path
        )

        print(
            f"\n[{number}/{total_updates}] "
            f"Updating {name}"
        )

        chunks = (
            build_document_chunks(
                file_path
            )
        )

        chunks = (
            create_embeddings(
                chunks,
                label=name
            )
        )

        indexed_documents[
            file_path
        ] = {
            "signature": (
                current_documents[
                    file_path
                ]
            ),
            "chunks": chunks
        }

    payload[
        "index_version"
    ] = INDEX_VERSION

    payload[
        "model_name"
    ] = MODEL_NAME

    save_index_payload(
        payload
    )

    chunks_data = (
        flatten_chunks(
            payload
        )
    )

    print(
        "\nAutomatic re-indexing complete."
    )

    print(
        f"Indexed chunks: "
        f"{len(chunks_data)}"
    )

    return chunks_data


# --------------------------------------------------
# Public loader used by RAG / Hybrid Retrieval
# --------------------------------------------------

def load_semantic_index():
    """
    V5.1 behavior:
    Every time the chatbot loads the semantic index,
    check the knowledge library automatically.
    Only new/changed documents are re-embedded.
    """

    return sync_semantic_index()


# --------------------------------------------------
# Semantic search
# --------------------------------------------------

def semantic_search(
    query,
    chunks_data,
    top_k=5
):
    query_embedding = list(
        embedding_model.embed(
            [query]
        )
    )[0]

    query_embedding = np.asarray(
        query_embedding,
        dtype=np.float32
    )

    results = []

    for item in chunks_data:
        similarity = (
            cosine_similarity(
                query_embedding,
                item["embedding"]
            )
        )

        results.append({
            "file": item["file"],
            "text": item["text"],
            "score": similarity
        })

    results.sort(
        key=lambda item: item[
            "score"
        ],
        reverse=True
    )

    return results[:top_k]


def show_semantic_results(
    query,
    chunks_data
):
    results = semantic_search(
        query,
        chunks_data,
        top_k=5
    )

    print(
        "\n========== SEMANTIC SEARCH V5.1 =========="
    )

    for number, result in enumerate(
        results,
        start=1
    ):
        relative_path = os.path.relpath(
            result["file"],
            BASE_DIR
        )

        print(
            "\n" + "=" * 70
        )

        print(
            f"Result {number}"
        )

        print(
            f"Source     : "
            f"{relative_path}"
        )

        print(
            f"Similarity : "
            f"{result['score']:.3f}"
        )

        print(
            "=" * 70
        )

        print(
            result["text"]
        )

        print(
            "-" * 70
        )


def search_loop(
    chunks_data
):
    while True:
        query = input(
            "\nAsk something "
            "(or type back): "
        ).strip()

        if query.lower() == "back":
            break

        if not query:
            continue

        show_semantic_results(
            query,
            chunks_data
        )


# --------------------------------------------------
# Standalone utility menu
# --------------------------------------------------

def main():
    chunks_data = None

    while True:
        print(
            "\n========== SEMANTIC INDEX V5.1 =========="
        )

        print(
            "1. Auto Sync / Load Index"
        )

        print(
            "2. Force Full Rebuild"
        )

        print(
            "3. Search Semantic Knowledge"
        )

        print(
            "4. Exit"
        )

        choice = input(
            "\nEnter your choice: "
        ).strip()

        if choice == "1":
            chunks_data = (
                sync_semantic_index()
            )

        elif choice == "2":
            chunks_data = (
                build_and_save_index()
            )

        elif choice == "3":
            if chunks_data is None:
                chunks_data = (
                    sync_semantic_index()
                )

            if chunks_data is None:
                continue

            search_loop(
                chunks_data
            )

        elif choice == "4":
            print(
                "\nExiting Semantic Index."
            )
            break

        else:
            print(
                "\nInvalid choice. "
                "Please enter 1 to 4."
            )


if __name__ == "__main__":
    main()
