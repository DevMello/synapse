// Synapse Web UI — Daemons (registered workers + uptime + capabilities + revoke).
// Ported from design-reference/app/Daemons.jsx onto the typed module stack.
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Icon, Button, Chip } from "../components/Primitives";
import {
  PageHead, MetricCard, HeartStrip, ConfirmDialog, AgentAvatar, daemonName,
} from "../components/Common";
import { useDaemons, useAgents } from "../api/queries";
import { useUI } from "../store/ui";
import type { Daemon, Capability } from "../types";

function glyphFor(os: string): string {
  if (os.startsWith("Windows")) return "monitor";
  if (os.startsWith("mac")) return "smartphone";
  return "server";
}

export default function Daemons() {
  const { data: daemons = [] } = useDaemons();
  const { data: agents = [] } = useAgents();
  const showToast = useUI((s) => s.showToast);
  const navigate = useNavigate();

  const [openId, setOpenId] = useState<string | null>("d-mbp");
  const [revoke, setRevoke] = useState<Daemon | null>(null);
  // Local, optimistic capability overrides keyed by daemon id (enable → installing → ready).
  const [capOverrides, setCapOverrides] = useState<Record<string, Capability[]>>({});

  // Resolved caps per daemon: local override if present, else the daemon's seed.
  const capsByDaemon = useMemo(() => {
    const m: Record<string, Capability[]> = {};
    daemons.forEach((d) => { m[d.id] = capOverrides[d.id] ?? d.capabilities; });
    return m;
  }, [daemons, capOverrides]);

  function provision(daemonId: string, capId: string) {
    const seed = capsByDaemon[daemonId] ?? [];
    setCapOverrides((prev) => ({
      ...prev,
      [daemonId]: seed.map((c) => (c.id === capId ? { ...c, state: "installing" } : c)),
    }));
    setTimeout(() => {
      setCapOverrides((prev) => {
        const base = prev[daemonId];
        if (!base) return prev;
        return { ...prev, [daemonId]: base.map((c) => (c.id === capId ? { ...c, state: "ready" } : c)) };
      });
      const cap = daemons.find((d) => d.id === daemonId)?.capabilities.find((c) => c.id === capId);
      showToast({ text: `${cap?.name ?? capId} ready on ${daemonName(daemonId)}`, variant: "ok" });
    }, 2200);
  }

  const onlineCount = daemons.filter((d) => d.status === "online").length;
  const totalActiveRuns = daemons.reduce((s, d) => s + d.activeRuns, 0);

  return (
    <>
      <PageHead
        kicker="Daemons"
        title="Every machine you"
        serif="point an agent at"
        sub="Registered workers, their device identity, uptime, and the capabilities installed on each host."
        actions={<Button variant="primary" icon="plus" onClick={() => navigate("/connect")}>Connect a device</Button>}
      />

      <div className="db-metric-grid db-metric-grid-3">
        <MetricCard label="Online" n={onlineCount} unit={"/ " + daemons.length} delta="1 needs attention" dir="down" />
        <MetricCard label="Fleet uptime" n="98.4" unit="%" delta="30-day average" />
        <MetricCard label="Active runs" n={totalActiveRuns} delta="across 3 hosts" dir="up" />
      </div>

      <div className="db-daemon-list">
        {daemons.map((d) => {
          const open = openId === d.id;
          const hosted = agents.filter((a) => a.daemonId === d.id);
          const agentCount = hosted.length;
          const dCaps = capsByDaemon[d.id] ?? [];
          return (
            <div key={d.id} className={"db-daemon-card" + (d.status === "offline" ? " offline" : "")}>
              <button className="db-daemon-head" onClick={() => setOpenId(open ? null : d.id)}>
                <span className={"db-daemon-glyph " + d.status}><Icon name={glyphFor(d.os)} size={18} /></span>
                <div className="db-daemon-id">
                  <div className="db-daemon-name-row">
                    <span className="db-daemon-name">{d.name}</span>
                    <Chip s={d.status} />
                    {d.tags.map((t) => <span key={t} className="db-tag">{t}</span>)}
                  </div>
                  <div className="db-daemon-line db-mono">
                    logged in on <b>{d.name}</b> ({d.os}) · {d.ip} · last seen {d.lastSeen}
                  </div>
                </div>
                <div className="db-daemon-stats">
                  <div className="db-dstat"><span className="db-dstat-n db-mono">{d.uptime}%</span><span className="db-dstat-l">uptime</span></div>
                  <div className="db-dstat"><span className="db-dstat-n db-mono">{d.cpu}%</span><span className="db-dstat-l">cpu</span></div>
                  <div className="db-dstat"><span className="db-dstat-n db-mono">{d.mem}%</span><span className="db-dstat-l">mem</span></div>
                  <div className="db-dstat"><span className="db-dstat-n db-mono">{d.activeRuns}</span><span className="db-dstat-l">runs</span></div>
                </div>
                <Icon name={open ? "chevron-up" : "chevron-down"} size={18} style={{ color: "var(--mute)" }} />
              </button>

              {open && (
                <div className="db-daemon-body">
                  <div className="db-daemon-cols">
                    <div className="db-daemon-col">
                      <div className="db-sublabel">Uptime · last 12 heartbeats</div>
                      <div className="db-uptime-block">
                        <HeartStrip data={d.heartbeat} />
                        <div className="db-uptime-meta db-mono">
                          {d.status === "online"
                            ? <span className="db-ok">heartbeat steady · {d.version}</span>
                            : <span className="db-warn">no heartbeat for {d.lastSeen} · {d.version}</span>}
                        </div>
                      </div>
                      <div className="db-sublabel" style={{ marginTop: 18 }}>Hosts {agentCount} agent{agentCount !== 1 ? "s" : ""}</div>
                      <div className="db-daemon-agents">
                        {hosted.map((a) => (
                          <button key={a.id} className="db-mini-agent" onClick={() => navigate(`/agents/${a.id}`)}>
                            <AgentAvatar engine={a.engine} size={26} />
                            <span>{a.name}</span><Chip s={a.status} />
                          </button>
                        ))}
                        {agentCount === 0 && <div className="db-muted db-mono">No agents on this host yet.</div>}
                      </div>
                    </div>

                    <div className="db-daemon-col">
                      <div className="db-sublabel">Capabilities on this host <span className="db-sublabel-hint">— daemon tier</span></div>
                      <div className="db-cap-grid">
                        {dCaps.map((c) => (
                          <div key={c.id} className={"db-cap-row state-" + c.state}>
                            <div className="db-cap-meta">
                              <span className="db-cap-name">{c.name}{c.builtin && <span className="db-cap-default">default</span>}</span>
                              <span className="db-cap-desc">{c.kind} · {c.desc}</span>
                            </div>
                            {c.state === "ready" && <span className="db-cap-state ready"><Icon name="check" size={13} /> ready</span>}
                            {c.state === "installing" && <span className="db-cap-state installing"><span className="db-spin" /> installing</span>}
                            {c.state === "failed" && <span className="db-cap-state failed"><Icon name="alert-triangle" size={13} /> failed</span>}
                            {c.state === "available" && <button className="db-cap-enable" onClick={() => provision(d.id, c.id)} disabled={d.status === "offline"}>Enable</button>}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="db-daemon-foot">
                    <div className="db-muted db-mono">Revoking drops this device's tokens and live connection — your password is unchanged, other daemons untouched.</div>
                    <button className="btn btn-danger-ghost" onClick={() => setRevoke(d)}><Icon name="log-out" size={15} stroke={2} />Revoke device</button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <ConfirmDialog
        open={!!revoke}
        onClose={() => setRevoke(null)}
        danger
        confirmLabel="Revoke this device"
        title="Revoke device access?"
        onConfirm={() => {
          if (revoke) showToast({ text: `${revoke.name} revoked — tokens invalidated`, variant: "warn" });
          setRevoke(null);
        }}
        body={revoke && <>
          <p>You're about to revoke <b>{revoke.name}</b> ({revoke.os}, last seen {revoke.lastSeen}). Its tokens are invalidated and the live connection drops immediately.</p>
          <div className="db-dialog-detail db-mono">{revoke.hostname} · {revoke.ip}</div>
        </>}
      />
    </>
  );
}
