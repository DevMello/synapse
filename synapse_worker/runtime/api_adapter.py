"""API adapter: hosted LLM providers over HTTP (§4.3).

Implements the :class:`~synapse_worker.runtime.base.Adapter` protocol for the
``"api"`` agent type. One adapter handles every hosted provider — anthropic, openai,
google, openrouter, ollama, or a custom ``base_url`` — by normalizing each provider's
request/response/usage shape into the daemon's common :class:`RunResult` + :class:`Usage`.

When the agent declares ``[[tools]]`` the adapter runs an **agentic tool-calling loop**
(§10.5): the model proposes a tool, the daemon executes it through the ``ctx.tool_executor``
seam, the result is threaded back, and the loop repeats until the model stops requesting
tools (or a bounded iteration cap is hit). The executor is pluggable: a normal run uses
:class:`~synapse_worker.runtime.tools.DefaultToolExecutor`; a §10 comparison variant injects
a draft-mode shim that simulates side-effecting calls instead of running them.

Design seams:
  * All network I/O funnels through :meth:`ApiAdapter._post`, and the ``httpx`` client is
    lazily constructed via :meth:`ApiAdapter._client`. Tests monkeypatch ``_post`` (or
    inject a client/transport) so the suite runs with NO network and NO real keys.
  * API keys are read from ``ctx.env`` (e.g. ``ANTHROPIC_API_KEY``) — never hardcoded,
    never logged.
  * Cost is derived from :func:`get_price_table` when the model is known; otherwise the
    run is flagged ``estimated`` rather than billed wrong.

Tool-calling loops are implemented for the Anthropic (``tool_use``/``tool_result``) and
OpenAI (``tool_calls``/``role:tool``) message shapes; google/ollama stay single-shot.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from ..logging import get_logger
from .base import RunContext, RunResult, Usage, get_price_table, register_adapter
from .tools import DefaultToolExecutor, ToolCall, ToolExecutor

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

# Hard upper bound on agentic-loop model turns, so a misbehaving model can't loop forever.
_DEFAULT_MAX_ITERS = 8

# Providers whose message shape the tool-calling loop understands. Others stay single-shot.
_TOOL_LOOP_PROVIDERS = {"anthropic", "openai", "openrouter", "custom"}


class _Turn:
    """One model turn: final text, usage, the tool calls it requested, and the raw
    assistant message to thread back for the next turn."""

    __slots__ = ("text", "usage", "tool_calls", "assistant_msg")

    def __init__(
        self,
        text: str,
        usage: Usage,
        tool_calls: list[ToolCall],
        assistant_msg: Optional[dict[str, Any]],
    ) -> None:
        self.text = text
        self.usage = usage
        self.tool_calls = tool_calls
        self.assistant_msg = assistant_msg


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
        tools = ctx.manifest.tools or []
        executor: ToolExecutor = ctx.tool_executor or DefaultToolExecutor()

        await ctx.trace("prompt", role="user", content=prompt)

        # Iteration cap: manifest max_tool_calls (+1 for the final text turn) bounded by a
        # hard ceiling. With no tools, this is a single turn (the loop breaks immediately).
        max_calls = ctx.manifest.max_tool_calls
        max_iters = 1 if not tools else min(
            _DEFAULT_MAX_ITERS, (int(max_calls) + 1) if max_calls else _DEFAULT_MAX_ITERS
        )

        messages = self._init_messages(provider, prompt)
        total = Usage()
        text = ""
        try:
            for i in range(max_iters):
                # On the last permitted iteration, drop the tools so the model must answer
                # with text rather than request another (un-runnable) tool call.
                offer_tools = tools if (tools and i < max_iters - 1) else []
                turn = await self._one_turn(ctx, provider, api, messages, offer_tools)
                total = total.add(turn.usage)
                text = turn.text or text
                if not turn.tool_calls:
                    break
                # Thread the assistant turn, execute each requested tool, append results.
                if turn.assistant_msg is not None:
                    messages.append(turn.assistant_msg)
                results: list[tuple[ToolCall, Any]] = []
                for call in turn.tool_calls:
                    await ctx.trace("tool_call", name=call.name, args=call.args, tool_id=call.id)
                    result = await executor.execute(call.name, call.args)
                    await ctx.trace("tool_result", name=call.name, tool_id=call.id, result=result)
                    results.append((call, result))
                messages.extend(self._tool_result_messages(provider, results))
        except Exception as exc:  # noqa: BLE001 - surface as a failed run, never raise
            log.warning("api run %s: provider call failed: %s", ctx.run_id, exc)
            await ctx.trace("error", message=str(exc))
            return RunResult(status="failed", error=str(exc))

        await ctx.trace("completion", role="assistant", content=text)

        # Cost: price table is keyed by model; absent -> estimated, not billed wrong.
        total = self._priced(model, total)
        await ctx.trace(
            "token",
            input_tokens=total.input_tokens,
            output_tokens=total.output_tokens,
            cost_usd=total.cost_usd,
        )
        return RunResult(status="success", usage=total, output=text)

    # ── one model turn (single POST + normalize) ──────────────────────────
    async def _one_turn(
        self,
        ctx: RunContext,
        provider: str,
        api: dict[str, Any],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> "_Turn":
        url = self._endpoint(provider, api)
        headers, body = self._build_request(provider, api, messages, tools, ctx.env)
        data = await self._post(url, headers=headers, json=body)
        return self._normalize(provider, data)

    # ── message threading ─────────────────────────────────────────────────
    def _init_messages(self, provider: str, prompt: str) -> list[dict[str, Any]]:
        if provider == "google":
            return [{"role": "user", "parts": [{"text": prompt}]}]
        return [{"role": "user", "content": prompt}]

    def _tool_result_messages(
        self, provider: str, results: list[tuple[ToolCall, Any]]
    ) -> list[dict[str, Any]]:
        """Build the provider-specific message(s) that carry tool results back to the model."""
        if not results:
            return []
        if provider == "anthropic":
            blocks = [
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": _as_text(result),
                }
                for call, result in results
            ]
            return [{"role": "user", "content": blocks}]
        # openai / openrouter / custom: one tool message per call.
        return [
            {"role": "tool", "tool_call_id": call.id, "content": _as_text(result)}
            for call, result in results
        ]

    # ── provider request build ────────────────────────────────────────────
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
        self,
        provider: str,
        api: dict[str, Any],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        env: dict[str, str],
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
                "messages": messages,
            }
            if temperature is not None:
                body["temperature"] = temperature
            if tools:
                body["tools"] = [_anthropic_tool(t) for t in tools]
            return headers, body

        if provider == "google":
            # Gemini keys go on the query in real usage, but the body stays the same;
            # we pass the key via header to keep _post signature uniform/test-friendly.
            headers = {"content-type": "application/json"}
            if key:
                headers["x-goog-api-key"] = key
            body = {"contents": messages}
            gen: dict[str, Any] = {"maxOutputTokens": max_tokens}
            if temperature is not None:
                gen["temperature"] = temperature
            body["generationConfig"] = gen
            return headers, body

        if provider == "ollama":
            # Local Ollama needs no key.
            headers = {"content-type": "application/json"}
            body = {"model": model, "messages": messages, "stream": False}
            return headers, body

        # openai / openrouter / custom -> OpenAI chat-completions
        headers = {"content-type": "application/json"}
        if key:
            headers["authorization"] = f"Bearer {key}"
        body = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if temperature is not None:
            body["temperature"] = temperature
        if tools:
            body["tools"] = [_openai_tool(t) for t in tools]
        return headers, body

    def _api_key(self, provider: str, env: dict[str, str]) -> Optional[str]:
        name = _KEY_ENV.get(provider)
        if name and env.get(name):
            return env[name]
        # custom / unknown providers may carry a generic key.
        return env.get("API_KEY")

    # ── response normalization ────────────────────────────────────────────
    def _normalize(self, provider: str, data: dict[str, Any]) -> "_Turn":
        if provider == "anthropic":
            return self._normalize_anthropic(data)
        if provider == "google":
            return self._normalize_google(data)
        if provider == "ollama":
            return self._normalize_ollama(data)
        return self._normalize_openai(data)

    def _normalize_anthropic(self, data: dict[str, Any]) -> "_Turn":
        parts = data.get("content") or []
        text = "".join(
            p.get("text", "")
            for p in parts
            if isinstance(p, dict) and p.get("type") == "text"
        )
        tool_calls = [
            ToolCall(
                id=str(p.get("id") or ""),
                name=str(p.get("name") or ""),
                args=p.get("input") if isinstance(p.get("input"), dict) else {},
            )
            for p in parts
            if isinstance(p, dict) and p.get("type") == "tool_use"
        ]
        u = data.get("usage") or {}
        usage = Usage(
            input_tokens=int(u.get("input_tokens", 0)),
            output_tokens=int(u.get("output_tokens", 0)),
            cache_create_tokens=int(u.get("cache_creation_input_tokens", 0)),
            cache_read_tokens=int(u.get("cache_read_input_tokens", 0)),
        )
        assistant_msg = {"role": "assistant", "content": parts} if tool_calls else None
        return _Turn(text, usage, tool_calls, assistant_msg)

    def _normalize_openai(self, data: dict[str, Any]) -> "_Turn":
        choices = data.get("choices") or []
        text = ""
        raw_msg: dict[str, Any] = {}
        tool_calls: list[ToolCall] = []
        if choices:
            raw_msg = choices[0].get("message") or {}
            text = raw_msg.get("content") or ""
            for tc in raw_msg.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                tool_calls.append(
                    ToolCall(
                        id=str(tc.get("id") or ""),
                        name=str(fn.get("name") or ""),
                        args=_parse_args(fn.get("arguments")),
                    )
                )
        u = data.get("usage") or {}
        details = u.get("prompt_tokens_details") or {}
        usage = Usage(
            input_tokens=int(u.get("prompt_tokens", 0)),
            output_tokens=int(u.get("completion_tokens", 0)),
            cache_read_tokens=int(details.get("cached_tokens", 0)),
        )
        assistant_msg = raw_msg if tool_calls else None
        return _Turn(text, usage, tool_calls, assistant_msg)

    def _normalize_google(self, data: dict[str, Any]) -> "_Turn":
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
        return _Turn(text, usage, [], None)

    def _normalize_ollama(self, data: dict[str, Any]) -> "_Turn":
        text = (data.get("message") or {}).get("content", "")
        usage = Usage(
            input_tokens=int(data.get("prompt_eval_count", 0)),
            output_tokens=int(data.get("eval_count", 0)),
            estimated=True,  # Ollama is local/free; tokens are informational only.
        )
        return _Turn(text, usage, [], None)

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


# ── module helpers ──────────────────────────────────────────────────────────
def _as_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return str(result)


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"_": parsed}
        except (TypeError, ValueError):
            return {}
    return {}


def _anthropic_tool(t: dict[str, Any]) -> dict[str, Any]:
    schema = t.get("input_schema") or t.get("parameters") or {"type": "object", "properties": {}}
    return {
        "name": str(t.get("name") or ""),
        "description": str(t.get("description") or ""),
        "input_schema": schema,
    }


def _openai_tool(t: dict[str, Any]) -> dict[str, Any]:
    schema = t.get("parameters") or t.get("input_schema") or {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": str(t.get("name") or ""),
            "description": str(t.get("description") or ""),
            "parameters": schema,
        },
    }


# Register at import so daemon assembly wires the "api" adapter (commands/agents imports us).
register_adapter("api", lambda: ApiAdapter())
