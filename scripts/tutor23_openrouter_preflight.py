"""Bounded synthetic preflight for allow-listed, zero-price OpenRouter models.

Only one successful model is used for the entire follow-up browser acceptance.
Never emit credentials, headers, personal records, or model-generated text.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import requests

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
CANDIDATES = (
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "cohere/north-mini-code:free",
    "openrouter/free",
)
assert os.environ.get("LLM_API_URL") == ENDPOINT, "Unexpected API endpoint"
assert os.environ.get("LLM_MODEL") in CANDIDATES, "Unexpected initial free model"
key = os.environ.get("LLM_API_KEY", "")
assert key, "BLOCKED: OpenRouter Actions secret unavailable"
results = []
selected = None
for model in CANDIDATES:
    try:
        response = requests.post(
            ENDPOINT,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with only the word OK."}],
                "max_tokens": 180,
            },
            timeout=65,
        )
    except requests.RequestException as exc:
        results.append({"model": model, "status": "network_error", "error_type": type(exc).__name__})
        print("BLOCKED: " + model + " network " + type(exc).__name__)
        continue

    result = {"model": model, "http_status": response.status_code}
    results.append(result)
    if response.status_code == 200:
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            content = None
        if isinstance(content, str) and content.strip():
            selected = model
            result["status"] = "response_verified"
            print("PASS: Genuine synthetic completion from " + model)
            break
        result["status"] = "empty_or_unreadable_response"
        print("BLOCKED: " + model + " response content empty/incompatible")
    else:
        result["status"] = "provider_error"
        print("BLOCKED: " + model + " HTTP " + str(response.status_code))
        # Account-level authorization, billing and rate-limit errors must not
        # trigger a burst of requests to other endpoints.
        if response.status_code in (401, 402, 403, 429):
            break

artifact_dir = Path(os.environ.get("ANVAYA_LIVE_ARTIFACTS", "tutor-openrouter-artifacts"))
artifact_dir.mkdir(parents=True, exist_ok=True)
(artifact_dir / "openrouter-preflight.json").write_text(
    json.dumps({"source": "synthetic API requests only", "attempts": results, "selected_model": selected}, indent=2),
    encoding="utf-8",
)
if not selected:
    print("BLOCKED: No allowed zero-price model returned an eligible response; live scenarios not run.")
    sys.exit(2)

# GITHUB_ENV scopes the chosen model to later steps in THIS SAME trusted job.
github_env = os.environ.get("GITHUB_ENV")
if not github_env:
    print("BLOCKED: Missing GitHub Actions environment file")
    sys.exit(2)
with open(github_env, "a", encoding="utf-8") as stream:
    stream.write("LLM_MODEL=" + selected + "\n")
print("PASS: Pinned one verified free model for subsequent Tutor acceptance.")
