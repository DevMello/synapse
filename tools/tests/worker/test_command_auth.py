"""Tests for nonce rowcount behavior and command_auth module."""
import asyncio
import pytest
import pytest_asyncio
import aiosqlite


@pytest.mark.asyncio
async def test_insert_or_ignore_rowcount():
    """Verify aiosqlite INSERT OR IGNORE rowcount is 1 on insert, 0 on duplicate."""
    db = await aiosqlite.connect(":memory:")
    await db.execute(
        "CREATE TABLE seen_nonces (nonce TEXT PRIMARY KEY, expires_at TEXT NOT NULL, stored_at REAL NOT NULL)"
    )
    cur = await db.execute(
        "INSERT OR IGNORE INTO seen_nonces VALUES (?, ?, ?)", ("abc", "2099-01-01", 1.0)
    )
    first = cur.rowcount
    cur2 = await db.execute(
        "INSERT OR IGNORE INTO seen_nonces VALUES (?, ?, ?)", ("abc", "2099-01-01", 1.0)
    )
    second = cur2.rowcount
    await db.close()
    assert first == 1, f"Expected 1, got {first}"
    assert second == 0, f"Expected 0 for duplicate, got {second}"
