"""Quota-aware, fail-closed OpenRouter preflight for disposable Tutor acceptance.

No new key or paid route, no secrets, headers or generated text in evidence.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import requests

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
KEY_ENDPOINT = "https://openrouter.ai/api/v1/key"
CANDIDATES = (
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "cohere/north-mini-code:free",
    "openrouter/free",
)
# The browser suite permits at most 24 model calls. Reserve one preflight.
REQUIRED_QUOTA = 25


def quota_snapshot(key):
    """Read remaining account quota without making an inference request."""
    try:
        response = requests.get(
            KEY_ENDPOINT, headers={"Authorization": "Bearer " + key}, timeout=20
        )
        if response.status_code != 200:
            return None, "quota_http_" + str(response.status_code)
        quota = response.json()["data"]["free_model_daily_requests"]
        remaining, limit, used = (quota[k] for k in ("remaining", "limit", "used"))
        if any(type(x) is not int or x < 0 for x in (remaining, limit, used)):
            return None, "invalid_quota_numbers"
        return {"remaining": remaining, "limit": limit, "used": used}, None
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        return None, "quota_unavailable_" + type(error).__name__


def upstream_rate_limit(response):
    """Only a documented upstream 429 permits testing another free model."""
    if response.status_code != 429:
        return False
    try:
        metadata = response.json().get("error", {}).get("metadata", {})
        return str(metadata.get("provider_code", "")) == "429"
    except (ValueError, AttributeError, TypeError):
        return False


def save_report(folder, attempts, quota, selected=None, blocked=None):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "openrouter-preflight.json").write_text(
        json.dumps({
            "source": "synthetic API requests only",
            "quota": quota,
            "attempts": attempts,
            "selected_model": selected,
            "blocked_reason": blocked,
            "estimated_full_run_reserve": REQUIRED_QUOTA,
        }, indent=2), encoding="utf-8"
    )


def main():
    folder = Path(os.environ.get("ANVAYA_LIVE_ARTIFACTS", "tutor-openrouter-artifacts"))
    attempts = []
    if os.environ.get("LLM_API_URL") != ENDPOINT or os.environ.get("LLM_MODEL") not in CANDIDATES:
        save_report(folder, attempts, None, blocked="endpoint_or_initial_model_not_allowlisted")
        print("BLOCKED: OpenRouter URL or requested model not allowlisted")
        return 2
    key = os.environ.get("LLM_API_KEY", "")
    if not key:
        save_report(folder, attempts, None, blocked="secret_unavailable")
        print("BLOCKED: OpenRouter Actions secret unavailable")
        return 2
    quota, error = quota_snapshot(key)
    if error or quota is None:
        save_report(folder, attempts, quota, blocked=error)
        print("BLOCKED: Cannot safely verify the free-model account quota")
        return 2
    print("OpenRouter daily free-model requests remaining: " + str(quota["remaining"]) +
          " of " + str(quota["limit"]))
    if quota["remaining"] < REQUIRED_QUOTA:
        save_report(folder, attempts, quota, blocked="insufficient_daily_quota")
        print("BLOCKED: Insufficient free quota for bounded full A-K; no model request sent.")
        return 2

    selected = None
    blocked = None
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
        except requests.RequestException as error:
            attempts.append({"model": model, "status": "network_error", "type": type(error).__name__})
            print("BLOCKED: " + model + " network " + type(error).__name__)
            continue

        result = {"model": model, "http_status": response.status_code}
        attempts.append(result)
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
            continue

        result["status"] = "provider_error"
        print("BLOCKED: " + model + " HTTP " + str(response.status_code))
        if response.status_code in (401, 402, 403):
            blocked = "account_or_key_rejected"
            break
        if response.status_code == 429:
            # 429 can mean daily/account exhaustion OR an overloaded upstream.
            # Query quota again (no completion) and only switch free models when
            # provider_code explicitly identifies a provider-side 429.
            after, quota_error = quota_snapshot(key)
            if after is not None:
                result["remaining_after"] = after["remaining"]
            if quota_error or not upstream_rate_limit(response) or after is None or after["remaining"] < 24:
                blocked = "account_or_unclassified_rate_limit"
                break
            result["status"] = "provider_scoped_rate_limit"
            print("Provider-scoped 429: trying next allowlisted free model, not retrying same model.")

    if not selected:
        save_report(folder, attempts, quota, blocked=blocked or "no_eligible_free_response")
        print("BLOCKED: No zero-price model available; genuine A-K not certified.")
        return 2

    github_env = os.environ.get("GITHUB_ENV")
    if not github_env:
        save_report(folder, attempts, quota, blocked="missing_github_env")
        print("BLOCKED: Missing GitHub Actions environment file")
        return 2
    with open(github_env, "a", encoding="utf-8") as stream:
        stream.write("LLM_MODEL=" + selected + "\n")
    save_report(folder, attempts, quota, selected=selected)
    print("PASS: Pinned a genuine, allowlisted free model for this job.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
