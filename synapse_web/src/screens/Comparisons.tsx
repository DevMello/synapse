// Model Comparison library (§10.12) — every "Compare models" run group appears here as a
// single expandable entry. Open one to see the per-model columns + winner selection.
import { useNavigate } from "react-router-dom";
import { Icon } from "../components/Primitives";
import { PageHead } from "../components/Common";
import { useComparisons } from "../api/queries";
import type { RunGroup } from "../types";
import "../styles/comparison.css";

export default function Comparisons() {
  const navigate = useNavigate();
  const { data: groups = [], isLoading } = useComparisons();

  return (
    <div className="db-screen">
      <PageHead
        kicker="Model Comparison Runs"
        title="Compare"
        serif="Models"
        sub="Evaluate how different models handle the same task — side by side, in draft mode. Launch a comparison from any API agent's Compare tab."
      />
      {isLoading ? (
        <div className="db-mono db-muted" style={{ padding: 16 }}>Loading comparisons…</div>
      ) : groups.length === 0 ? (
        <div className="cmp-empty">
          <Icon name="git-pull-request" size={26} />
          <p>No comparisons yet — open an API agent and use the <b>Compare</b> tab.</p>
        </div>
      ) : (
        <div className="cmp-lib">
          {groups.map((g) => (
            <GroupCard key={g.id} group={g} onOpen={() => navigate(`/comparisons/${g.id}`)} />
          ))}
        </div>
      )}
    </div>
  );
}

function GroupCard({ group, onOpen }: { group: RunGroup; onOpen: () => void }) {
  const winner = group.variants.find((v) => v.isWinner);
  return (
    <div className="cmp-libcard" onClick={onOpen}>
      <div className="cmp-libcard-head">
        <span className={"cmp-status cmp-status--" + group.status}>{group.status.replace(/_/g, " ")}</span>
        <span className="cmp-libcard-time db-mono">{group.created}</span>
      </div>
      <div className="cmp-libcard-models">
        {group.models.map((m, i) => (
          <span key={i} className={"cmp-chip" + (winner?.model === m ? " win" : "")}>{m}</span>
        ))}
      </div>
      <div className="cmp-libcard-foot db-mono db-muted">
        <span>{group.variants.length} variants</span>
        <span><Icon name="dollar-sign" size={12} /> ${group.totalCostUsd.toFixed(4)}</span>
        {winner && <span className="cmp-libcard-winner"><Icon name="check-circle" size={12} /> {winner.model}</span>}
      </div>
    </div>
  );
}
