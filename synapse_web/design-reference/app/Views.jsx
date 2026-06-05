/* Synapse Web UI — Approvals (HITL queue), Alerts, and stub views */

function Approvals({ state, setState, nav, toast }) {
  const queue = state.approvals;
  const [reasons, setReasons] = React.useState({});
  const [resolved, setResolved] = React.useState([]);

  function decide(ap, decision) {
    setResolved(r => [{ ...ap, decision, reason: reasons[ap.id] }, ...r]);
    setState(s => ({ ...s, approvals: s.approvals.filter(x => x.id !== ap.id) }));
    toast({ msg: decision === 'approve' ? `Approved — routed to ${ap.daemon} to resume` : `Denied — run aborted on ${ap.daemon}`,
      icon: decision === 'approve' ? 'check' : 'x', kind: decision === 'approve' ? 'ok' : 'warn' });
  }

  return (
    <>
      <PageHead kicker="Approvals" title="Paused runs" serif="awaiting your call"
        sub="Each gate is RBAC-checked, written to the audit log, and routed back to the daemon to resume or abort. The same gate is mirrored to Slack, Discord, and Email."
        actions={queue.length > 0 && <span className="db-queue-count db-mono"><span className="eyebrow-pulse" style={{ position: 'static' }} />{queue.length} in queue</span>} />

      {queue.length === 0 ? (
        <div className="db-empty">
          <HatchCorners onLight />
          <span className="db-empty-icon ok"><Icon name="check-check" size={22} /></span>
          <div className="db-empty-caption">Queue clear · every gate resolved. Decisions are in the <span className="db-empty-cmd">audit log</span>.</div>
        </div>
      ) : (
        <div className="db-approvals">
          {queue.map(ap => (
            <div key={ap.id} className="db-approval-card">
              <div className="db-approval-l">
                <div className="db-approval-head">
                  <span className={'db-sev-badge ' + ap.severity}><Icon name="shield-alert" size={14} /> {ap.severity === 'block' ? 'blocked' : 'requires approval'}</span>
                  <button className="db-approval-agent db-mono" onClick={() => nav({ view: 'agent', agentId: ap.agentId })}><Icon name="cpu" size={12} /> {ap.agent}</button>
                  <span className="db-mono db-muted">· {ap.daemon} · {ap.when}</span>
                </div>
                <h3 className="db-approval-action">{ap.action}</h3>
                <div className="db-approval-cmd db-mono"><span className="db-cmd-prompt">$</span> {ap.command}</div>
                <div className="db-approval-reason">
                  <div className="db-sublabel">Agent's reasoning</div>
                  <p>{ap.reason}</p>
                </div>
                <div className="db-approval-context db-mono"><Icon name="corner-down-right" size={13} /> {ap.context}</div>
              </div>
              <div className="db-approval-r">
                <div className="db-sublabel">Decision</div>
                <textarea className="db-input db-approval-note" placeholder="Optional reason (logged)…" value={reasons[ap.id] || ''} onChange={e => setReasons(p => ({ ...p, [ap.id]: e.target.value }))} />
                <button className="btn btn-primary db-approval-btn" onClick={() => decide(ap, 'approve')}><Icon name="check" size={15} stroke={2} /> Approve & resume</button>
                <button className="btn btn-danger-ghost db-approval-btn" onClick={() => decide(ap, 'deny')}><Icon name="x" size={15} stroke={2} /> Deny & abort</button>
                <div className="db-approval-mirror db-mono"><Icon name="slack" size={12} /> mirrored to #ops-approvals</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {resolved.length > 0 && (
        <>
          <SectionRow title="Just resolved" />
          <div className="db-resolved-list">
            {resolved.map((r, i) => (
              <div key={i} className="db-resolved-row">
                <span className={'db-resolved-icon ' + r.decision}><Icon name={r.decision === 'approve' ? 'check' : 'x'} size={14} /></span>
                <span className="db-resolved-action">{r.action}</span>
                <span className="db-mono db-muted">{r.agent} · {r.decision === 'approve' ? 'resumed' : 'aborted'}</span>
                {r.reason && <span className="db-mono db-muted db-resolved-reason">“{r.reason}”</span>}
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}

function Alerts({ nav }) {
  return (
    <>
      <PageHead kicker="Alerts" title="What the fleet" serif="flagged for you"
        sub="Anomalies from the cloud detection engine: cost spikes, latency regressions, silent agents, offline daemons, and prompt-injection spikes." />
      <div className="db-alert-list">
        {DATA.alerts.map(al => (
          <div key={al.id} className={'db-alert-card sev-' + al.sev}>
            <span className={'db-alert-icon lg ' + al.sev}><Icon name={al.icon} size={20} /></span>
            <div className="db-alert-card-meta">
              <div className="db-alert-card-top">
                <h3 className="db-alert-card-title">{al.title}</h3>
                <span className="db-mono db-muted">{al.when}</span>
              </div>
              <p className="db-alert-card-detail">{al.detail}</p>
              <div className="db-alert-metrics db-mono">
                <span className="db-alert-metric"><span className="db-alert-metric-l">{al.metric}</span> baseline <b>{al.baseline}</b> → observed <b className="db-accent">{al.observed}</b></span>
                <button className="db-link" onClick={() => nav({ view: al.type === 'offline' ? 'daemons' : 'runs' })}><Icon name="external-link" size={13} /> {al.type === 'offline' ? 'View daemon' : 'View runs'}</button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function GlobalRuns({ nav }) {
  const [filter, setFilter] = React.useState('all');
  const runs = DATA.runs.filter(r => filter === 'all' ? true : r.status === filter);
  return (
    <>
      <PageHead kicker="Runs" title="Every run," serif="across all agents"
        sub="Trigger source, status, duration, cost, tokens, and exit. Drill into any run for its live or replayed trace." />
      <div className="db-toolbar">
        <Segmented value={filter} onChange={setFilter} options={[
          { value: 'all', label: 'All' }, { value: 'running', label: 'Running' }, { value: 'passed', label: 'Passed' }, { value: 'blocked', label: 'Blocked' },
        ]} />
      </div>
      <div className="db-table-wrap">
        <table className="db-table">
          <thead><tr><th>Run</th><th>Agent</th><th>Trigger</th><th>Started</th><th>Duration</th><th>Tokens</th><th>Cost</th><th>Exit</th><th>Status</th></tr></thead>
          <tbody>
            {runs.map(r => (
              <tr key={r.id} className="clickable-row" onClick={() => nav({ view: 'agent', agentId: r.agentId, tab: 'runs', runId: r.id })}>
                <td className="db-cell-primary db-mono">#{r.id.replace('r', '')}</td>
                <td>{r.agent}</td>
                <td className="db-mono">{r.trigger}</td>
                <td className="db-mono">{r.started}</td>
                <td className="db-mono">{r.dur}</td>
                <td className="db-mono">{(r.tokens / 1000).toFixed(0)}k</td>
                <td className="db-mono">${r.cost.toFixed(2)}</td>
                <td className="db-mono">{r.exit}</td>
                <td><Chip s={r.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

const MARKET = [
  { name: 'PR reviewer', kind: 'Agent', desc: 'Reviews diffs against a ruleset, writes a report.', plat: 'macOS · Linux', rating: 4.8, icon: 'git-pull-request' },
  { name: 'Support triage', kind: 'Agent', desc: 'Triages tickets, drafts replies, escalates via HITL.', plat: 'all', rating: 4.6, icon: 'inbox' },
  { name: 'browser use', kind: 'Plugin', desc: 'Playwright browser automation pack.', plat: 'all', rating: 4.7, icon: 'globe' },
  { name: 'github', kind: 'MCP', desc: 'PRs, issues, reviews quick-install.', plat: 'all', rating: 4.9, icon: 'git-branch' },
  { name: 'security-scan', kind: 'Skill', desc: 'Static + dependency scanning checklist.', plat: 'macOS · Linux', rating: 4.5, icon: 'shield' },
  { name: 'postgres', kind: 'MCP', desc: 'Read-only SQL over a connection string.', plat: 'all', rating: 4.4, icon: 'database' },
];

function Marketplace({ openWizard }) {
  const [tab, setTab] = React.useState('All');
  const items = MARKET.filter(m => tab === 'All' ? true : m.kind === tab);
  return (
    <>
      <PageHead kicker="Marketplace" title="Install in" serif="one click"
        sub="Agents, skills, and capability packs. Pick a target daemon and the item is provisioned onto it." />
      <div className="db-toolbar">
        <Segmented value={tab} onChange={setTab} options={['All', 'Agent', 'Skill', 'Plugin', 'MCP'].map(v => ({ value: v, label: v }))} />
      </div>
      <div className="db-market-grid">
        {items.map(m => (
          <div key={m.name} className="db-market-card">
            <div className="db-market-top">
              <span className="db-market-icon"><Icon name={m.icon} size={18} /></span>
              <span className="db-market-kind db-mono">{m.kind}</span>
            </div>
            <div className="db-market-name">{m.name}</div>
            <p className="db-market-desc">{m.desc}</p>
            <div className="db-market-foot">
              <span className="db-mono db-muted">{m.plat}</span>
              <span className="db-market-rating db-mono"><Icon name="star" size={12} /> {m.rating}</span>
            </div>
            <Button variant="outline-light" icon="download" onClick={() => openWizard()}>Install</Button>
          </div>
        ))}
      </div>
    </>
  );
}

function Webhooks({ toast }) {
  const HOOKS = [
    { name: 'pr-opened', url: 'https://hooks.synapse.sh/in/9f2a…', agent: 'pr-reviewer', last: '2 min ago', count: 1284, status: 'passed' },
    { name: 'ticket-created', url: 'https://hooks.synapse.sh/in/4c7b…', agent: 'support-triage', last: '12 sec ago', count: 5821, status: 'running' },
  ];
  return (
    <>
      <PageHead kicker="Webhooks" title="Inbound" serif="triggers"
        sub="Signed URLs that start agents on external events. View delivery history per hook."
        actions={<Button variant="primary" icon="plus" onClick={() => toast({ msg: 'Create a signed webhook', icon: 'plus' })}>New webhook</Button>} />
      <div className="db-table-wrap">
        <table className="db-table">
          <thead><tr><th>Name</th><th>Endpoint</th><th>Agent</th><th>Deliveries</th><th>Last</th><th>Status</th></tr></thead>
          <tbody>
            {HOOKS.map(h => (
              <tr key={h.name}>
                <td className="db-cell-primary db-mono">{h.name}</td>
                <td className="db-mono db-muted">{h.url}</td>
                <td>{h.agent}</td>
                <td className="db-mono">{h.count.toLocaleString()}</td>
                <td className="db-mono">{h.last}</td>
                <td><Chip s={h.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Notifications({ toast }) {
  const CH = [
    { icon: 'slack', name: 'Slack', detail: '#ops-approvals · #alerts', on: true },
    { icon: 'message-square', name: 'Discord', detail: 'northwind / agents', on: true },
    { icon: 'mail', name: 'Email', detail: 'ops@northwind.io', on: false },
  ];
  const [chans, setChans] = React.useState(CH);
  return (
    <>
      <PageHead kicker="Notifications" title="Where the fleet" serif="reaches you"
        sub="Connect channels and route which events from which agents go where." />
      <div className="db-channel-list">
        {chans.map((c, i) => (
          <div key={c.name} className="db-channel-row">
            <span className="db-channel-icon"><Icon name={c.icon} size={18} /></span>
            <div className="db-channel-meta"><div className="db-channel-name">{c.name}</div><div className="db-channel-detail db-mono">{c.detail}</div></div>
            <Toggle on={c.on} onChange={v => { setChans(cs => cs.map((x, j) => j === i ? { ...x, on: v } : x)); toast({ msg: `${c.name} ${v ? 'connected' : 'paused'}`, icon: v ? 'check' : 'pause' }); }} />
          </div>
        ))}
      </div>
      <SectionRow title="Routing rules" />
      <div className="db-route-list">
        {[['Approvals', 'all agents', 'Slack #ops-approvals'], ['Alerts · prompt-injection', 'all agents', 'Slack #alerts + Email'], ['Run failed', 'codex-builder', 'Discord']].map((r, i) => (
          <div key={i} className="db-route-row db-mono">
            <span className="db-route-evt">{r[0]}</span><Icon name="arrow-right" size={13} style={{ color: 'var(--mute)' }} /><span className="db-muted">{r[1]}</span><Icon name="arrow-right" size={13} style={{ color: 'var(--mute)' }} /><span className="db-accent">{r[2]}</span>
          </div>
        ))}
      </div>
    </>
  );
}

function Settings({ toast }) {
  const [sub, setSub] = React.useState('members');
  const MEMBERS = [
    { name: 'Avery Koss', email: 'avery@northwind.io', role: 'Owner', init: 'AK' },
    { name: 'Jin Park', email: 'jin@northwind.io', role: 'Admin', init: 'JP' },
    { name: 'Mara Vance', email: 'mara@northwind.io', role: 'Operator', init: 'MV' },
    { name: 'Theo Lund', email: 'theo@northwind.io', role: 'Viewer', init: 'TL' },
  ];
  return (
    <>
      <PageHead kicker="Settings" title="Your" serif="workspace"
        sub="Org profile, members and roles, billing, and API tokens. Roles gate who can deploy, edit, approve, and view secrets-adjacent data." />
      <div className="db-subtabs">
        {[['members', 'Members & RBAC'], ['billing', 'Billing'], ['tokens', 'API tokens'], ['org', 'Org profile']].map(([id, n]) => (
          <button key={id} className={'db-subtab' + (sub === id ? ' active' : '')} onClick={() => setSub(id)}>{n}</button>
        ))}
      </div>
      {sub === 'members' && (
        <div className="db-table-wrap">
          <table className="db-table">
            <thead><tr><th>Member</th><th>Email</th><th>Role</th><th></th></tr></thead>
            <tbody>
              {MEMBERS.map(m => (
                <tr key={m.email}>
                  <td className="db-cell-primary"><span className="db-member"><span className="db-member-av">{m.init}</span>{m.name}</span></td>
                  <td className="db-mono db-muted">{m.email}</td>
                  <td><span className={'db-role-pill ' + m.role.toLowerCase()}>{m.role}</span></td>
                  <td><button className="db-icon-mini" onClick={() => toast({ msg: 'Edit role', icon: 'pencil' })}><Icon name="more-horizontal" size={15} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {sub === 'billing' && <div className="db-metric-grid db-metric-grid-3"><MetricCard label="Plan" n="Team" sub="$0.00 platform fee" /><MetricCard label="Spend this month" n="$418" delta="across 6 agents" /><MetricCard label="Seats" n="4" unit="/ 10" /></div>}
      {sub === 'tokens' && <div className="db-empty"><HatchCorners onLight /><div className="db-empty-caption">No API tokens yet · run <span className="db-empty-cmd">synapse token create</span> to mint one</div></div>}
      {sub === 'org' && <div className="db-panel" style={{ maxWidth: 520 }}><div className="db-panel-head"><h3 className="db-panel-title">Organization</h3></div><div className="db-ov-facts"><div className="db-ov-fact"><span className="db-ov-fact-l">Name</span><span className="db-mono">northwind</span></div><div className="db-ov-fact"><span className="db-ov-fact-l">Region</span><span className="db-mono">us-east</span></div><div className="db-ov-fact"><span className="db-ov-fact-l">Created</span><span className="db-mono">2025-11-02</span></div></div></div>}
    </>
  );
}

Object.assign(window, { Approvals, Alerts, GlobalRuns, Marketplace, Webhooks, Notifications, Settings });
