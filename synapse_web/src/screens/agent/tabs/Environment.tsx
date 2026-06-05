// Synapse Web UI — Agent Detail · Environment tab. E2E-encrypted env vars: a
// KEY/VALUE table per agent. Secret rows are write-only (masked, never read back);
// plain rows show their value. Locally-set vars (origin 'local') are read-only.
// Ported from the prototype's EnvTab (design-reference/app/AgentTabs2.jsx).
import { useEffect, useState } from "react";
import { Icon, Button } from "../../../components/Primitives";
import { daemonName } from "../../../components/Common";
import { useUI } from "../../../store/ui";
import { useCurrentAgent } from "../context";
import { useEnvVars } from "../../../api/queries";
import type { EnvVar } from "../../../types";

export default function EnvironmentTab() {
  const agent = useCurrentAgent();
  const { data: envVars = [] } = useEnvVars();
  const showToast = useUI((s) => s.showToast);

  // Local working copy seeded from the query; add/overwrite/delete mutate it.
  // useEnvVars() resolves async (data is [] on first render), so adopt the
  // resolved seed when it arrives.
  const [vars, setVars] = useState<EnvVar[]>(envVars);
  useEffect(() => {
    setVars(envVars);
  }, [envVars]);
  const [adding, setAdding] = useState(false);
  const [k, setK] = useState("");
  const [v, setV] = useState("");
  const [secret, setSecret] = useState(true);

  const host = daemonName(agent.daemonId);

  function save() {
    if (!k.trim()) return;
    const key = k.toUpperCase().replace(/[^A-Z0-9_]/g, "_");
    setVars((vs) => [
      { key, secret, value: secret ? undefined : v, origin: "cloud", updated: "just now", by: "AK" },
      ...vs,
    ]);
    showToast(`${key} encrypted to ${host} · cloud never sees it`);
    setAdding(false);
    setK("");
    setV("");
    setSecret(true);
  }

  return (
    <div className="db-env">
      <div className="db-callout">
        <Icon name="lock" size={16} />
        <span>
          <b>End-to-end encrypted.</b> Secret values are sealed in your browser to{" "}
          <span className="db-mono">{host}</span>'s public key and relayed as opaque ciphertext. The
          cloud can't read them — and neither can this UI once saved. You can overwrite or delete,
          never view.
        </span>
      </div>

      <div className="db-section-row">
        <h2 className="db-h2">
          Variables <span className="db-count db-mono">{vars.length}</span>
        </h2>
        <div className="db-section-actions">
          <Button variant="outline-light" icon="upload" onClick={() => showToast("Paste / import a .env file")}>
            Import .env
          </Button>
          <Button variant="primary" icon="plus" onClick={() => setAdding(true)}>
            Add variable
          </Button>
        </div>
      </div>

      <div className="db-table-wrap">
        <table className="db-table db-env-table">
          <thead>
            <tr>
              <th>Key</th>
              <th>Value</th>
              <th>Origin</th>
              <th>Updated</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {adding && (
              <tr className="db-env-add">
                <td>
                  <input
                    className="db-input-sm db-mono"
                    autoFocus
                    placeholder="KEY"
                    value={k}
                    onChange={(e) => setK(e.target.value)}
                  />
                </td>
                <td>
                  <input
                    className="db-input-sm db-mono"
                    type={secret ? "password" : "text"}
                    placeholder={secret ? "secret value" : "value"}
                    value={v}
                    onChange={(e) => setV(e.target.value)}
                  />
                </td>
                <td colSpan={2}>
                  <label className="db-secret-check">
                    <input type="checkbox" checked={secret} onChange={(e) => setSecret(e.target.checked)} /> secret
                    (write-only)
                  </label>
                </td>
                <td>
                  <div className="db-env-add-actions">
                    <button className="db-mini-btn primary" onClick={save}>
                      Save
                    </button>
                    <button className="db-mini-btn" onClick={() => setAdding(false)}>
                      Cancel
                    </button>
                  </div>
                </td>
              </tr>
            )}
            {vars.map((vr, i) => (
              <tr key={vr.key + i} className={vr.origin === "local" ? "db-env-local" : ""}>
                <td className="db-cell-primary db-mono">{vr.key}</td>
                <td className="db-mono">
                  {vr.origin === "local" ? (
                    <span className="db-muted">set on daemon</span>
                  ) : vr.secret ? (
                    <span className="db-secret-mask db-mono">
                      <Icon name="lock" size={11} /> •••••••••••• <span className="db-writeonly">write-only</span>
                    </span>
                  ) : (
                    <span>{vr.value}</span>
                  )}
                </td>
                <td>
                  <span className={"db-origin-pill " + vr.origin}>{vr.origin === "local" ? "set locally" : "cloud"}</span>
                </td>
                <td className="db-mono db-muted">
                  {vr.updated}
                  {vr.by && vr.by !== "—" && " · " + vr.by}
                </td>
                <td>
                  {vr.origin !== "local" && (
                    <div className="db-env-row-actions">
                      <button
                        className="db-icon-mini"
                        title="Overwrite"
                        onClick={() => showToast(`Overwrite ${vr.key}`)}
                      >
                        <Icon name="pencil" size={14} />
                      </button>
                      <button
                        className="db-icon-mini danger"
                        title="Delete"
                        onClick={() => {
                          setVars((vs) => vs.filter((x) => x !== vr));
                          showToast({ text: `${vr.key} deleted`, variant: "warn" });
                        }}
                      >
                        <Icon name="trash" size={14} />
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="db-env-foot db-mono">
        <span>
          <Icon name="key" size={12} /> Locally-set vars (<span className="db-muted">synapse env set</span>) show as
          read-only — the UI can't expose their values.
        </span>
      </div>
    </div>
  );
}
