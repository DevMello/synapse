/* Synapse Web UI — Agent tabs (part 2): Tools & MCP / blockers / filtering, Environment */

function ToolsTab({ a, d, nav, toast }) {
  const [sub, setSub] = React.useState('caps');
  return (
    <div className="db-tools">
      <div className="db-subtabs">
        {[{ id: 'caps', name: 'Capabilities' }, { id: 'blockers', name: 'Rulesets & blockers' }, { id: 'filter', name: 'Filtering' }].map(s => (
          <button key={s.id} className={'db-subtab' + (sub === s.id ? ' active' : '')} onClick={() => setSub(s.id)}>{s.name}</button>
        ))}
      </div>
      {sub === 'caps' && <CapabilitiesPanel a={a} d={d} nav={nav} toast={toast} />}
      {sub === 'blockers' && <BlockersPanel toast={toast} />}
      {sub === 'filter' && <FilteringPanel toast={toast} />}
    </div>
  );
}

function CapabilitiesPanel({ a, d, nav, toast }) {
  const installed = d ? d.capabilities : [];
  const [attached, setAttached] = React.useState(() => {
    const m = {}; DATA.CAP_DEFS.forEach(c => { m[c.id] = c.builtin && c.id !== 'fetch' ? true : (c.id === 'github'); }); m.fetch = true; return m;
  });
  return (
    <>
      <div className="db-callout">
        <Icon name="layers" size={16} />
        <span><b>Agent tier.</b> Toggle what this agent may use from the capabilities already installed on <button className="db-inline-link" onClick={() => nav({ view: 'daemons' })}>{daemonName(a.daemonId)}</button>. Toggling is instant — it attaches/detaches, it doesn't install or tear down.</span>
      </div>
      <div className="db-cap-list">
        {DATA.CAP_DEFS.map(c => {
          const onHost = installed.find(x => x.id === c.id);
          const ready = onHost && onHost.state === 'ready';
          const installing = onHost && onHost.state === 'installing';
          return (
            <div key={c.id} className={'db-cap-attach' + (!ready ? ' unavailable' : '')}>
              <span className={'db-cap-attach-icon' + (attached[c.id] && ready ? ' on' : '')}><Icon name={c.kind === 'plugin' ? 'puzzle' : 'plug'} size={15} /></span>
              <div className="db-cap-attach-meta">
                <div className="db-cap-attach-name">{c.name}{c.builtin && <span className="db-cap-default">default</span>}</div>
                <div className="db-cap-attach-desc">{c.kind} · {c.desc}</div>
              </div>
              {ready ? <Toggle on={!!attached[c.id]} onChange={v => { setAttached(p => ({ ...p, [c.id]: v })); toast({ msg: `${c.name} ${v ? 'attached to' : 'detached from'} ${a.name}`, icon: v ? 'check' : 'minus' }); }} />
                : installing ? <span className="db-cap-state installing"><span className="db-spin" /> installing</span>
                : <button className="db-cap-install-hint" onClick={() => nav({ view: 'daemons' })}>Install on daemon <Icon name="arrow-up-right" size={12} /></button>}
            </div>
          );
        })}
      </div>
      <div className="db-gateways">
        <div className="db-sublabel">Gateways</div>
        <div className="db-gateway-row">
          <span className="db-mono"><Icon name="globe" size={13} /> anthropic-proxy.northwind.internal</span>
          <Chip s="ready" label="active" />
        </div>
      </div>
    </>
  );
}

const RULES = [
  { id: 'r1', name: 'Force-push to protected branch', pattern: 'git push --force', sev: 'require-approval', icon: 'git-branch' },
  { id: 'r2', name: 'Delete outside repo root', pattern: 'rm -rf <path not in repo>', sev: 'require-approval', icon: 'trash' },
  { id: 'r3', name: 'Network allow-list', pattern: 'only hosts in reports/allow-list.txt', sev: 'block', icon: 'globe' },
  { id: 'r4', name: 'Production secrets in shell', pattern: 'echo $*_SECRET / $*_KEY', sev: 'block', icon: 'key' },
  { id: 'r5', name: 'Cost cap per run', pattern: '> $8.00 / run', sev: 'warn', icon: 'dollar-sign' },
  { id: 'r6', name: 'Tool-call cap', pattern: '> 200 tool calls / run', sev: 'warn', icon: 'sliders' },
];

