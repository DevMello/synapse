"""Model Comparison Runs (possible-features §10).

A human launches a one-off "Compare models" run that executes ONE agent task across several
models in parallel as a *run group* of *variants*. Every variant is an ordinary run wrapped
in **draft mode** (:mod:`.draft_shim`): read-only tools run for real; side-effecting + HITL
tools are simulated and recorded so nothing real happens during the comparison (E3). The
:mod:`.executor` fans the variants out (bounded concurrency, group cost cap), tags telemetry
with ``run_group_id`` / ``variant_model``, and streams results up for the human to review and
pick a winner — which can then be re-run live (E4). API agents only in v1 (E5).
"""
