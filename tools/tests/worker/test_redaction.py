"""Layer A redaction tests (§4.5) — self-contained, no network.

The conftest resets the shared filter chain per-test, so these construct/register the
filter EXPLICITLY rather than relying on the ``redaction_boot`` import side-effect.
"""
from __future__ import annotations

import re

import pytest

from synapse_worker.filtering.base import (
    Direction,
    FilterChain,
    Severity,
    get_filter_chain,
)
from synapse_worker.filtering.redaction import (
    MODE_BLOCK,
    MODE_HASH,
    RedactionFilter,
    redact_bulk,
    shannon_entropy,
)

# A fixed salt makes token suffixes deterministic across the test (the production default
# is a per-process random salt; we pin it only so assertions can hard-code expected forms).
SALT = b"unit-test-salt-0"


def _flt(**kw) -> RedactionFilter:
    return RedactionFilter(salt=SALT, **kw)


TOKEN_RE = re.compile(r"<REDACTED:[A-Z_]+:[0-9a-f]{8}>")


# ── per-secret-type detection ────────────────────────────────────────────────
@pytest.mark.parametrize(
    "category, secret",
    [
        ("AWS_KEY", "AKIAIOSFODNN7EXAMPLE"),
        ("API_KEY", "sk-proj-abc123DEF456ghi789JKL012mno345"),
        ("GITHUB_TOKEN", "ghp_" + "a1B2c3D4e5F6g7H8i9J0" + "kLmNoPqRsTuVwXyZ0123"),
        (
            "JWT",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N",
        ),
        ("EMAIL", "alice.smith@example.com"),
        ("IP", "192.168.13.37"),
    ],
)
def test_each_secret_type_is_masked(category, secret):
    flt = _flt()
    text = f"prefix {secret} suffix"
    res = flt.screen(text, direction=Direction.OUTBOUND)
    assert secret not in res.text, f"{category} raw value leaked"
    assert TOKEN_RE.search(res.text)
    assert res.manifest.counts.get(category, 0) >= 1
    assert any(f.category == category for f in res.findings)


def test_pem_private_key_block_masked():
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQ\n"
        "abcdef====\n"
        "-----END RSA PRIVATE KEY-----"
    )
    res = _flt().screen(f"key:\n{pem}\ndone", direction=Direction.OUTBOUND)
    assert "PRIVATE KEY" not in res.text
    assert "MIIEvQ" not in res.text
    assert res.manifest.counts.get("PRIVATE_KEY", 0) == 1


# ── stable salting ───────────────────────────────────────────────────────────
def test_same_secret_same_token():
    flt = _flt()
    secret = "AKIAIOSFODNN7EXAMPLE"
    a = flt.screen(f"a {secret}").text
    b = flt.screen(f"b {secret} again {secret}").text
    tok_a = TOKEN_RE.search(a).group(0)
    toks_b = TOKEN_RE.findall(b)
    assert tok_a == toks_b[0] == toks_b[1]  # same value -> same token everywhere


def test_different_salt_different_token():
    s = "AKIAIOSFODNN7EXAMPLE"
    t1 = RedactionFilter(salt=b"salt-one").screen(s).text
    t2 = RedactionFilter(salt=b"salt-two").screen(s).text
    assert TOKEN_RE.search(t1).group(0) != TOKEN_RE.search(t2).group(0)


# ── non-secrets untouched ────────────────────────────────────────────────────
def test_plain_text_untouched():
    res = _flt().screen("hello world", direction=Direction.OUTBOUND)
    assert res.text == "hello world"
    assert res.findings == []
    assert res.manifest.total == 0


def test_ordinary_prose_not_over_redacted():
    prose = (
        "The quick brown fox jumps over the lazy dog while the committee "
        "reviewed the quarterly financial projections in great detail."
    )
    res = _flt().screen(prose, direction=Direction.OUTBOUND)
    assert res.text == prose
    assert res.manifest.total == 0


# ── credit card: Luhn gating ─────────────────────────────────────────────────
def test_valid_card_masked():
    # 4242 4242 4242 4242 is a Luhn-valid test card.
    res = _flt().screen("card 4242424242424242 end", direction=Direction.OUTBOUND)
    assert "4242424242424242" not in res.text
    assert res.manifest.counts.get("CARD", 0) == 1


def test_invalid_16_digits_not_flagged_as_card():
    # 1234567890123456 fails Luhn -> must NOT be a CARD finding.
    res = _flt().screen("num 1234567890123456 end", direction=Direction.OUTBOUND)
    assert res.manifest.counts.get("CARD", 0) == 0


