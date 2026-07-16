"""LLM providers for natural-language → SQL generation (Task C).

Each provider talks to its own HTTP endpoint with the user's API key (a plain
HTTP call — no SDK required) and returns the model's SQL text. The HTTP client is
injectable so tests can mock it (no real network, no real key). The generated SQL
is treated as a **read-only** report query: callers must pass it through
``ensure_readonly`` (Phase 5) before executing it.
"""

from __future__ import annotations

import json
import re
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Callable

# HTTP client: (url, headers, json_payload) -> parsed JSON response.
HttpClient = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]

_SYSTEM = (
    "You are a SQL assistant. Generate a single READ-ONLY SQL SELECT query for the "
    "user's request, using only the given tables and columns. Return ONLY the SQL, "
    "with no explanation and no code fences. Never write INSERT/UPDATE/DELETE/DDL."
)

_FENCE = re.compile(r"^```(?:sql)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def default_http(
    url: str, headers: dict[str, str], payload: dict[str, Any]
) -> dict[str, Any]:
    """POST ``payload`` as JSON and return the parsed JSON response."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as resp:  # noqa: S310 (local app)
        return json.loads(resp.read().decode("utf-8"))


def format_schema(schema: dict[str, list[str]]) -> str:
    """Render ``{table: [columns]}`` as a compact textual schema for the prompt."""
    return "\n".join(f"{t}({', '.join(cols)})" for t, cols in schema.items())


def clean_sql(text: str) -> str:
    """Strip markdown fences / surrounding whitespace from the model output."""
    return _FENCE.sub("", text).strip()


class LLMProvider(ABC):
    """Abstract base for an LLM provider."""

    name: str = "base"

    def __init__(
        self,
        api_key: str,
        model: str,
        http: HttpClient | None = None,
        system: str | None = None,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._http = http or default_http
        self._system = system or _SYSTEM

    def _user_prompt(self, prompt: str, schema: dict[str, list[str]]) -> str:
        return f"Schema:\n{format_schema(schema)}\n\nRequest:\n{prompt}"

    @abstractmethod
    def build_request(
        self, prompt: str, schema: dict[str, list[str]]
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        """Return ``(url, headers, payload)`` for this provider."""

    @abstractmethod
    def extract_sql(self, response: dict[str, Any]) -> str:
        """Pull the SQL text out of the provider's response JSON."""

    def generate_sql(self, prompt: str, schema: dict[str, list[str]]) -> str:
        """Call the provider and return cleaned SQL (still to be validated)."""
        url, headers, payload = self.build_request(prompt, schema)
        response = self._http(url, headers, payload)
        return clean_sql(self.extract_sql(response))


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def build_request(self, prompt, schema):  # type: ignore[override]
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "system": self._system,
            "messages": [
                {"role": "user", "content": self._user_prompt(prompt, schema)}
            ],
        }
        return url, headers, payload

    def extract_sql(self, response):  # type: ignore[override]
        return response["content"][0]["text"]


class OpenAIProvider(LLMProvider):
    name = "openai"
    _url = "https://api.openai.com/v1/chat/completions"

    def build_request(self, prompt, schema):  # type: ignore[override]
        headers = {"Authorization": f"Bearer {self._api_key}"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._system},
                {"role": "user", "content": self._user_prompt(prompt, schema)},
            ],
        }
        return self._url, headers, payload

    def extract_sql(self, response):  # type: ignore[override]
        return response["choices"][0]["message"]["content"]


class DeepSeekProvider(OpenAIProvider):
    """DeepSeek exposes an OpenAI-compatible chat completions API."""

    name = "deepseek"
    _url = "https://api.deepseek.com/chat/completions"


class GeminiProvider(LLMProvider):
    name = "google"

    def build_request(self, prompt, schema):  # type: ignore[override]
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self._api_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": self._system}]},
            "contents": [{"parts": [{"text": self._user_prompt(prompt, schema)}]}],
        }
        return url, {}, payload

    def extract_sql(self, response):  # type: ignore[override]
        return response["candidates"][0]["content"]["parts"][0]["text"]


_PROVIDERS: dict[str, type[LLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "google": GeminiProvider,
    "deepseek": DeepSeekProvider,
}

# Convenience default models per provider (user-overridable).
DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-3-5-sonnet-latest",
    "openai": "gpt-4o-mini",
    "google": "gemini-1.5-flash",
    "deepseek": "deepseek-chat",
}

PROVIDER_LABELS: dict[str, str] = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI (ChatGPT)",
    "google": "Google (Gemini)",
    "deepseek": "DeepSeek",
}


def get_provider(
    name: str,
    api_key: str,
    model: str,
    http: HttpClient | None = None,
    system: str | None = None,
) -> LLMProvider:
    """Instantiate a provider by name (optionally with a custom system prompt)."""
    try:
        cls = _PROVIDERS[name]
    except KeyError as exc:
        raise ValueError(f"Provider LLM sconosciuto: {name!r}") from exc
    return cls(api_key=api_key, model=model, http=http, system=system)


def ddl_system_prompt(dialect: str) -> str:
    """System prompt instructing the model to emit reviewable DDL for ``dialect``."""
    return (
        "You are a database schema assistant. Generate DDL (e.g. CREATE TABLE) for "
        f"the {dialect} dialect from the user's description: columns with types, "
        "primary keys and foreign keys. Return ONLY the SQL DDL, no explanation and "
        "no code fences. The statement will be reviewed by a human before execution."
    )
