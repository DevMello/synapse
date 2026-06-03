"""skill.install handler tests (§4.2 / §4.3)."""
from __future__ import annotations

import importlib

import synapse_worker.commands.skills as skills_cmd
from synapse_worker.commands.skills import handle_skill_install
from synapse_worker.paths import get_paths
from synapse_worker.router import CommandContext, known_commands


async def test_skill_install_writes_versioned_file(store, settings):
    get_paths().ensure_layout()
    await handle_skill_install(
        CommandContext(command_type="skill.install"),
        {"agent_id": "agt_1", "name": "triage", "content": "# How to triage", "version": 2},
    )
    target = get_paths().agent_dir("agt_1") / "skills" / "triage.md"
    assert target.is_file()
    assert target.read_text(encoding="utf-8") == "# How to triage"


async def test_skill_install_agent_from_idempotency_key(store, settings):
    get_paths().ensure_layout()
    await handle_skill_install(
        CommandContext(
            command_type="skill.install",
            idempotency_key="skill.install:agt_9:summarize",
        ),
        {"name": "summarize.toml", "content": "x = 1"},
    )
    assert (get_paths().agent_dir("agt_9") / "skills" / "summarize.toml").is_file()


async def test_skill_install_missing_fields_is_noop(store, settings):
    # No crash, nothing written.
    await handle_skill_install(CommandContext(command_type="skill.install"), {"name": "x"})


def test_skill_install_registered():
    importlib.reload(skills_cmd)
    assert "skill.install" in known_commands()
