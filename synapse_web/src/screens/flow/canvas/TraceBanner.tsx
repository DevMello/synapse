// Unified-trace banner (§11.11) — overlaid on the canvas while a chain runs. The baton
// lights up node-by-node (handled in FlowCanvas); this strip shows the run id, the active
// hop, and the one-click Halt / Revoke kill switches. In draft mode it flags the §10
// best-effort-simulation caveat.
import { Icon } from "../../../components/Primitives";

interface Props {
  draft: boolean;
  rootRunId: string;
  activeLabel?: string;
  hop: number;
  total: number;
  done: boolean;
  onHalt: () => void;
  onRevoke: () => void;
  onClose: () => void;
}

export default function TraceBanner({
  draft, rootRunId, activeLabel, hop, total, done, onHalt, onRevoke, onClose,
}: Props) {
  return (
    <div className={"fc-trace" + (draft ? " is-draft" : "")}>
      <span className="fc-trace-pip" aria-hidden />
      <div className="fc-trace-info">
        <span className="fc-trace-title">
          {draft ? "Draft run" : "Live chain"} · <span className="db-mono">{rootRunId}</span>
        </span>
        <span className="fc-trace-sub">
          {done ? "chain complete" : activeLabel ? `running ${activeLabel}` : "starting…"} · hop {hop}/{total}
        </span>
      </div>
      {draft && (
        <span className="fc-trace-caveat" title="Draft mode (§10.5)">
          <Icon name="info" size={12} /> side effects simulated
        </span>
      )}
      <div className="fc-trace-actions">
        {!done && (
          <button className="db-btn outline-light" onClick={onHalt}>
            <Icon name="octagon-x" size={13} /> Halt chain
          </button>
        )}
        <button className="db-btn outline-light" onClick={onRevoke}>
          <Icon name="ban" size={13} /> Revoke grant
        </button>
        <button className="fc-trace-x" onClick={onClose} title="Dismiss"><Icon name="x" size={14} /></button>
      </div>
    </div>
  );
}
