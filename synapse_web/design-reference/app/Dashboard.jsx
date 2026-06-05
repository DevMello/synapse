/* Synapse Web UI — Dashboard (fleet overview) */

function Dashboard({ nav, state }) {
  const onlineDaemons = DATA.daemons.filter(d => d.status === 'online').length;
  const activeRuns = DATA.runs.filter(r => r.status === 'running').length;
  const spendToday = DATA.agents.reduce((s, a) => s + a.spendToday, 0);
  const topAgents = [...DATA.agents].sort((a, b) => b.spendToday - a.spendToday).slice(0, 4);

  return (
    <>
      <PageHead kicker="Overview" title="Your whole fleet," serif="one pane of glass"
        sub="Agents run on your machines. Synapse only brokers commands and stores redacted records — keys never leave the host."
        actions={<>
          <Button variant="outline-light" icon="server" onClick={() => nav({ view: 'connect' })}>Connect a device</Button>
          <Button variant="primary" arrow onClick={() => nav({ view: 'agents', newAgent: true })}>New agent</Button>
        </>} />

      <div className="db-metric-grid">
        <MetricCard label="Daemons online" n={onlineDaemons} unit={'/ ' + DATA.daemons.length} delta="1 offline" dir="down" onClick={() => nav({ view: 'daemons' })} />
        <MetricCard label="Active runs" n={activeRuns} delta="streaming now" dir="up" onClick={() => nav({ view: 'runs' })} />
        <MetricCard label="Spend today" n={'$' + spendToday.toFixed(2)} delta="+12% vs yesterday" dir="up" onClick={() => nav({ view: 'agents' })} />
        <MetricCard label="Open approvals" n={state.approvals.length} delta={state.approvals.length + ' awaiting you'} dir="down" onClick={() => nav({ view: 'approvals' })} />
      </div>

      <div className="db-dash-grid">
        <div className="db-dash-main">
          <SectionRow title="Active runs">
            <Link icon="external-link" onClick={() => nav({ view: 'runs' })}>All runs</Link>
          </SectionRow>
          <div className="db-table-wrap">
            <table className="db-table">
              <thead><tr><th>Agent</th><th>Trigger</th><th>Host</th><th>Started</th><th>Cost</th><th>Status</th></tr></thead>
              <tbody>
                {DATA.runs.filter(r => ['running', 'recovering'].includes(r.status)).map(r => {
                  const a = DATA.agents.find(x => x.id === r.agentId);
                  return (
                    <tr key={r.id} onClick={() => nav({ view: 'agent', agentId: r.agentId, tab: 'runs', runId: r.id })} className="clickable-row">
                      <td className="db-cell-primary">{r.agent}</td>
                      <td className="db-mono">{r.trigger}</td>
                      <td className="db-mono">{a ? daemonName(a.daemonId) : '—'}</td>
                      <td className="db-mono">{r.started}</td>
                      <td className="db-mono">${r.cost.toFixed(2)}</td>
                      <td><Chip s={r.status} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <SectionRow title="Top agents by spend">
            <Link icon="external-link" onClick={() => nav({ view: 'agents' })}>All agents</Link>
          </SectionRow>
          <div className="db-toplist">
            {topAgents.map(a => (
              <button key={a.id} className="db-toprow" onClick={() => nav({ view: 'agent', agentId: a.id })}>
                <AgentAvatar engine={a.engine} size={36} />
                <div className="db-toprow-meta">
                  <div className="db-toprow-name">{a.name}</div>
                  <div className="db-toprow-sub db-mono">{a.engine} · {daemonName(a.daemonId)}</div>
                </div>
                <Sparkline data={[3,5,4,7,6,9,8,11].map(x => x * a.spendToday / 11)} w={96} h={30} />
                <div className="db-toprow-spend">
                  <div className="db-toprow-amt db-mono">${a.spendToday.toFixed(2)}</div>
                  <div className="db-toprow-lbl">today</div>
                </div>
                <Chip s={a.status} />
              </button>
            ))}
          </div>
        </div>

        <div className="db-dash-side">
          <div className="db-panel">
            <div className="db-panel-head">
              <h3 className="db-panel-title">Daemons</h3>
              <Link icon="external-link" onClick={() => nav({ view: 'daemons' })}>Manage</Link>
            </div>
            <div className="db-daemon-mini-list">
              {DATA.daemons.map(d => (
                <button key={d.id} className="db-daemon-mini" onClick={() => nav({ view: 'daemons' })}>
                  <span className={'db-status-dot ' + d.status} />
                  <div className="db-daemon-mini-meta">
                    <div className="db-daemon-mini-name">{d.name}</div>
                    <div className="db-daemon-mini-os db-mono">{d.os}</div>
                  </div>
                  <HeartStrip data={d.heartbeat} />
                </button>
              ))}
            </div>
          </div>

          <div className="db-panel">
            <div className="db-panel-head">
              <h3 className="db-panel-title">Alerts</h3>
              <Link icon="external-link" onClick={() => nav({ view: 'alerts' })}>All</Link>
            </div>
            <div className="db-alert-mini-list">
              {DATA.alerts.map(al => (
                <button key={al.id} className="db-alert-mini" onClick={() => nav({ view: 'alerts' })}>
                  <span className={'db-alert-icon ' + al.sev}><Icon name={al.icon} size={15} /></span>
                  <div className="db-alert-mini-meta">
                    <div className="db-alert-mini-title">{al.title}</div>
                    <div className="db-alert-mini-sub db-mono">{al.observed} · {al.when}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

Object.assign(window, { Dashboard });