function BlockersPanel({ toast }) {
  const [rules, setRules] = React.useState(RULES);
  const SEV = [{ value: 'block', label: 'Block' }, { value: 'require-approval', label: 'Approve' }, { value: 'warn', label: 'Warn' }];
  return (
    <>
      <div className="db-callout">
        <Icon name="shield" size={16} />
        <span><b>Enforcement surface.</b> Each rule fires on the daemon before a command runs. Severity decides what happens: <span className="db-sev-pill block">block</span> <span className="db-sev-pill require-approval">require approval</span> <span className="db-sev-pill warn">warn</span>.</span>
      </div>
      <div className="db-rule-list">
        {rules.map(r => (
          <div key={r.id} className="db-rule-row">
            <span className="db-rule-icon"><Icon name={r.icon} size={15} /></span>
            <div className="db-rule-meta">
              <div className="db-rule-name">{r.name}</div>
              <div className="db-rule-pattern db-mono">{r.pattern}</div>
            </div>
            <Segmented value={r.sev} onChange={v => { setRules(rs => rs.map(x => x.id === r.id ? { ...x, sev: v } : x)); }} options={SEV} />
          </div>
        ))}
      </div>
      <button className="db-add-row" onClick={() => toast({ msg: 'Add a custom rule', icon: 'plus' })}><Icon name="plus" size={14} /> Add rule</button>
    </>
  );
}

