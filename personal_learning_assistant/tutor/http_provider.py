"""Optional OpenAI-compatible HTTP provider for Phase 6.2.

The adapter is lazy: importing Phase 6.2 performs no network request. Tests use
fake providers; the Phase 6.2 gate never performs a network call.
"""

from __future__ import annotations

import os

from personal_learning_assistant.domain.tutor_models import TutorProviderResponse
from personal_learning_assistant.tutor.provider import (
    TutorProviderUnavailableError,
)


class TutorProviderRequestError(RuntimeError):
    pass


class OpenAICompatibleTutorProvider:
    def __init__(
        self,
        *,
        api_url=None,
        api_key=None,
        model=None,
        timeout_seconds=90,
        temperature=0.1,
    ):
        self.api_url = str(
            api_url if api_url is not None else os.getenv("LLM_API_URL", "")
        ).strip()
        self.api_key = str(
            api_key if api_key is not None else os.getenv("LLM_API_KEY", "")
        ).strip()
        self.model = str(
            model if model is not None else os.getenv("LLM_MODEL", "")
        ).strip()
        self.timeout_seconds = int(timeout_seconds)
        self.temperature = float(temperature)

    @property
    def configured(self):
        return bool(self.api_url and self.api_key and self.model)

    def complete(self, request):
        if not self.configured:
            raise TutorProviderUnavailableError(
                "Tutor provider is not configured. Set LLM_API_URL, "
                "LLM_API_KEY and LLM_MODEL, or inject another TutorProvider."
            )
        try:
            import requests
        except ImportError as error:
            raise TutorProviderUnavailableError(
                "Tutor HTTP generation requires the requests package."
            ) from error

        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": "Bearer {}".format(self.api_key),
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": list(request.messages),
                    "temperature": self.temperature,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except requests.Timeout as error:
            raise TutorProviderRequestError("tutor provider request timed out") from error
        except requests.RequestException as error:
            raise TutorProviderRequestError(
                "tutor provider HTTP request failed: {}".format(error)
            ) from error
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise TutorProviderRequestError(
                "tutor provider returned an invalid response payload"
            ) from error

        clean = str(content or "").strip()
        if not clean:
            raise TutorProviderRequestError(
                "tutor provider returned an empty answer"
            )
        request_id = str(
            payload.get("id", "")
            if isinstance(payload, dict)
            else ""
        )
        return TutorProviderResponse(
            content=clean,
            provider_name="openai-compatible-http",
            provider_model=self.model,
            request_id=request_id,
        )
