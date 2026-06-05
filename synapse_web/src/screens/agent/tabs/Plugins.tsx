// Agent Detail — Plugins tab (capability packs). The agent tier of the two-tier
// model: a pack is provisioned once on the host daemon (§4.2), then attached to an
// agent here — instant, reusing the provisioned sandbox. Built on-system from
// docs/web-ui.md §4.7, composed from the existing .db-* design language.
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Icon, Button, Chip } from "../../../components/Primitives";
import { Toggle } from "../../../components/Common";
import { useCurrentAgent } from "../context";
import { data } from "../../../api/queries";
import { useUI } from "../../../store/ui";
import type { Capability } from "../../../types";

// Per-pack manifest the daemon would surface: exposed tools + declared permissions.
// Keyed by capability id; anything missing falls back to a sensible default.
type Perm = "network" | "filesystem" | "hitl";
interface PackManifest {
  tools: string[];
  perms: Perm[];
  version: string;
  latest?: string; // present when an update is available
}
const MANIFESTS: Record<string, PackManifest> = {
  fs: { tools: ["read_file", "write_file", "list_dir", "stat"], perms: ["filesystem"], version: "1.4.2" },
  fetch: { tools: ["http_get", "http_post"], perms: ["network"], version: "1.4.2" },
  git: { tools: ["status", "diff", "commit", "branch", "push"], perms: ["filesystem", "hitl"], version: "1.4.2" },
  memory: { tools: ["recall", "store", "forget"], perms: ["filesystem"], version: "1.4.2" },
  github: { tools: ["list_prs", "review", "comment", "merge"], perms: ["network", "hitl"], version: "2.1.0", latest: "2.2.0" },
  playwright: { tools: ["navigate", "click", "fill", "screenshot", "extract"], perms: ["network", "filesystem"], version: "0.9.3" },
  shell: { tools: ["run", "spawn", "kill"], perms: ["filesystem", "hitl"], version: "0.6.1" },
  postgres: { tools: ["query", "explain", "schema"], perms: ["network"], version: "1.2.0" },
  slack: { tools: ["post_message", "read_channel", "list_users"], perms: ["network"], version: "1.0.4" },
};
function manifestFor(id: string): PackManifest {
  return MANIFESTS[id] ?? { tools: [], perms: [], version: "1.0.0" };
}

const PERM_META: Record<Perm, { icon: string; label: string }> = {
  network: { icon: "globe", label: "network" },
  filesystem: { icon: "folder", label: "filesystem" },
  hitl: { icon: "shield", label: "HITL approval" },
};

