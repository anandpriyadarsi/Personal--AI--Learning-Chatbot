"""One synthetic OpenRouter availability check with a bounded, sanitized error.

No secrets, request headers, or generated text are ever printed.
"""
import os
import re
import sys
import requests

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
assert os.environ.get("LLM_API_URL") == ENDPOINT, "Endpoint mismatch"
assert os.environ.get("LLM_MODEL") == MODEL, "Model mismatch"
key = os.environ.get("LLM_API_KEY", "")
assert key, "BLOCKED: OpenRouter Actions secret unavailable"
payload = {
    "model": MODEL,
    "messages": [{"role": "user", "content": "Answer only OK, with no explanation."}],
    "temperature": 0.1,
    "max_tokens": 80,
}
try:
    response = requests.post(
        ENDPOINT,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        json=payload,
        timeout=70,
    )
except requests.RequestException as exc:
    print("BLOCKED: OpenRouter request: " + type(exc).__name__)
    sys.exit(2)
if response.status_code != 200:
    message = ""
    try:
        error = response.json().get("error", {})
        message = str(error.get("message", ""))[:220] if isinstance(error, dict) else ""
    except (ValueError, TypeError):
        pass
    message = message.replace(key, "[REDACTED]")
    message = re.sub(r"sk-or-v1-[A-Za-z0-9_-]+", "[REDACTED]", message)
    message = re.sub(r"Bearer\\s+\\S+", "[REDACTED]", message, flags=re.I)
    print("BLOCKED: OpenRouter HTTP " + str(response.status_code) + ". " + message)
    sys.exit(2)
try:
    result = response.json()
    answer = result["choices"][0]["message"]["content"]
except (ValueError, TypeError, KeyError, IndexError):
    print("BLOCKED: Model response shape incompatible with Tutor HTTP adapter")
    sys.exit(2)
if not isinstance(answer, str) or not answer.strip():
    print("BLOCKED: Model returned empty content")
    sys.exit(2)
print("PASS: OpenRouter returned a genuine chat completion for a synthetic prompt.")
print("Model: " + MODEL)
