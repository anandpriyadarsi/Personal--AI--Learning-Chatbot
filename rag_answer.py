import os
import re
import requests

from knowledge import BASE_DIR
from semantic_retrieval import load_semantic_index
from hybrid_retrieval import hybrid_search


DEFAULT_TOP_K = 5
DEFAULT_MAX_CONTEXT_CHARS = 12000


# --------------------------------------------------
# Configuration
# --------------------------------------------------

def get_llm_config():
    api_url = os.getenv("LLM_API_URL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()

    return api_url, api_key, model


def llm_is_configured():
    api_url, api_key, model = get_llm_config()
    return bool(api_url and api_key and model)


# --------------------------------------------------
# Source helpers
# --------------------------------------------------

def extract_page_number(text):
    match = re.search(r"--- Page (\d+) ---", text)

    if match:
        return int(match.group(1))

    return None


def make_source_label(result):
    relative_path = os.path.relpath(
        result["file"],
        BASE_DIR
    )

    page = result.get("page")

    if page is None:
        page = extract_page_number(
            result["text"]
        )

    if page is not None:
        return f"{relative_path} | page {page}"

    return relative_path


# --------------------------------------------------
# Build RAG context
# --------------------------------------------------

def build_context(results, max_chars=DEFAULT_MAX_CONTEXT_CHARS):
    context_parts = []
    used_chars = 0

    for number, result in enumerate(results, start=1):
        source = make_source_label(result)

        block = (
            f"[SOURCE {number}]\n"
            f"{source}\n\n"
            f"{result['text'].strip()}\n"
        )

        if used_chars + len(block) > max_chars:
            remaining = max_chars - used_chars

            if remaining > 300:
                context_parts.append(
                    block[:remaining]
                )

            break

        context_parts.append(block)
        used_chars += len(block)

    return "\n\n".join(context_parts)


# --------------------------------------------------
# Prompt
# --------------------------------------------------

def build_messages(question, context):
    system_message = (
        "You are Anand's personal academic learning assistant. "
        "Answer using ONLY the supplied academic context. "
        "Do not invent facts that are not supported by the context. "
        "If the context is insufficient, clearly say what is missing. "
        "Use simple, clear English. "
        "Teach with intuition first, then mathematics or technical detail. "
        "When useful, give step-by-step guidance. "
        "Do not claim that you read a source that is not in the context. "
        "At the end, include a short 'Sources used' section using the "
        "source labels supplied in the context."
    )

    user_message = (
        f"QUESTION:\n{question}\n\n"
        f"RETRIEVED ACADEMIC CONTEXT:\n{context}\n\n"
        "Now answer the question from this context."
    )

    return [
        {
            "role": "system",
            "content": system_message
        },
        {
            "role": "user",
            "content": user_message
        }
    ]


# --------------------------------------------------
# Call an OpenAI-compatible chat endpoint
# --------------------------------------------------

def call_llm(messages):
    api_url, api_key, model = get_llm_config()

    if not api_url or not api_key or not model:
        raise RuntimeError(
            "LLM is not configured. Set LLM_API_URL, "
            "LLM_API_KEY and LLM_MODEL."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2
    }

    response = requests.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=90
    )

    response.raise_for_status()

    data = response.json()

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(
            "The LLM returned an unexpected response format."
        )


# --------------------------------------------------
# Retrieve + Answer
# --------------------------------------------------

def rag_answer(question, semantic_chunks, top_k=DEFAULT_TOP_K):
    results = hybrid_search(
        question,
        semantic_chunks,
        final_top_k=top_k
    )

    if not results:
        return None, []

    context = build_context(results)
    messages = build_messages(
        question,
        context
    )

    answer = call_llm(messages)

    return answer, results


# --------------------------------------------------
# Fallback preview when no API is configured
# --------------------------------------------------

def show_retrieved_context(question, semantic_chunks):
    results = hybrid_search(
        question,
        semantic_chunks,
        final_top_k=DEFAULT_TOP_K
    )

    if not results:
        print("\nNo relevant context found.")
        return

    print(
        "\n========== RETRIEVED CONTEXT =========="
    )

    for number, result in enumerate(
        results,
        start=1
    ):
        print(
            f"\n[{number}] "
            f"{make_source_label(result)}"
        )
        print("-" * 70)
        print(result["text"][:1200])

        if len(result["text"]) > 1200:
            print("\n[Context preview truncated...]")


# --------------------------------------------------
# Interactive RAG mode
# --------------------------------------------------

def rag_chat_loop():
    print(
        "\n========== RAG ACADEMIC ASSISTANT V4 =========="
    )

    semantic_chunks = load_semantic_index()

    if semantic_chunks is None:
        print(
            "\nNo saved semantic index found."
        )
        print(
            "Run semantic_retrieval.py and build the index first."
        )
        return

    if not llm_is_configured():
        print(
            "\nLLM API is not configured yet."
        )
        print(
            "RAG retrieval will still work, but answer generation "
            "needs these environment variables:"
        )
        print("  LLM_API_URL")
        print("  LLM_API_KEY")
        print("  LLM_MODEL")

    while True:
        question = input(
            "\nAsk an academic question "
            "(or type back): "
        ).strip()

        if question.lower() == "back":
            break

        if not question:
            continue

        if not llm_is_configured():
            show_retrieved_context(
                question,
                semantic_chunks
            )
            continue

        try:
            print(
                "\nRetrieving knowledge and generating answer..."
            )

            answer, results = rag_answer(
                question,
                semantic_chunks
            )

            if answer is None:
                print(
                    "\nI could not find enough relevant material "
                    "in your knowledge library."
                )
                continue

            print(
                "\n========== AI ACADEMIC ANSWER =========="
            )
            print(answer)

        except requests.Timeout:
            print(
                "\nThe LLM request timed out. "
                "Please try again."
            )

        except requests.RequestException as error:
            print(
                f"\nLLM request failed: {error}"
            )

        except RuntimeError as error:
            print(
                f"\n{error}"
            )


if __name__ == "__main__":
    rag_chat_loop()
