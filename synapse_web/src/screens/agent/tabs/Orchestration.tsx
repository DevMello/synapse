// Agent Detail — Orchestration tab (possible-features §2). Mint/revoke the agent's
// signed orchestration grants (elevated consent), and view the lineage of runs it has
// initiated on its daemon. Reads come from Supabase (RLS); mint/revoke go through the
// Cloud Backend (it signs the grant). All `.db-*` design classes are reused.
import { useState } from "react";
import { Icon, Button, Chip } from "../../../components/Primitives";
import { useCurrentAgent } from "../context";
import {
  useOrchestrationGrants,
  useMintGrant,
  useRevokeGrant,
  useAgentLineage,
} from "../../../api/queries";
import { useUI } from "../../../store/ui";
import type { Grant, GrantVerb, RunLineage } from "../../../types";

const ALL_VERBS: GrantVerb[] = ["run", "create", "edit"];

export default function OrchestrationTab() {
  const agent = useCurrentAgent();
  const showToast = useUI((s) => s.showToast);
  const { data: grants = [] } = useOrchestrationGrants(agent.id);
  const { data: lineage = [] } = useAgentLineage(agent.id);
  const mint = useMintGrant(agent.id);
  const revoke = useRevokeGrant(agent.id);

  const [verbs, setVerbs] = useState<Set<GrantVerb>>(new Set(["run"]));
  const [targets, setTargets] = useState("");
  const [maxDepth, setMaxDepth] = useState(3);
  const [maxFanOut, setMaxFanOut] = useState(5);
  const [budget, setBudget] = useState(10);
  const [expiresHours, setExpiresHours] = useState(24);
  const [confirming, setConfirming] = useState(false);

  function toggleVerb(v: GrantVerb) {
    setVerbs((prev) => {
      const next = new Set(prev);
      next.has(v) ? next.delete(v) : next.add(v);
      if (next.size === 0) next.add("run");
      return next;
    });
  }

  function doMint() {
    const targetAllow = targets.split(",").map((t) => t.trim()).filter(Boolean);
    mint.mutate(
      {
        verbs: [...verbs],
        targetAllow,
        maxDepth,
        maxFanOut,
        treeBudgetUsd: budget,
        expiresInSeconds: Math.max(60, expiresHours * 3600),
      },
      {
        onSuccess: () => showToast({ text: "Orchestration grant minted" }),
        onError: (e) => showToast({ text: (e as Error).message, variant: "warn" }),
      },
    );
    setConfirming(false);
  }

  function doRevoke(g: Grant) {
    revoke.mutate(
      { grantId: g.id },
      {
        onSuccess: () => showToast({ text: "Grant revoked — tree halted", variant: "warn" }),
        onError: (e) => showToast({ text: (e as Error).message, variant: "warn" }),
      },
    );
  }

  return (
    <div className="db-tools">
      <div className="db-callout">
        <Icon name="shield-alert" size={16} />
        <span>
          <b>Elevated grant.</b> A signed, attenuated grant lets <b>{agent.name}</b> run other
          agents <b>on its own daemon</b>, within these bounds. The daemon verifies and enforces
          it locally; <b>create/edit</b> always require a human approval. Revoke halts the tree.
        </span>
      </div>

      {/* ── mint a grant ─────────────────────────────────────────────── */}
      <div className="db-panel">
        <div className="db-panel-head"><h3 className="db-panel-title">Mint a grant</h3></div>
        <div className="db-ov-facts">
          <div className="db-ov-fact">
            <span className="db-ov-fact-l">Verbs</span>
            <span style={{ display: "flex", gap: 8 }}>
              {ALL_VERBS.map((v) => (
                <button
                  key={v}
                  className={"db-role-pill " + (verbs.has(v) ? "operator" : "viewer")}
                  style={{ border: "none", cursor: "pointer" }}
                  onClick={() => toggleVerb(v)}
                >
                  {v}
                </button>
              ))}
            </span>
          </div>
          <div className="db-ov-fact">
            <span className="db-ov-fact-l">Target allow</span>
            <input className="db-input" style={{ marginBottom: 0, width: 260 }}
              placeholder="agent ids / * (comma-separated)"
              value={targets} onChange={(e) => setTargets(e.target.value)} />
          </div>
          <div className="db-ov-fact">
            <span className="db-ov-fact-l">Max depth</span>
            <input className="db-input" type="number" style={{ marginBottom: 0, width: 90 }}
              value={maxDepth} onChange={(e) => setMaxDepth(Number(e.target.value))} />
          </div>
          <div className="db-ov-fact">
            <span className="db-ov-fact-l">Max fan-out</span>
            <input className="db-input" type="number" style={{ marginBottom: 0, width: 90 }}
              value={maxFanOut} onChange={(e) => setMaxFanOut(Number(e.target.value))} />
          </div>
          <div className="db-ov-fact">
            <span className="db-ov-fact-l">Tree budget ($)</span>
            <input className="db-input" type="number" style={{ marginBottom: 0, width: 90 }}
              value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
          </div>
          <div className="db-ov-fact">
            <span className="db-ov-fact-l">Expires (hours)</span>
            <input className="db-input" type="number" style={{ marginBottom: 0, width: 90 }}
              value={expiresHours} onChange={(e) => setExpiresHours(Number(e.target.value))} />
          </div>
        </div>
        {confirming ? (
          <div className="db-callout" style={{ marginTop: 10 }}>
            <Icon name="alert-triangle" size={16} />
            <span style={{ flex: 1 }}>
              This lets software act as you within these limits. Mint the grant?
            </span>
            <Button variant="primary" icon="check" onClick={doMint}>Confirm</Button>
            <Button variant="outline-light" onClick={() => setConfirming(false)}>Cancel</Button>
          </div>
        ) : (
          <div style={{ marginTop: 10 }}>
            <Button variant="primary" icon="shield" onClick={() => setConfirming(true)}>
              Mint grant
            </Button>
          </div>
        )}
      </div>

      {/* ── existing grants ──────────────────────────────────────────── */}
      <div className="db-panel">
        <div className="db-panel-head"><h3 className="db-panel-title">Grants {grants.length}</h3></div>
        <div className="db-table-wrap">
          <table className="db-table">
            <thead>
              <tr><th>Verbs</th><th>Targets</th><th>Limits</th><th>Expires</th><th>Status</th><th></th></tr>
            </thead>
            <tbody>
              {grants.length === 0 && (
                <tr><td colSpan={6} className="db-mono db-muted" style={{ padding: 12 }}>No grants yet.</td></tr>
              )}
              {grants.map((g) => (
                <tr key={g.id}>
                  <td className="db-mono">{g.verbs.join(", ")}</td>
                  <td className="db-mono db-muted">{g.targetAllow.join(", ") || "—"}</td>
                  <td className="db-mono db-muted">d{g.maxDepth}·f{g.maxFanOut}·${g.treeBudgetUsd}</td>
                  <td className="db-mono db-muted">{g.expiresAt}</td>
                  <td>
                    <span className={"db-role-pill " + (g.revoked ? "viewer" : "operator")}>
                      {g.revoked ? "revoked" : "active"}
                    </span>
                  </td>
                  <td>
                    {!g.revoked && (
                      <button className="db-icon-mini danger" title="Revoke + halt tree" onClick={() => doRevoke(g)}>
                        <Icon name="octagon-x" size={15} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── lineage tree ─────────────────────────────────────────────── */}
      <div className="db-panel">
        <div className="db-panel-head"><h3 className="db-panel-title">Orchestration lineage</h3></div>
        {lineage.length === 0 ? (
          <div className="db-mono db-muted" style={{ padding: 12 }}>
            No agent-initiated runs yet.
          </div>
        ) : (
          <div>{lineage.map((n) => <LineageNode key={n.run.id} node={n} depth={0} />)}</div>
        )}
      </div>
    </div>
  );
}

function LineageNode({ node, depth }: { node: RunLineage; depth: number }) {
  const r = node.run;
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", paddingLeft: 12 + depth * 22, borderTop: "1px solid rgba(0,0,0,0.06)" }}>
        <Icon name={node.children.length ? "git-branch" : "activity"} size={14} />
        <span className="db-cell-primary" style={{ minWidth: 120 }}>{r.agent}</span>
        <Chip s={r.status} />
        <span className="db-mono db-muted" style={{ fontSize: 12 }}>depth {r.depth} · {r.started} · ${r.cost.toFixed(2)}</span>
      </div>
      {node.children.map((c) => <LineageNode key={c.run.id} node={c} depth={depth + 1} />)}
    </>
  );
}
