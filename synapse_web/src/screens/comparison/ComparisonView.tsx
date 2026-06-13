// Comparison screen (§10.12) — one column per model with output, cost, tokens, latency, the
// full tool-call list, the proposed-actions list, "would have paused for HITL" markers, and
// errors; a sortable summary (cheapest / fastest / fewest interventions); a side-by-side
// output diff; and winner selection → "Run winner for real" (E4). A banner notes draft
// mode's best-effort-simulation caveat (§10.5).
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button, Icon } from "../../components/Primitives";
import { PageHead, ScreenStub } from "../../components/Common";
import { useUI } from "../../store/ui";
import {
  useComparison,
  useCancelComparison,
  useSelectWinner,
  usePromoteWinner,
} from "../../api/queries";
import type { ComparisonVariant, RunGroup } from "../../types";
import "../../styles/comparison.css";

type SortKey = "model" | "cheapest" | "fastest" | "fewest";

export default function ComparisonView() {
  const { groupId } = useParams();
  const navigate = useNavigate();
  const showToast = useUI((s) => s.showToast);
  const { data: group, isLoading } = useComparison(groupId);
  const cancel = useCancelComparison();
  const selectWinner = useSelectWinner();
  const promote = usePromoteWinner();
  const [sort, setSort] = useState<SortKey>("model");
  const [showDiff, setShowDiff] = useState(false);

  if (isLoading) return <ScreenStub name="Comparison" note="Loading variants…" />;
  if (!group) return <ScreenStub name="Comparison" note="Comparison not found." />;

  const done = group.variants.filter((v) => v.status === "succeeded");
  const sorted = sortVariants(group.variants, sort);
  const winner = group.variants.find((v) => v.isWinner) ?? null;

  function pick(v: ComparisonVariant) {
    if (!groupId) return;
    selectWinner.mutate(
      { groupId, runId: v.runId },
      {
        onSuccess: () => showToast({ text: `${v.model} selected as winner` }),
        onError: (e) => showToast({ text: (e as Error).message, variant: "warn" }),
      },
    );
  }

  function runForReal() {
    if (!groupId) return;
    promote.mutate(groupId, {
      onSuccess: () => showToast({ text: "Winner queued for a live run" }),
      onError: (e) => showToast({ text: (e as Error).message, variant: "warn" }),
    });
  }

  return (
    <div className="db-screen">
      <PageHead
        kicker="Model Comparison"
        title="Compare"
        serif="Models"
        sub="One task, several models, side by side — in draft mode. Pick the winner, then optionally run it for real."
        actions={
          group.status === "running" ? (
            <Button variant="outline-light" icon="cloud-off" onClick={() => groupId && cancel.mutate(groupId)}>
              Cancel
            </Button>
          ) : winner ? (
            <Button variant="primary" icon="check-circle" onClick={runForReal} disabled={promote.isPending}>
              Run winner for real
            </Button>
          ) : undefined
        }
      />

      {/* ── draft-mode caveat (§10.5) ──────────────────────────────────── */}
      <div className="cmp-banner">
        <Icon name="shield-alert" size={16} />
        <span>
          <b>Draft mode.</b> Read-only tools ran for real; side-effecting + approval-gated calls
          were <b>simulated</b>, so once a model takes a simulated action the rest of its run is a
          best-effort simulation. To actually act, select a winner and <b>run it for real</b>.
        </span>
      </div>

      {/* ── summary / sort ─────────────────────────────────────────────── */}
      <div className="cmp-summary">
        <span className="cmp-summary-stat db-mono">
          <Icon name="dollar-sign" size={13} /> total ${group.totalCostUsd.toFixed(4)}
        </span>
        {done.length > 0 && (
          <>
            <Badge label="cheapest" value={best(done, (v) => v.costUsd, "min")?.model} />
            <Badge label="fastest" value={best(done, (v) => v.latencyMs ?? Infinity, "min")?.model} />
            <Badge label="fewest interventions" value={best(done, (v) => v.simulatedHitl.length, "min")?.model} />
          </>
        )}
        <span className="cmp-spacer" />
        <div className="cmp-sortbar">
          {(["model", "cheapest", "fastest", "fewest"] as SortKey[]).map((k) => (
            <button key={k} className={"cmp-sort" + (sort === k ? " on" : "")} onClick={() => setSort(k)}>
              {k}
            </button>
          ))}
          <button className={"cmp-sort" + (showDiff ? " on" : "")} onClick={() => setShowDiff((d) => !d)}>
            diff
          </button>
        </div>
      </div>

      {showDiff && <DiffPanel group={group} />}

      {/* ── per-model columns ──────────────────────────────────────────── */}
      <div className="cmp-cols">
        {sorted.map((v) => (
          <VariantColumn
            key={v.runId}
            v={v}
            isWinner={v.isWinner}
            canPick={group.status !== "running" && v.status === "succeeded"}
            onPick={() => pick(v)}
          />
        ))}
      </div>

      <button className="db-inline-link" style={{ marginTop: 18 }} onClick={() => navigate("/comparisons")}>
        <Icon name="arrow-left" size={13} /> All comparisons
      </button>
    </div>
  );
}

