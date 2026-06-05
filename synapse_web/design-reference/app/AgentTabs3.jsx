/* Synapse Web UI — Agent tabs (part 3): Memory, Runs, Logs, Analytics */

function MemoryTab({ a, toast }) {
  const [rows, setRows] = React.useState(DATA.memory);
  const [q, setQ] = React.useState('');
  const [provider, setProvider] = React.useState('vector');
  const [editing, setEditing] = React.useState(null);
  const [draft, setDraft] = React.useState('');
  const filtered = rows.filter(r => !q.trim() || (r.key + r.val + r.tags.join(' ')).toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="db-memory">
      <div className="db-callout">
        <Icon name="brain" size={16} />
        <span><b>Visible by design.</b> Memory is redacted on-device before sync and stored cloud-side as RLS-scoped plaintext — not E2E-encrypted — so you can read and fix it. Secrets belong in <b>Environment</b>, never here.</span>
      </div>

      <div className="db-metric-grid db-metric-grid-3">
        <MetricCard label="Entries" n={rows.length} sub="this agent" />
        <MetricCard label="Footprint" n="50" unit="MB" delta="+4 MB this week" dir="up" />
        <MetricCard label="Provider" n={provider === 'vector' ? 'vector' : 'sqlite'} sub={provider === 'vector' ? 'Qdrant · semantic recall' : 'sqlite-memory'} />
      </div>

      <div className="db-toolbar">
        <div className="db-search-inline">
          <Icon name="search" size={15} style={{ color: 'var(--mute)' }} />
          <input placeholder="Search keys, values, tags… (semantic on vector)" value={q} onChange={e => setQ(e.target.value)} />
        </div>
        <div className="db-toolbar-r">
          <Segmented value={provider} onChange={setProvider} options={[{ value: 'sqlite', label: 'sqlite-memory' }, { value: 'vector', label: 'vector-memory' }]} />
          <Button variant="outline-light" icon="upload" onClick={() => toast({ msg: 'Bulk pre-load entries before first run', icon: 'upload' })}>Pre-load</Button>
        </div>
      </div>

      <div className="db-table-wrap">
        <table className="db-table db-mem-table">
          <thead><tr><th>Key</th><th>Value</th><th>Namespace</th><th>Tags</th><th>Size</th><th></th></tr></thead>
          <tbody>
            {filtered.map((r, i) => (
              <tr key={r.key}>
                <td className="db-cell-primary db-mono">{r.key}</td>
                <td className="db-mem-val">
                  {editing === r.key
                    ? <input className="db-input-sm" autoFocus value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { setRows(rs => rs.map(x => x.key === r.key ? { ...x, val: draft } : x)); setEditing(null); toast({ msg: `${r.key} corrected — synced to daemon`, icon: 'check' }); } }} />
                    : r.val}
                </td>
                <td className="db-mono"><span className="db-ns-pill">{r.ns}</span></td>
                <td>{r.tags.map(t => <span key={t} className="db-tag">{t}</span>)}</td>
                <td className="db-mono db-muted">{r.size}</td>
                <td><div className="db-env-row-actions">
                  <button className="db-icon-mini" title="Edit" onClick={() => { setEditing(r.key); setDraft(r.val); }}><Icon name="pencil" size={14} /></button>
                  <button className="db-icon-mini danger" title="Delete" onClick={() => { setRows(rs => rs.filter(x => x.key !== r.key)); toast({ msg: `${r.key} deleted — synced to daemon`, icon: 'trash', kind: 'warn' }); }}><Icon name="trash" size={14} /></button>
                </div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="db-env-foot db-mono"><Icon name="refresh-cw" size={12} /> Reads come from the cloud snapshot (synced on demand). Edits round-trip to the daemon's local store — the source of truth.</div>
    </div>
  );
}

function RunsTab({ a, nav }) {
  const runs = DATA.runs.filter(r => r.agentId === a.id);
  const live = runs.find(r => r.status === 'running');
  const recovering = runs.find(r => r.status === 'recovering');
  const [sel, setSel] = React.useState(live ? live.id : (runs[0] && runs[0].id));

  return (
    <div className="db-runs">
      <div className="db-runs-list-col">
        <div className="db-sublabel">Run history</div>
        <div className="db-runs-list">
          {runs.map(r => (
            <button key={r.id} className={'db-run-item' + (sel === r.id ? ' sel' : '')} onClick={() => setSel(r.id)}>
              <Chip s={r.status} />
              <div className="db-run-item-meta">
                <div className="db-run-item-id db-mono">#{r.id.replace('r', '')}</div>
                <div className="db-run-item-sub db-mono">{r.trigger} · {r.started}</div>
              </div>
              <div className="db-run-item-cost db-mono">${r.cost.toFixed(2)}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="db-runs-trace-col">
        {recovering && sel === recovering.id ? (
          <div className="db-recovery">
            <div className="db-recovery-head">
              <span className="status-chip recovering">recovering</span>
              <span className="db-mono">run #{recovering.id.replace('r','')} · checkpoint resume</span>
            </div>
            <div className="db-recovery-progress">
              <div className="db-recovery-bar"><div className="db-recovery-fill" style={{ width: '47%' }} /></div>
              <div className="db-mono db-muted">step 14 / 30 · resumed on macbook-pro-m3 after a dropped connection</div>
            </div>
            <div className="db-recovery-actions">
              <Button variant="primary" icon="play">Resume</Button>
              <Button variant="outline-light" icon="refresh-cw">Restart</Button>
              <Button variant="danger-ghost" icon="square">Abort</Button>
            </div>
            <p className="db-muted db-mono" style={{ marginTop: 14 }}>Auto-recovery is handling this. Manual override is here for the rare case it needs a human decision.</p>
          </div>
        ) : (
          <TraceViewer autoplay={sel === (live && live.id)} embedded />
        )}
      </div>
    </div>
  );
}

function LogsTab({ a }) {
  const [filter, setFilter] = React.useState('all');
  const rows = DATA.logLines.filter(l => filter === 'all' ? true : l.guard);
  return (
    <div className="db-logs">
      <div className="db-toolbar">
        <div className="db-search-inline">
          <Icon name="search" size={15} style={{ color: 'var(--mute)' }} />
          <input placeholder="Search access & tool logs…" />
        </div>
        <div className="db-toolbar-r">
          <Segmented value={filter} onChange={setFilter} options={[{ value: 'all', label: 'All events' }, { value: 'guard', label: 'Guardrail only' }]} />
        </div>
      </div>

      <div className="db-redact-summary db-mono"><Icon name="shield-check" size={14} /> 2 secrets masked on the daemon before upload · this UI never receives raw secrets.</div>

      <div className="db-log-panel">
        {rows.map((l, i) => (
          <div key={i} className={'db-log-line' + (l.guard ? ' guard' : '')}>
            <span className="db-log-time db-mono">{l.time}</span>
            <span className={'db-log-tag ' + l.tag}>{l.tag}</span>
            <span className="db-log-msg db-mono" dangerouslySetInnerHTML={{ __html: l.msg.replace(/(&lt;REDACTED:[^&]+&gt;|<REDACTED:[^>]+>)/g, '<span class="db-redacted">$1</span>') }} />
            {l.guard && <span className="db-log-guard"><Icon name="shield-alert" size={12} /> {l.guard} · blocked</span>}
          </div>
        ))}
        {rows.length === 0 && <div className="db-muted db-mono" style={{ padding: 16 }}>No guardrail events for this run.</div>}
      </div>
    </div>
  );
}

function AnalyticsTab({ a }) {
  const tokens = [0.9, 1.2, 0.8, 1.6, 1.4, 1.9, 1.84];
  const spend = [3.1, 4.0, 2.8, 5.2, 4.6, 6.0, 4.82];
  const latency = [4.2, 3.8, 5.1, 4.6, 3.9, 4.4, 4.1];
  const labels = ['Th', 'Fr', 'Sa', 'Su', 'Mo', 'Tu', 'We'];
  return (
    <div className="db-analytics">
      <div className="db-metric-grid">
        <MetricCard label="Tokens (7d)" n="9.6" unit="M" delta="+14% vs prior week" dir="up" />
        <MetricCard label="Spend (7d)" n="$30.5" delta="+8% vs prior week" dir="up" />
        <MetricCard label="Avg latency" n="4.1" unit="s" delta="−0.3s vs baseline" dir="up" />
        <MetricCard label="Tool calls" n="1,204" delta="git, fetch, fs top 3" />
      </div>

      <div className="db-chart-grid">
        <div className="db-panel">
          <div className="db-panel-head"><h3 className="db-panel-title">Tokens / day <span className="db-mono db-muted">millions</span></h3></div>
          <BarChart data={tokens} labels={labels} color="var(--accent)" />
        </div>
        <div className="db-panel">
          <div className="db-panel-head"><h3 className="db-panel-title">Spend / day <span className="db-mono db-muted">USD</span></h3></div>
          <BarChart data={spend} labels={labels} color="var(--accent-deep)" />
        </div>
      </div>

      <div className="db-chart-grid">
        <div className="db-panel">
          <div className="db-panel-head"><h3 className="db-panel-title">Latency trend <span className="db-mono db-muted">seconds / run</span></h3></div>
          <div style={{ padding: '8px 4px' }}><Sparkline data={latency} w={520} h={90} /></div>
          <div className="db-spark-labels db-mono">{labels.map(l => <span key={l}>{l}</span>)}</div>
        </div>
        <div className="db-panel">
          <div className="db-panel-head"><h3 className="db-panel-title">Cost by model</h3></div>
          <div className="db-breakdown">
            {[['claude-sonnet-4', 68, 'var(--accent)'], ['claude-haiku-4', 20, 'var(--accent-soft)'], ['gpt-5-codex', 12, 'var(--accent-deep)']].map(([m, p, c]) => (
              <div key={m} className="db-breakdown-row">
                <span className="db-breakdown-label db-mono">{m}</span>
                <div className="db-breakdown-track"><div className="db-breakdown-fill" style={{ width: p + '%', background: c }} /></div>
                <span className="db-breakdown-pct db-mono">{p}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { MemoryTab, RunsTab, LogsTab, AnalyticsTab });
