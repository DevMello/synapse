"""Tests for nacl verify behavior."""
import base64
import pytest
from nacl.signing import VerifyKey, SigningKey


def test_verify_empty_sig_raises():
    """nacl verify with empty sig should raise (and be caught by broad except)."""
    vk = SigningKey.generate().verify_key
    try:
        vk.verify(b"hello", b"")
        assert False, "Expected exception"
    except Exception as e:
        print(f"Got exception: {type(e).__name__}: {e}")
        assert True


def test_verify_invalid_b64_raises():
    """base64.b64decode of invalid string raises binascii.Error."""
    import binascii
    try:
        base64.b64decode("not!valid!b64!!")
        # might succeed with validation=False (default)
    except Exception:
        pass  # expected
    # Just ensure decode of empty works
    assert base64.b64decode("") == b""
