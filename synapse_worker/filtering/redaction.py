"""Layer A — PII / Secret Redaction (§4.5).

Every log line, tool arg, tool result, prompt, and completion passes through this filter
*on-device* before any byte is persisted or uploaded. Detection runs in layers:

  1. **Pattern / entropy** — regexes for well-known secret shapes (AWS/OpenAI/GitHub keys,
     JWTs, PEM private keys, emails, phones, Luhn-validated cards, IPv4/IPv6) plus a
     Shannon-entropy scan that catches generic high-entropy tokens (long base64/hex).
  2. **User rules** — per-agent / global regex or keyword denylists supplied via context
     or :meth:`RedactionFilter.add_rule`.
  3. **Registered secrets** — exact values known to be sensitive (e.g. a run's env-var
     values) registered via :meth:`RedactionFilter.register_secret`, masked even if echoed
     verbatim. (Presidio NER is an OPTIONAL extra; we guard the import and skip if absent.)

Matches are replaced with **stable, salted tokens** — ``<REDACTED:API_KEY:a91f>`` — where
the suffix is a truncated HMAC-SHA256 of ``(salt, raw_value)``. The same secret therefore
reads consistently across one trace WITHOUT leaking its value; the salt is per-process
random (or configurable) so tokens are not portable/guessable across daemons.

We NEVER place a raw matched value in a :class:`Finding`, the manifest, or a log line —
only categories, counts, and the stable token. CPU-bound *bulk* passes (large batches)
can be offloaded to a :class:`ProcessPoolExecutor` via :func:`redact_bulk`; the per-line
:meth:`RedactionFilter.screen` stays in-process and fast for normal-size text.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .base import (
    Direction,
    Finding,
    FilterResult,
    RedactionManifest,
    Severity,
)

# ── modes ───────────────────────────────────────────────────────────────────
MODE_MASK = "mask"   # tokenize -> <REDACTED:TYPE:hash> (default)
MODE_HASH = "hash"   # replace with the bare hash suffix only
MODE_BLOCK = "block"  # drop the whole field (FilterResult.blocked=True)

# Default per-category severities; categories not listed fall back to MEDIUM.
_SEVERITY: dict[str, Severity] = {
    "API_KEY": Severity.HIGH,
    "PRIVATE_KEY": Severity.HIGH,
    "JWT": Severity.HIGH,
    "AWS_KEY": Severity.HIGH,
    "GITHUB_TOKEN": Severity.HIGH,
    "ENV": Severity.HIGH,
    "CARD": Severity.HIGH,
    "EMAIL": Severity.LOW,
    "PHONE": Severity.LOW,
    "IP": Severity.LOW,
    "HIGH_ENTROPY": Severity.MEDIUM,
}


def _severity_for(category: str) -> Severity:
    return _SEVERITY.get(category, Severity.MEDIUM)


# ── entropy ─────────────────────────────────────────────────────────────────
def shannon_entropy(s: str) -> float:
    """Bits of Shannon entropy per character — high for random tokens, low for prose."""
    if not s:
        return 0.0
    counts: dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


# Entropy threshold (bits/char) above which a base64/hex-ish token is treated as a secret.
# Tuned so ordinary English words stay well under it (English prose ~3.5-4.0 over a *word*,
# but the candidate must ALSO be long and from a restricted alphabet, which prose isn't).
_ENTROPY_THRESHOLD = 4.0
_ENTROPY_MIN_LEN = 20  # only screen long candidate tokens; short words are never secrets


# ── detector spec ───────────────────────────────────────────────────────────
@dataclass
class _Detector:
    category: str
    pattern: re.Pattern[str]
    # Optional validator (e.g. Luhn) — return True to accept the raw match as a real hit.
    validate: Optional[Callable[[str], bool]] = None


def _luhn_ok(number: str) -> bool:
    """Luhn check — cuts false positives on arbitrary 13-19 digit runs."""
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 13:
        return False
    total = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# Order matters: the most specific / highest-value secrets first so an AWS key isn't
# first swallowed by the generic high-entropy pass. The high-entropy scan runs LAST.
def _build_detectors() -> list[_Detector]:
    return [
        # PEM private-key block (multi-line) — match the whole armored block.
        _Detector(
            "PRIVATE_KEY",
            re.compile(
                r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z ]+ )?PRIVATE KEY-----",
                re.DOTALL,
            ),
        ),
        # AWS access key id.
        _Detector("AWS_KEY", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
        # GitHub PATs (classic ghp_ + fine-grained github_pat_).
        _Detector(
            "GITHUB_TOKEN",
            re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{36,}\b|\bgithub_pat_[0-9A-Za-z_]{22,}\b"),
        ),
        # OpenAI / generic sk- keys (sk-, sk-proj-, ...).
        _Detector("API_KEY", re.compile(r"\bsk-(?:proj-)?[0-9A-Za-z_-]{20,}\b")),
        # JWT: three base64url segments separated by dots.
        _Detector(
            "JWT",
            re.compile(r"\beyJ[0-9A-Za-z_-]+\.[0-9A-Za-z_-]+\.[0-9A-Za-z_-]+\b"),
        ),
        # Email.
        _Detector(
            "EMAIL",
            re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        ),
        # Credit card — 13-19 digit runs (optional space/dash grouping), Luhn-validated.
        _Detector(
            "CARD",
            re.compile(r"\b(?:\d[ -]?){13,19}\b"),
            validate=_luhn_ok,
        ),
        # IPv6 (before IPv4; require a plausible colon-grouped form).
        _Detector(
            "IP",
            re.compile(r"\b(?:[0-9A-Fa-f]{1,4}:){2,7}[0-9A-Fa-f]{1,4}\b"),
        ),
        # IPv4 (each octet 0-255). Runs BEFORE phone so dotted IPs aren't read as numbers.
        _Detector(
            "IP",
            re.compile(
                r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
            ),
        ),
        # Phone — international-ish; require >= 10 digits and disallow '.' so it doesn't
        # eat IPv4 dotted-quads (those are claimed by the IP pass just above).
        _Detector(
            "PHONE",
            re.compile(r"(?<![\w.])\+?\d[\d()\- ]{8,}\d(?![\w.])"),
            validate=lambda m: sum(c.isdigit() for c in m) >= 10,
        ),
    ]


# Candidate tokens for the generic high-entropy pass: long base64/hex/url-safe runs.
_ENTROPY_CANDIDATE = re.compile(r"\b[0-9A-Za-z+/_=-]{%d,}\b" % _ENTROPY_MIN_LEN)


# ── user rules ──────────────────────────────────────────────────────────────
@dataclass
class UserRule:
    """A user-configured denylist entry. ``keyword`` is matched literally (escaped)."""

    category: str
    pattern: Optional[re.Pattern[str]] = None
    keyword: Optional[str] = None
    mode: str = MODE_MASK

    def finditer(self, text: str):
        if self.pattern is not None:
            yield from self.pattern.finditer(text)
        elif self.keyword:
            for m in re.finditer(re.escape(self.keyword), text):
                yield m


class RedactionFilter:
    """Layer A redaction filter (foundation :class:`Filter` protocol).

    Applies in BOTH directions — secrets can leak inbound (a poisoned prompt echoing a
    key) or outbound (a model logging an env var). Construct one per chain; salting state
    (the token map) is per-instance so the same secret reads consistently across a trace.
    """

    name = "redaction"

    def __init__(
        self,
        *,
        salt: Optional[bytes] = None,
        category_modes: Optional[dict[str, str]] = None,
        entropy_threshold: float = _ENTROPY_THRESHOLD,
    ) -> None:
        # Per-process random salt by default so tokens aren't portable/guessable.
        self._salt = salt if salt is not None else os.urandom(16)
        self._detectors = _build_detectors()
        self._user_rules: list[UserRule] = []
        # Exact known-secret values (e.g. a run's env values) -> category. Masked verbatim.
        self._registered: dict[str, str] = {}
        # Per-category mode override (block | mask | hash). Default mask.
        self._category_modes: dict[str, str] = dict(category_modes or {})
        self._entropy_threshold = entropy_threshold

    # ── public configuration API ────────────────────────────────────────────
    def add_rule(
        self,
        *,
        category: str,
        regex: Optional[str] = None,
        keyword: Optional[str] = None,
        mode: str = MODE_MASK,
        flags: int = 0,
    ) -> None:
        """Register a custom denylist rule (regex OR literal keyword)."""
        if not regex and not keyword:
            raise ValueError("add_rule needs a regex or a keyword")
        pattern = re.compile(regex, flags) if regex else None
        self._user_rules.append(
            UserRule(category=category, pattern=pattern, keyword=keyword, mode=mode)
        )

    def register_secret(self, value: str, category: str = "ENV") -> None:
        """Mark an exact value as sensitive so it's masked even when echoed verbatim.

        Short/empty values are ignored — masking a 1-char "secret" would shred normal text.
        """
        value = (value or "").strip()
        if len(value) < 4:
            return
        self._registered[value] = category

    def set_category_mode(self, category: str, mode: str) -> None:
        self._category_modes[category] = mode

    # ── token construction ──────────────────────────────────────────────────
    def _hash(self, raw: str) -> str:
        """Stable 4-byte (8 hex) HMAC suffix over (salt, raw). Never reversible."""
        digest = hmac.new(self._salt, raw.encode("utf-8", "surrogatepass"), hashlib.sha256)
        return digest.hexdigest()[:8]

    def _token(self, category: str, raw: str, mode: str) -> str:
        h = self._hash(raw)
        if mode == MODE_HASH:
            return h
        return f"<REDACTED:{category}:{h}>"

    def _mode_for(self, category: str, rule_mode: Optional[str] = None) -> str:
        if rule_mode and rule_mode != MODE_MASK:
            return rule_mode
        return self._category_modes.get(category, rule_mode or MODE_MASK)

    # ── Filter protocol ─────────────────────────────────────────────────────
    def screen(
        self,
        text: str,
        *,
        direction: Direction = Direction.OUTBOUND,
        context: Optional[dict[str, Any]] = None,
    ) -> FilterResult:
        if not text:
            return FilterResult(text=text)

        manifest = RedactionManifest()
        findings: list[Finding] = []
        out = text
        blocked = False

        def _run_pass(category: str, finditer, mode: str, validate=None) -> None:
            """Run one detector pass over the CURRENT ``out`` and splice in tokens.

            Passes run earliest-priority first and rebuild ``out`` left-to-right. Later
            passes re-scan the rebuilt string; emitted ``<REDACTED:...>`` tokens don't
            re-match secret patterns, and the 8-hex hash inside them is shorter than the
            entropy candidate minimum, so there's no double-redaction to guard against.
            """
            nonlocal out, blocked
            matches = [
                m
                for m in finditer(out)
                if validate is None or validate(m.group(0))
            ]
            if not matches:
                return
            if mode == MODE_BLOCK:
                # Drop the entire field; count once per match and stop processing it.
                for _ in matches:
                    manifest.bump(category)
                    findings.append(
                        Finding(
                            category=category,
                            severity=_severity_for(category),
                            action=MODE_BLOCK,
                            excerpt=f"<REDACTED:{category}:blocked>",
                        )
                    )
                blocked = True
                return
            pieces: list[str] = []
            cursor = 0
            for m in matches:
                pieces.append(out[cursor : m.start()])
                raw = m.group(0)
                token = self._token(category, raw, mode)
                manifest.bump(category)
                findings.append(
                    Finding(
                        category=category,
                        severity=_severity_for(category),
                        action=mode,
                        # excerpt is signal-only: the stable token, never the raw value.
                        excerpt=token if mode != MODE_HASH else f"<{category}:{token}>",
                    )
                )
                pieces.append(token)
                cursor = m.end()
            pieces.append(out[cursor:])
            out = "".join(pieces)

        # 1) Registered exact secrets (verbatim) — highest priority.
        for value, category in self._registered.items():
            mode = self._mode_for(category)
            literal = re.compile(re.escape(value))
            _run_pass(category, literal.finditer, mode)
            if blocked:
                return FilterResult(text="", findings=findings, manifest=manifest, blocked=True)

        # 2) User rules.
        for rule in self._user_rules:
            mode = self._mode_for(rule.category, rule.mode)
            _run_pass(rule.category, rule.finditer, mode)
            if blocked:
                return FilterResult(text="", findings=findings, manifest=manifest, blocked=True)

        # 3) Optional Presidio NER — guarded; the [redaction] extra is not installed.
        self._maybe_presidio(out, manifest, findings)

        # 4) Built-in pattern detectors.
        for det in self._detectors:
            mode = self._mode_for(det.category)
            _run_pass(det.category, det.pattern.finditer, mode, validate=det.validate)
            if blocked:
                return FilterResult(text="", findings=findings, manifest=manifest, blocked=True)

        # 5) Generic high-entropy token pass (runs LAST; respects claimed spans).
        ent_mode = self._mode_for("HIGH_ENTROPY")

        def _entropy_finditer(s: str):
            for m in _ENTROPY_CANDIDATE.finditer(s):
                if shannon_entropy(m.group(0)) >= self._entropy_threshold:
                    yield m

        _run_pass("HIGH_ENTROPY", _entropy_finditer, ent_mode)
        if blocked:
            return FilterResult(text="", findings=findings, manifest=manifest, blocked=True)

        return FilterResult(text=out, findings=findings, manifest=manifest, blocked=False)

    # ── optional Presidio NER (extra not installed by default) ───────────────
    def _maybe_presidio(self, text, manifest, findings) -> None:
        """Use Presidio NER if the optional [redaction] extra is importable; else skip.

        Kept best-effort and silent — the default install has no presidio_analyzer, and a
        missing optional dependency must never break the redaction path.
        """
        try:  # pragma: no cover - optional dependency, not installed in CI
            from presidio_analyzer import AnalyzerEngine  # type: ignore
        except Exception:  # noqa: BLE001 - any import failure => skip NER silently
            return
        # If importable we *could* run it, but NER is heavyweight; only do so when the
        # caller opts in. Left as a guarded hook so the default path stays dependency-free.
        return  # pragma: no cover


# ── bulk / CPU-bound offload ─────────────────────────────────────────────────
def _redact_one(args: tuple[str, bytes, float]) -> str:
    """Top-level worker for the process pool (must be picklable / importable)."""
    text, salt, threshold = args
    flt = RedactionFilter(salt=salt, entropy_threshold=threshold)
    return flt.screen(text, direction=Direction.OUTBOUND).text


def redact_bulk(
    texts: list[str],
    *,
    salt: Optional[bytes] = None,
    entropy_threshold: float = _ENTROPY_THRESHOLD,
    max_workers: Optional[int] = None,
    min_offload_chars: int = 50_000,
) -> list[str]:
    """Redact a batch of texts, offloading to a :class:`ProcessPoolExecutor` when large.

    The per-line :meth:`RedactionFilter.screen` stays in-process (fast for normal text);
    this helper exists for big batch/bulk passes (e.g. re-scanning a large captured
    transcript) where the CPU cost is worth the pool spin-up. For small inputs we stay
    synchronous — spawning a pool for a few short strings is pure overhead.

    A shared ``salt`` is REQUIRED for stable tokens across the batch (each subprocess
    builds its own filter); when omitted we generate one so the batch is internally
    consistent, but tokens won't match a separate in-process filter.
    """
    if not texts:
        return []
    if salt is None:
        salt = os.urandom(16)

    total = sum(len(t) for t in texts)
    # Pragmatic: only pay for a process pool on genuinely large work.
    if total < min_offload_chars or len(texts) < 2:
        flt = RedactionFilter(salt=salt, entropy_threshold=entropy_threshold)
        return [flt.screen(t, direction=Direction.OUTBOUND).text for t in texts]

    from concurrent.futures import ProcessPoolExecutor

    payload = [(t, salt, entropy_threshold) for t in texts]
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(_redact_one, payload))