function FilteringPanel({ toast }) {
  const [detectors, setDetectors] = React.useState({ apikey: true, email: true, token: true, card: true, ssn: false });
  const [inbound, setInbound] = React.useState(true);
  const [outbound, setOutbound] = React.useState(true);
  const [classifier, setClassifier] = React.useState(true);
  const DET = [{ id: 'apikey', name: 'API keys', mode: 'hash' }, { id: 'email', name: 'Email addresses', mode: 'mask' }, { id: 'token', name: 'Bearer / OAuth tokens', mode: 'hash' }, { id: 'card', name: 'Card / SSN patterns', mode: 'block' }, { id: 'ssn', name: 'Custom: employee IDs', mode: 'mask' }];
  return (
    <>
      <div className="db-callout">
        <Icon name="eye-off" size={16} />
        <span><b>Daemon-side guardrails.</b> Content is screened on the host before it reaches the model and before output leaves. Overrides sit on top of the org-wide default policy. <span className="db-inherited">3 inherited</span> · <span className="db-overridden">2 overridden</span>.</span>
      </div>

      <div className="db-filter-grid">
        <div className="db-panel">
          <div className="db-panel-head"><h3 className="db-panel-title">PII / secret redaction</h3></div>
          <div className="db-det-list">
            {DET.map(dt => (
              <div key={dt.id} className="db-det-row">
                <Toggle on={!!detectors[dt.id]} onChange={v => setDetectors(p => ({ ...p, [dt.id]: v }))} />
                <span className="db-det-name">{dt.name}</span>
                <span className={'db-mode-pill ' + dt.mode}>{dt.mode}</span>
              </div>
            ))}
          </div>
          <div className="db-filter-note db-mono"><Icon name="lock" size={12} /> Tokens are salted on-device — the cloud never sees plaintext.</div>
        </div>

        <div className="db-panel">
          <div className="db-panel-head"><h3 className="db-panel-title">Prompt-injection & jailbreak guard</h3></div>
          <div className="db-guard-toggle"><Toggle on={inbound} onChange={setInbound} /><div><div className="db-guard-name">Inbound screening</div><div className="db-guard-desc">Untrusted tool/web content checked for override, exfiltration, tool-bypass.</div></div></div>
          <div className="db-guard-toggle"><Toggle on={outbound} onChange={setOutbound} /><div><div className="db-guard-name">Outbound screening</div><div className="db-guard-desc">Model output checked for self-instruction override, policy divergence, secret-leak.</div></div></div>
          <div className="db-guard-toggle"><Toggle on={classifier} onChange={setClassifier} /><div><div className="db-guard-name">Local classifier <span className="db-mono db-muted">(Ollama)</span></div><div className="db-guard-desc">On-device model. Available on this host.</div></div></div>
          <div className="db-finding-map">
            <div className="db-sublabel">Finding → action</div>
            {[['override', 'block'], ['exfiltration', 'block'], ['tool-bypass', 'require-approval'], ['policy-divergence', 'warn']].map(([cat, act]) => (
              <div key={cat} className="db-finding-row db-mono"><span>{cat}</span><span className={'db-sev-pill ' + act}>{act.replace('require-approval', 'approve')}</span></div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

function EnvTab({ a, d, toast }) {
  const [vars, setVars] = React.useState(DATA.envVars);
  const [adding, setAdding] = React.useState(false);
  const [k, setK] = React.useState(''); const [v, setV] = React.useState(''); const [secret, setSecret] = React.useState(true);

  function save() {
    if (!k.trim()) return;
    setVars(vs => [{ key: k.toUpperCase().replace(/[^A-Z0-9_]/g, '_'), secret, value: secret ? undefined : v, origin: 'cloud', updated: 'just now', by: 'AK' }, ...vs]);
    toast({ msg: `${k.toUpperCase()} encrypted to ${daemonName(a.daemonId)} · cloud never sees it`, icon: 'lock' });
    setAdding(false); setK(''); setV(''); setSecret(true);
  }

  return (
    <div className="db-env">
      <div className="db-callout">
        <Icon name="lock" size={16} />
        <span><b>End-to-end encrypted.</b> Secret values are sealed in your browser to <span className="db-mono">{daemonName(a.daemonId)}</span>'s public key and relayed as opaque ciphertext. The cloud can't read them — and neither can this UI once saved. You can overwrite or delete, never view.</span>
      </div>

      <div className="db-section-row">
        <h2 className="db-h2">Variables <span className="db-count db-mono">{vars.length}</span></h2>
        <div className="db-section-actions">
          <Button variant="outline-light" icon="upload" onClick={() => toast({ msg: 'Paste / import a .env file', icon: 'upload' })}>Import .env</Button>
          <Button variant="primary" icon="plus" onClick={() => setAdding(true)}>Add variable</Button>
        </div>
      </div>

      <div className="db-table-wrap">
        <table className="db-table db-env-table">
          <thead><tr><th>Key</th><th>Value</th><th>Origin</th><th>Updated</th><th></th></tr></thead>
          <tbody>
            {adding && (
              <tr className="db-env-add">
                <td><input className="db-input-sm db-mono" autoFocus placeholder="KEY" value={k} onChange={e => setK(e.target.value)} /></td>
                <td>{secret ? <input className="db-input-sm db-mono" type="password" placeholder="secret value" value={v} onChange={e => setV(e.target.value)} /> : <input className="db-input-sm db-mono" placeholder="value" value={v} onChange={e => setV(e.target.value)} />}</td>
                <td colSpan="2"><label className="db-secret-check"><input type="checkbox" checked={secret} onChange={e => setSecret(e.target.checked)} /> secret (write-only)</label></td>
                <td><div className="db-env-add-actions"><button className="db-mini-btn primary" onClick={save}>Save</button><button className="db-mini-btn" onClick={() => setAdding(false)}>Cancel</button></div></td>
              </tr>
            )}
            {vars.map((vr, i) => (
              <tr key={vr.key + i} className={vr.origin === 'local' ? ' db-env-local' : ''}>
                <td className="db-cell-primary db-mono">{vr.key}</td>
                <td className="db-mono">
                  {vr.origin === 'local' ? <span className="db-muted">set on daemon</span>
                    : vr.secret ? <span className="db-secret-mask db-mono"><Icon name="lock" size={11} /> •••••••••••• <span className="db-writeonly">write-only</span></span>
                    : <span>{vr.value}</span>}
                </td>
                <td><span className={'db-origin-pill ' + vr.origin}>{vr.origin === 'local' ? 'set locally' : 'cloud'}</span></td>
                <td className="db-mono db-muted">{vr.updated}{vr.by !== '—' && ' · ' + vr.by}</td>
                <td>
                  {vr.origin !== 'local' && <div className="db-env-row-actions">
                    <button className="db-icon-mini" title="Overwrite" onClick={() => toast({ msg: `Overwrite ${vr.key}`, icon: 'pencil' })}><Icon name="pencil" size={14} /></button>
                    <button className="db-icon-mini danger" title="Delete" onClick={() => { setVars(vs => vs.filter(x => x !== vr)); toast({ msg: `${vr.key} deleted`, icon: 'trash', kind: 'warn' }); }}><Icon name="trash" size={14} /></button>
                  </div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="db-env-foot db-mono">
        <span><Icon name="key" size={12} /> Locally-set vars (<span className="db-muted">synapse env set</span>) show as read-only — the UI can't expose their values.</span>
      </div>
    </div>
  );
}

Object.assign(window, { ToolsTab, EnvTab });
