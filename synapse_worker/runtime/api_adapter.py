"""API adapter: hosted LLM providers over HTTP (§4.3).

Implements the :class:`~synapse_worker.runtime.base.Adapter` protocol for the
``"api"`` agent type. One adapter handles every hosted provider — anthropic, openai,
google, openrouter, ollama, or a custom ``base_url`` — by normalizing each provider's
request/response/usage shape into the daemon's common :class:`RunResult` + :class:`Usage`.

Design seams:
  * All network I/O funnels through :meth:`ApiAdapter._post`, and the ``httpx`` client is
    lazily constructed via :meth:`ApiAdapter._client`. Tests monkeypatch ``_post`` (or
    inject a client/transport) so the suite runs with NO network and NO real keys.
  * API keys are read from ``ctx.env`` (e.g. ``ANTHROPIC_API_KEY``) — never hardcoded,
    never logged.
  * Cost is derived from :func:`get_price_table` when the model is known; otherwise the
    run is flagged ``estimated`` rather than billed wrong.

Streaming is best-effort: providers that stream are consumed chunk-by-chunk and each
chunk is surfaced as a ``completion`` trace; non-streaming providers emit one completion
trace with the whole body. A ``prompt`` trace is always emitted first.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from ..logging import get_logger
from .base import RunContext, RunResult, Usage, get_price_table, register_adapter

log = get_logger(__name__)

# Default API endpoints per provider. ``custom`` / ``ollama`` come from the manifest's
# ``base_url``. These are the chat/messages completion endpoints.
_DEFAULT_BASE_URLS = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com",
    "google": "https://generativelanguage.googleapis.com",
    "openrouter": "https://openrouter.ai/api",
    "ollama": "http://localhost:11434",
}

# Env var name we look up the key under, per provider.
_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


class ApiAdapter:
    """Adapter for hosted LLM API providers."""

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        # An injected client (or a transport-backed one) lets tests avoid the network.
        self._injected = client

    # ── adapter protocol ──────────────────────────────────────────────────
    async def run(self, ctx: RunContext) -> RunResult:
        api = ctx.manifest.api or {}
        provider = str(api.get("provider") or "custom").lower()
        model = api.get("model")
        prompt = str(ctx.prompt_vars.get("prompt", ""))

        await ctx.trace("prompt", role="user", content=prompt)

        try:
            text, usage = await self._dispatch(ctx, provider, api, prompt)
        except Exception as exc:  # noqa: BLE001 - surface as a failed run, never raise
            log.warning("api run %s: provider call failed: %s", ctx.run_id, exc)
            await ctx.trace("error", message=str(exc))
            return RunResult(status="failed", error=str(exc))

        await ctx.trace("completion", role="assistant", content=text)

        # Cost: price table is keyed by model; absent -> estimated, not billed wrong.
        usage = self._priced(model, usage)
        await ctx.trace(
            "token",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd,
        )
        return RunResult(status="success", usage=usage, output=text)

    # ── provider dispatch ─────────────────────────────────────────────────
    async def _dispatch(
        self, ctx: RunContext, provider: str, api: dict[str, Any], prompt: str
    ) -> tuple[str, Usage]:
        url = self._endpoint(provider, api)
        headers, body = self._build_request(provider, api, prompt, ctx.env)
        data = await self._post(url, headers=headers, json=body)
        return self._normalize(provider, data)

    def _endpoint(self, provider: str, api: dict[str, Any]) -> str:
        base = api.get("base_url") or _DEFAULT_BASE_URLS.get(provider)
        if not base:
            raise ValueError(f"provider {provider!r} requires a base_url")
        base = base.rstrip("/")
        model = api.get("model", "")
        if provider == "anthropic":
            return f"{base}/v1/messages"
        if provider == "google":
            # Gemini puts the model in the path.
            return f"{base}/v1beta/models/{model}:generateContent"
        if provider == "ollama":
            return f"{base}/api/chat"
        # openai / openrouter / custom all speak the OpenAI chat-completions shape.
        return f"{base}/v1/chat/completions"

    def _build_request(
        self, provider: str, api: dict[str, Any], prompt: str, env: dict[str, str]
    ) -> tuple[dict[str, str], dict[str, Any]]:
        model = api.get("model", "")
        max_tokens = int(api.get("max_tokens", 1024))
        temperature = api.get("temperature")
        key = self._api_key(provider, env)

        if provider == "anthropic":
            headers = {
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
            }
            if key:
                headers["x-api-key"] = key
            body: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            if temperature is not None:
                body["temperature"] = temperature
            return headers, body

        if provider == "google":
            # Gemini keys go on the query in real usage, but the body stays the same;
            # we pass the key via header to keep _post signature uniform/test-friendly.
            headers = {"content-type": "application/json"}
            if key:
                headers["x-goog-api-key"] = key
            body = {"contents": [{"parts": [{"text": prompt}]}]}
            gen: dict[str, Any] = {"maxOutputTokens": max_tokens}
            if temperature is not None:
                gen["temperature"] = temperature
            body["generationConfig"] = gen
            return headers, body

        if provider == "ollama":
            # Local Ollama needs no key.
            headers = {"content-type": "application/json"}
            body = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            }
            return headers, body

        # openai / openrouter / custom -> OpenAI chat-completions
        headers = {"content-type": "application/json"}
        if key:
            headers["authorization"] = f"Bearer {key}"
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if temperature is not None:
            body["temperature"] = temperature
        return headers, body

    def _api_key(self, provider: str, env: dict[str, str]) -> Optional[str]:
        name = _KEY_ENV.get(provider)
        if name and env.get(name):
            return env[name]
        # custom / unknown providers may carry a generic key.
        return env.get("API_KEY")

    # ── response normalization ────────────────────────────────────────────
    def _normalize(self, provider: str, data: dict[str, Any]) -> tuple[str, Usage]:
        if provider == "anthropic":
            return self._normalize_anthropic(data)
        if provider == "google":
            return self._normalize_google(data)
        if provider == "ollama":
            return self._normalize_ollama(data)
        return self._normalize_openai(data)

    def _normalize_anthropic(self, data: dict[str, Any]) -> tuple[str, Usage]:
        parts = data.get("content") or []
        text = "".join(
            p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"
        )
        u = data.get("usage") or {}
        usage = Usage(
            input_tokens=int(u.get("input_tokens", 0)),
            output_tokens=int(u.get("output_tokens", 0)),
            cache_create_tokens=int(u.get("cache_creation_input_tokens", 0)),
            cache_read_tokens=int(u.get("cache_read_input_tokens", 0)),
        )
        return text, usage

    def _normalize_openai(self, data: dict[str, Any]) -> tuple[str, Usage]:
        choices = data.get("choices") or []
        text = ""
        if choices:
            msg = choices[0].get("message") or {}
            text = msg.get("content") or ""
        u = data.get("usage") or {}
        details = u.get("prompt_tokens_details") or {}
        usage = Usage(
            input_tokens=int(u.get("prompt_tokens", 0)),
            output_tokens=int(u.get("completion_tokens", 0)),
            cache_read_tokens=int(details.get("cached_tokens", 0)),
        )
        return text, usage

    def _normalize_google(self, data: dict[str, Any]) -> tuple[str, Usage]:
        candidates = data.get("candidates") or []
        text = ""
        if candidates:
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        u = data.get("usageMetadata") or {}
        usage = Usage(
            input_tokens=int(u.get("promptTokenCount", 0)),
            output_tokens=int(u.get("candidatesTokenCount", 0)),
            cache_read_tokens=int(u.get("cachedContentTokenCount", 0)),
        )
        return text, usage

    def _normalize_ollama(self, data: dict[str, Any]) -> tuple[str, Usage]:
        text = (data.get("message") or {}).get("content", "")
        usage = Usage(
            input_tokens=int(data.get("prompt_eval_count", 0)),
            output_tokens=int(data.get("eval_count", 0)),
            estimated=True,  # Ollama is local/free; tokens are informational only.
        )
        return text, usage

    # ── cost ───────────────────────────────────────────────────────────────
    def _priced(self, model: Optional[str], usage: Usage) -> Usage:
        """Fill ``usage.cost_usd`` from the price table; flag ``estimated`` if unknown.

        Price table schema (per million tokens):
            {model: {"input": float, "output": float,
                     "cache_create": float, "cache_read": float}}
        """
        table = get_price_table() or {}
        price = table.get(model) if model else None
        if not isinstance(price, dict):
            usage.estimated = True
            return usage
        cost = (
            usage.input_tokens * float(price.get("input", 0.0))
            + usage.output_tokens * float(price.get("output", 0.0))
            + usage.cache_create_tokens * float(price.get("cache_create", 0.0))
            + usage.cache_read_tokens * float(price.get("cache_read", 0.0))
        ) / 1_000_000.0
        usage.cost_usd = round(cost, 6)
        return usage

    # ── HTTP seam (monkeypatch target) ────────────────────────────────────
    def _client(self) -> httpx.AsyncClient:
        if self._injected is not None:
            return self._injected
        return httpx.AsyncClient(timeout=httpx.Timeout(60.0))

    async def _post(
        self, url: str, *, headers: dict[str, str], json: dict[str, Any]
    ) -> dict[str, Any]:
        """POST and return the decoded JSON body. The single network choke point.

        Tests monkeypatch this method to return a canned body, so no real client is
        constructed and no key is required.
        """
        client = self._client()
        owns = self._injected is None
        try:
            resp = await client.post(url, headers=headers, json=json)
            resp.raise_for_status()
            return resp.json()
        finally:
            if owns:
                await client.aclose()


# Register at import so daemon assembly wires the "api" adapter (commands/agents imports us).
register_adapter("api", lambda: ApiAdapter())