export default function PluginsTab() {
  const agent = useCurrentAgent();
  const navigate = useNavigate();
  const showToast = useUI((s) => s.showToast);

  const daemon = data.daemons.find((d) => d.id === agent.daemonId);
  const packs = useMemo(
    () => (daemon?.capabilities ?? []).filter((c) => c.kind === "plugin" || c.kind === "MCP server"),
    [daemon],
  );

  // Agent-tier attach state. Built-in default packs start auto-attached; everything
  // else starts detached. Pin selections track which packs are pinned to a version.
  const [attached, setAttached] = useState<Record<string, boolean>>(() => {
    const m: Record<string, boolean> = {};
    packs.forEach((p) => { m[p.id] = p.builtin; });
    return m;
  });
  const [pinned, setPinned] = useState<Record<string, boolean>>({});

  function toggleAttach(p: Capability, next: boolean) {
    setAttached((prev) => ({ ...prev, [p.id]: next }));
    showToast({
      text: `${p.name} ${next ? "attached to" : "detached from"} ${agent.name}`,
      variant: next ? "ok" : "warn",
    });
  }
  function pin(p: Capability, m: PackManifest, next: boolean) {
    setPinned((prev) => ({ ...prev, [p.id]: next }));
    showToast({ text: next ? `${p.name} pinned to v${m.version}` : `${p.name} tracking latest` });
  }
  function update(p: Capability, m: PackManifest) {
    showToast({ text: `${p.name} updated to v${m.latest}` });
  }

  const defaults = packs.filter((p) => p.builtin);
  const extra = packs.filter((p) => !p.builtin);

  return (
    <div className="db-plugins">
      <div className="db-callout">
        <Icon name="puzzle" size={16} />
        <span>
          <b>Two tiers.</b> Packs are <b>provisioned</b> once on{" "}
          <button className="db-inline-link" onClick={() => navigate("/daemons")}>{daemon?.name ?? "the daemon"}</button>{" "}
          (creating its sandbox + registering tools), then <b>attached</b> to an agent here. Attaching
          is instant and reuses the provisioned pack — no re-install. Find more in the{" "}
          <button className="db-inline-link" onClick={() => navigate("/marketplace")}>marketplace</button>.
        </span>
      </div>

      {defaults.length > 0 && (
        <>
          <div className="db-sublabel">Built-in packs <span className="db-sublabel-hint">· auto-attached, detachable per agent</span></div>
          <div className="db-cap-list">
            {defaults.map((p) => (
              <PackRow
                key={p.id} pack={p} manifest={manifestFor(p.id)}
                attached={!!attached[p.id]} pinned={!!pinned[p.id]}
                onToggle={(v) => toggleAttach(p, v)}
                onPin={(v) => pin(p, manifestFor(p.id), v)}
                onUpdate={() => update(p, manifestFor(p.id))}
              />
            ))}
          </div>
        </>
      )}

      <div className="db-section-row">
        <h2 className="db-h2">Capability packs <span className="db-count db-mono">{extra.length}</span></h2>
        <div className="db-section-actions">
          <Button variant="outline-light" icon="package" onClick={() => navigate("/marketplace")}>Browse marketplace</Button>
        </div>
      </div>

      {extra.length === 0 ? (
        <div className="db-cap-attach unavailable">
          <span className="db-cap-attach-icon"><Icon name="puzzle" size={15} /></span>
          <div className="db-cap-attach-meta">
            <div className="db-cap-attach-name">No extra packs on this daemon</div>
            <div className="db-cap-attach-desc">provision one first</div>
          </div>
          <button className="db-cap-install-hint" onClick={() => navigate("/marketplace")}>
            Provision <Icon name="arrow-up-right" size={12} />
          </button>
        </div>
      ) : (
        <div className="db-cap-list">
          {extra.map((p) => (
            <PackRow
              key={p.id} pack={p} manifest={manifestFor(p.id)}
              attached={!!attached[p.id]} pinned={!!pinned[p.id]}
              onToggle={(v) => toggleAttach(p, v)}
              onPin={(v) => pin(p, manifestFor(p.id), v)}
              onUpdate={() => update(p, manifestFor(p.id))}
              onProvision={() => navigate("/daemons")}
              onMarket={() => navigate("/marketplace")}
              onInstallLog={() => showToast({ text: `${p.name} install log`, variant: "warn" })}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface PackRowProps {
  pack: Capability;
  manifest: PackManifest;
  attached: boolean;
  pinned: boolean;
  onToggle: (next: boolean) => void;
  onPin: (next: boolean) => void;
  onUpdate: () => void;
  onProvision?: () => void;
  onMarket?: () => void;
  onInstallLog?: () => void;
}

function PackRow({
  pack, manifest, attached, pinned, onToggle, onPin, onUpdate, onProvision, onMarket, onInstallLog,
}: PackRowProps) {
  const ready = pack.state === "ready";
  const installing = pack.state === "installing";
  const failed = pack.state === "failed";
  const unprovisioned = pack.state === "available";
  const canUpdate = ready && manifest.latest && !pinned;

  return (
    <div className={"db-cap-attach" + (ready ? "" : " unavailable")}>
      <span className={"db-cap-attach-icon" + (attached && ready ? " on" : "")}>
        <Icon name={pack.kind === "plugin" ? "puzzle" : "plug"} size={15} />
      </span>
      <div className="db-cap-attach-meta">
        <div className="db-cap-attach-name">
          {pack.name}
          {pack.builtin && <span className="db-cap-default">default</span>}
          <span className="db-tag">v{manifest.version}{pinned ? " · pinned" : ""}</span>
        </div>
        <div className="db-cap-attach-desc">{pack.kind} · {pack.desc}</div>
        {manifest.tools.length > 0 && (
          <div className="db-cap-attach-desc" style={{ marginTop: 6 }}>
            <Icon name="terminal" size={11} style={{ verticalAlign: "-1px", marginRight: 4 }} />
            {manifest.tools.join(" · ")}
          </div>
        )}
        <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
          {manifest.perms.map((perm) => (
            <span key={perm} className="db-tag">
              <Icon name={PERM_META[perm].icon} size={10} style={{ verticalAlign: "-1px", marginRight: 4 }} />
              {PERM_META[perm].label}
            </span>
          ))}
          {manifest.perms.length === 0 && <span className="db-tag">no special permissions</span>}
        </div>
        {canUpdate && (
          <div style={{ marginTop: 8 }}>
            <button className="db-inline-link" onClick={onUpdate}>Update available → v{manifest.latest}</button>
          </div>
        )}
        {failed && (
          <div style={{ marginTop: 8 }}>
            <button className="db-inline-link" onClick={onInstallLog}>View install log</button>
          </div>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12, flex: "none" }}>
        {ready ? (
          <>
            <Toggle on={attached} onChange={onToggle} />
            {attached && (
              <button
                className="db-cap-install-hint"
                onClick={() => onPin(!pinned)}
                title={pinned ? "Track latest" : `Pin to v${manifest.version}`}
              >
                <Icon name="tag" size={12} /> {pinned ? "unpin" : "pin"}
              </button>
            )}
          </>
        ) : installing ? (
          <span className="db-cap-state installing"><span className="db-spin" /> installing</span>
        ) : failed ? (
          <Chip s="failed" />
        ) : unprovisioned ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
            <button className="db-cap-install-hint" onClick={onProvision}>
              Provision on a daemon <Icon name="arrow-up-right" size={12} />
            </button>
            <button className="db-inline-link" style={{ fontSize: 11 }} onClick={onMarket}>marketplace</button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
