// Elevated-grant consent (§11.11 "publish = sign the chain grant"; shared with §2). A
// plain-language risk screen shown before a flow compiles into a signed chain grant.
import { useState } from "react";
import { Icon } from "../../../components/Primitives";
import type { AgentFlow } from "../../../types";

interface Props {
  flow: AgentFlow;
  edgeCount: number;
  publishing: boolean;
  onConfirm: (expiresHours: number) => void;
  onCancel: () => void;
}

export default function ConsentModal({ flow, edgeCount, publishing, onConfirm, onCancel }: Props) {
  const [hours, setHours] = useState(24);
  return (
    <div className="fc-modal-scrim" onPointerDown={onCancel}>
      <div className="fc-modal" onPointerDown={(e) => e.stopPropagation()}>
        <div className="fc-modal-head">
          <span className="fc-modal-ico"><Icon name="shield-alert" size={18} /></span>
          <h3>Publish &amp; sign the chain grant</h3>
        </div>
        <p className="fc-modal-body">
          Publishing compiles <b>{flow.name}</b> into a <b>cloud-signed chain grant</b> — the
          immutable security artifact the daemon verifies and enforces locally. This authorises{" "}
          <b>{edgeCount} handoff {edgeCount === 1 ? "edge" : "edges"}</b> to move work between these
          agents <b>on one daemon</b>, within {flow.settings.maxHops} hops and a{" "}
          ${flow.settings.chainBudgetUsd} shared budget. Agents gain <b>no new permissions</b> —
          a handoff transfers work, not authority.
        </p>
        <div className="fc-modal-facts">
          <div><span>Routing</span><b>one path per hop (no fan-out)</b></div>
          <div><span>Payload</span><b>Layer-A redacted · ≤ {flow.settings.maxPayloadBytes.toLocaleString()} B</b></div>
          <div className="fc-modal-expiry">
            <span>Expires in</span>
            <input className="db-input" type="number" min={1} value={hours}
              onChange={(e) => setHours(Math.max(1, Number(e.target.value)))} /> hours
          </div>
        </div>
        <div className="fc-modal-actions">
          <button className="db-btn outline-light" onClick={onCancel} disabled={publishing}>Cancel</button>
          <button className="db-btn primary" onClick={() => onConfirm(hours)} disabled={publishing}>
            <Icon name="check" size={14} /> {publishing ? "Signing…" : "Sign & publish"}
          </button>
        </div>
      </div>
    </div>
  );
}