# ── high-entropy generic token ───────────────────────────────────────────────
def test_high_entropy_token_masked():
    token = "Zk9xQ2pWb1RmN2hLc1JtYldlUmF6UThuVGc4eUxk"  # 40-char random-ish base64
    assert shannon_entropy(token) >= 4.0
    res = _flt().screen(f"opaque {token} blob", direction=Direction.OUTBOUND)
    assert token not in res.text
    assert res.manifest.counts.get("HIGH_ENTROPY", 0) == 1


# ── modes ────────────────────────────────────────────────────────────────────
def test_block_mode_sets_blocked():
    flt = _flt(category_modes={"AWS_KEY": MODE_BLOCK})
    res = flt.screen("leak AKIAIOSFODNN7EXAMPLE here", direction=Direction.OUTBOUND)
    assert res.blocked is True
    assert res.text == ""  # whole field dropped
    assert res.manifest.counts.get("AWS_KEY", 0) >= 1


def test_hash_mode_emits_bare_hash():
    flt = _flt(category_modes={"AWS_KEY": MODE_HASH})
    res = flt.screen("v AKIAIOSFODNN7EXAMPLE", direction=Direction.OUTBOUND)
    assert "AKIAIOSFODNN7EXAMPLE" not in res.text
    assert "<REDACTED:" not in res.text  # hash mode = bare hex, no wrapper
    assert re.search(r"\bv [0-9a-f]{8}$", res.text)


# ── registered secrets ───────────────────────────────────────────────────────
def test_register_secret_masks_verbatim_echo():
    flt = _flt()
    flt.register_secret("hunter2-the-db-password", category="ENV")
    res = flt.screen("DB_PASS=hunter2-the-db-password loaded", direction=Direction.OUTBOUND)
    assert "hunter2-the-db-password" not in res.text
    assert res.manifest.counts.get("ENV", 0) == 1


def test_register_secret_ignores_tiny_values():
    flt = _flt()
    flt.register_secret("ab")  # too short to register
    res = flt.screen("ab cd ab", direction=Direction.OUTBOUND)
    assert res.text == "ab cd ab"


# ── user rules ───────────────────────────────────────────────────────────────
def test_user_regex_rule():
    flt = _flt()
    flt.add_rule(category="INTERNAL_ID", regex=r"EMP-\d{6}")
    res = flt.screen("employee EMP-004217 record", direction=Direction.OUTBOUND)
    assert "EMP-004217" not in res.text
    assert res.manifest.counts.get("INTERNAL_ID", 0) == 1


def test_user_keyword_rule():
    flt = _flt()
    flt.add_rule(category="CODEWORD", keyword="bluebird")
    res = flt.screen("operation bluebird is go", direction=Direction.OUTBOUND)
    assert "bluebird" not in res.text
    assert res.manifest.counts.get("CODEWORD", 0) == 1


# ── direction coverage ───────────────────────────────────────────────────────
def test_redacts_inbound_direction_too():
    res = _flt().screen("inbound AKIAIOSFODNN7EXAMPLE", direction=Direction.INBOUND)
    assert "AKIAIOSFODNN7EXAMPLE" not in res.text


# ── findings never carry raw values ──────────────────────────────────────────
def test_findings_have_no_raw_value():
    secret = "AKIAIOSFODNN7EXAMPLE"
    res = _flt().screen(f"x {secret}")
    for f in res.findings:
        assert secret not in f.excerpt
        assert secret not in str(f.detail)
    assert all(isinstance(f.severity, Severity) for f in res.findings)


# ── chain integration ────────────────────────────────────────────────────────
def test_integrates_into_filter_chain():
    chain = FilterChain()
    chain.register(_flt())
    out = chain.screen_outbound("token sk-proj-abc123DEF456ghi789JKL012mno345 sent")
    assert "sk-proj-abc123DEF456ghi789JKL012mno345" not in out.text
    assert out.manifest.total >= 1


def test_boot_module_registers_into_global_chain():
    # The boot import respects redaction_enabled; in test mode it's True by default.
    import importlib

    from synapse_worker.commands import redaction_boot

    importlib.reload(redaction_boot)
    names = [f.name for f in get_filter_chain().filters]
    assert "redaction" in names
    # Idempotent: reloading must not double-register.
    importlib.reload(redaction_boot)
    assert names.count("redaction") == [f.name for f in get_filter_chain().filters].count("redaction")


# ── bulk offload helper ──────────────────────────────────────────────────────
def test_redact_bulk_small_inputs_stay_in_process():
    texts = ["plain one", "leak AKIAIOSFODNN7EXAMPLE", "plain three"]
    out = redact_bulk(texts, salt=SALT)
    assert out[0] == "plain one"
    assert "AKIAIOSFODNN7EXAMPLE" not in out[1]
    assert out[2] == "plain three"


def test_redact_bulk_empty():
    assert redact_bulk([]) == []
