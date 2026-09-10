import os
import pickle
import numpy as np

from fastembed import TextEmbedding
from knowledge import find_documents, read_document, split_into_chunks, BASE_DIR

MODEL_NAME = "BAAI/bge-small-en-v1.5"
INDEX_DIR = os.path.join(BASE_DIR, "semantic_index")
INDEX_FILE = os.path.join(INDEX_DIR, "semantic_index.pkl")
BATCH_SIZE = 32

embedding_model = TextEmbedding(model_name=MODEL_NAME)

def cosine_similarity(vector_a, vector_b):
    vector_a = np.array(vector_a)
    vector_b = np.array(vector_b)
    denominator = np.linalg.norm(vector_a) * np.linalg.norm(vector_b)
    if denominator == 0:
        return 0.0
    return float(np.dot(vector_a, vector_b) / denominator)

def build_semantic_chunks():
    documents = find_documents()
    chunks_data = []
    print(f"\nScanning {len(documents)} document(s)...")
    for file_path in documents:
        content = read_document(file_path)
        if content.startswith("["):
            continue
        chunks = split_into_chunks(content, chunk_size=900)
        for chunk in chunks:
            chunks_data.append({"file": file_path, "text": chunk})
    print(f"Prepared {len(chunks_data)} chunk(s).")
    return chunks_data

def create_embeddings(chunks_data):
    total = len(chunks_data)
    print(f"\nCreating embeddings in batches of {BATCH_SIZE}...")
    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)
        batch_items = chunks_data[start:end]
        batch_texts = [item["text"] for item in batch_items]
        batch_embeddings = list(embedding_model.embed(batch_texts))
        for item, embedding in zip(batch_items, batch_embeddings):
            item["embedding"] = np.asarray(embedding, dtype=np.float32)
        print(f"Embedded {end}/{total} chunks", end="\r")
    print(f"\nFinished embedding {total} chunks.")
    return chunks_data

def save_semantic_index(chunks_data):
    os.makedirs(INDEX_DIR, exist_ok=True)
    payload = {"model_name": MODEL_NAME, "chunks": chunks_data}
    with open(INDEX_FILE, "wb") as file:
        pickle.dump(payload, file, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"\nSemantic index saved to:\n{INDEX_FILE}")

def load_semantic_index():
    if not os.path.exists(INDEX_FILE):
        return None
    try:
        with open(INDEX_FILE, "rb") as file:
            payload = pickle.load(file)
        if payload.get("model_name") != MODEL_NAME:
            print("\nSaved index uses a different embedding model.")
            print("Please rebuild the semantic index.")
            return None
        chunks_data = payload.get("chunks", [])
        if not chunks_data:
            return None
        print(f"\nLoaded semantic index with {len(chunks_data)} chunks.")
        return chunks_data
    except (OSError, EOFError, pickle.UnpicklingError) as error:
        print(f"\nCould not load semantic index: {error}")
        return None

def build_and_save_index():
    print("\n========== BUILD SEMANTIC INDEX ==========")
    chunks_data = build_semantic_chunks()
    if not chunks_data:
        print("\nNo readable documents found.")
        return None
    chunks_data = create_embeddings(chunks_data)
    save_semantic_index(chunks_data)
    print("\nSemantic knowledge index ready.")
    return chunks_data

def semantic_search(query, chunks_data, top_k=5):
    query_embedding = list(embedding_model.embed([query]))[0]
    query_embedding = np.asarray(query_embedding, dtype=np.float32)
    results = []
    for item in chunks_data:
        similarity = cosine_similarity(query_embedding, item["embedding"])
        results.append({"file": item["file"], "text": item["text"], "score": similarity})
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:top_k]

def show_semantic_results(query, chunks_data):
    results = semantic_search(query, chunks_data, top_k=5)
    print("\n========== SEMANTIC SEARCH V3.1 ==========")
    for number, result in enumerate(results, start=1):
        relative_path = os.path.relpath(result["file"], BASE_DIR)
        print("\n" + "=" * 70)
        print(f"Result {number}")
        print(f"Source     : {relative_path}")
        print(f"Similarity : {result['score']:.3f}")
        print("=" * 70)
        print(result["text"])
        print("-" * 70)

def search_loop(chunks_data):
    while True:
        query = input("\nAsk something (or type back): ").strip()
        if query.lower() == "back":
            break
        if not query:
            continue
        show_semantic_results(query, chunks_data)

def main():
    chunks_data = None
    while True:
        print("\n========== SEMANTIC RETRIEVAL V3.1 ==========")
        print("1. Load Saved Semantic Index")
        print("2. Build / Rebuild Semantic Index")
        print("3. Search Semantic Knowledge")
        print("4. Exit")
        choice = input("\nEnter your choice: ").strip()
        if choice == "1":
            chunks_data = load_semantic_index()
            if chunks_data is None:
                print("\nNo valid saved semantic index found.")
                print("Choose option 2 to build one.")
        elif choice == "2":
            chunks_data = build_and_save_index()
        elif choice == "3":
            if chunks_data is None:
                chunks_data = load_semantic_index()
            if chunks_data is None:
                print("\nNo semantic index is available.")
                print("Choose option 2 first.")
                continue
            search_loop(chunks_data)
        elif choice == "4":
            print("\nExiting Semantic Retrieval.")
            break
        else:
            print("\nInvalid choice. Please enter 1, 2, 3, or 4.")

if __name__ == "__main__":
    main()