function VariantColumn({
  v, isWinner, canPick, onPick,
}: {
  v: ComparisonVariant;
  isWinner: boolean;
  canPick: boolean;
  onPick: () => void;
}) {
  return (
    <div className={"cmp-col" + (isWinner ? " winner" : "")}>
      <div className="cmp-col-head">
        <span className="cmp-col-model">{v.model}</span>
        <span className={"cmp-status cmp-status--" + v.status}>{v.status}</span>
      </div>

      <div className="cmp-metrics db-mono">
        <span><Icon name="dollar-sign" size={12} /> ${v.costUsd.toFixed(4)}</span>
        <span>{v.tokensIn}/{v.tokensOut} tok</span>
        <span>{v.latencyMs != null ? `${(v.latencyMs / 1000).toFixed(1)}s` : "—"}</span>
      </div>

      <div className="cmp-section-label">Output</div>
      <div className="cmp-output">{v.output || (v.error ? "" : "—")}</div>
      {v.error && (
        <div className="cmp-error db-mono"><Icon name="alert-triangle" size={12} /> {v.error}</div>
      )}

      {v.proposedActions.length > 0 && (
        <>
          <div className="cmp-section-label">Proposed actions <span className="cmp-count">{v.proposedActions.length}</span></div>
          <ul className="cmp-actions">
            {v.proposedActions.map((a, i) => (
              <li key={i} className={a.hitl ? "hitl" : ""}>
                <Icon name={a.hitl ? "shield-alert" : "circle-dot"} size={12} />
                <code>{a.name}</code>
                {a.hitl && <span className="cmp-tag">would pause</span>}
              </li>
            ))}
          </ul>
        </>
      )}

      {v.simulatedHitl.length > 0 && (
        <div className="cmp-hitl db-mono">
          <Icon name="shield-alert" size={12} /> {v.simulatedHitl.length} human-intervention point
          {v.simulatedHitl.length === 1 ? "" : "s"}
        </div>
      )}

      {v.toolCalls.length > 0 && (
        <div className="cmp-toolcalls db-mono db-muted">
          {v.toolCalls.length} tool call{v.toolCalls.length === 1 ? "" : "s"} ·{" "}
          {v.toolCalls.filter((t) => !t.simulated).length} ran ·{" "}
          {v.toolCalls.filter((t) => t.simulated).length} simulated
        </div>
      )}

      <div className="cmp-col-foot">
        {isWinner ? (
          <span className="cmp-winner-badge"><Icon name="check-circle" size={14} /> winner</span>
        ) : canPick ? (
          <Button variant="outline-light" icon="check-circle" onClick={onPick}>Select winner</Button>
        ) : null}
      </div>
    </div>
  );
}

// ── side-by-side output diff (first two variants, naive line compare) ─────────
function DiffPanel({ group }: { group: RunGroup }) {
  const [a, b] = useMemo(() => pickTwo(group.variants), [group.variants]);
  if (!a || !b) return null;
  const linesA = a.output.split("\n");
  const linesB = b.output.split("\n");
  const setB = new Set(linesB.map((l) => l.trim()));
  const setA = new Set(linesA.map((l) => l.trim()));
  return (
    <div className="cmp-diff">
      <div className="cmp-diff-col">
        <div className="cmp-diff-head">{a.model}</div>
        {linesA.map((l, i) => (
          <div key={i} className={"cmp-diff-line" + (setB.has(l.trim()) ? "" : " changed")}>{l || " "}</div>
        ))}
      </div>
      <div className="cmp-diff-col">
        <div className="cmp-diff-head">{b.model}</div>
        {linesB.map((l, i) => (
          <div key={i} className={"cmp-diff-line" + (setA.has(l.trim()) ? "" : " changed")}>{l || " "}</div>
        ))}
      </div>
    </div>
  );
}

// ── helpers ───────────────────────────────────────────────────────────────────
function sortVariants(variants: ComparisonVariant[], key: SortKey): ComparisonVariant[] {
  const v = [...variants];
  if (key === "cheapest") return v.sort((x, y) => x.costUsd - y.costUsd);
  if (key === "fastest") return v.sort((x, y) => (x.latencyMs ?? Infinity) - (y.latencyMs ?? Infinity));
  if (key === "fewest") return v.sort((x, y) => x.simulatedHitl.length - y.simulatedHitl.length);
  return v;
}

function best(
  variants: ComparisonVariant[],
  metric: (v: ComparisonVariant) => number,
  dir: "min" | "max",
): ComparisonVariant | undefined {
  if (variants.length === 0) return undefined;
  return variants.reduce((acc, v) =>
    dir === "min" ? (metric(v) < metric(acc) ? v : acc) : (metric(v) > metric(acc) ? v : acc),
  );
}

function pickTwo(variants: ComparisonVariant[]): [ComparisonVariant?, ComparisonVariant?] {
  const done = variants.filter((v) => v.status === "succeeded");
  return [done[0], done[1]];
}

function Badge({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <span className="cmp-badge">
      <span className="cmp-badge-l">{label}</span>
      <span className="cmp-badge-v">{value}</span>
    </span>
  );
}
