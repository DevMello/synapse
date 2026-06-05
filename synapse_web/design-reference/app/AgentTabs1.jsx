/* Synapse Web UI — Agent tabs (part 1): Editor, Versions, Schedule, Tools, Environment */

// --- tiny markdown renderer (headings, bold, code, lists, vars) ---
function renderMd(src) {
  const lines = src.split('\n');
  const out = [];
  let list = null;
  const inline = (t) => {
    let h = t
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\{\{(\w+)\}\}/g, '<span class="db-md-var">{{$1}}</span>');
    return h;
  };
  lines.forEach((ln, i) => {
    if (/^#\s/.test(ln)) { if (list) { out.push(list); list = null; } out.push(<h1 key={i} className="db-md-h1" dangerouslySetInnerHTML={{ __html: inline(ln.slice(2)) }} />); }
    else if (/^##\s/.test(ln)) { if (list) { out.push(list); list = null; } out.push(<h2 key={i} className="db-md-h2" dangerouslySetInnerHTML={{ __html: inline(ln.slice(3)) }} />); }
    else if (/^-\s/.test(ln)) { const item = <li key={i} dangerouslySetInnerHTML={{ __html: inline(ln.slice(2)) }} />; if (!list) list = []; list.push(item); }
    else { if (list) { out.push(<ul key={'ul'+i} className="db-md-ul">{list}</ul>); list = null; } if (ln.trim()) out.push(<p key={i} className="db-md-p" dangerouslySetInnerHTML={{ __html: inline(ln) }} />); }
  });
  if (list) out.push(<ul key="ul-last" className="db-md-ul">{list}</ul>);
  return out;
}

const EDITOR_FILES = [
  { id: 'prompt', name: 'system-prompt.md', label: 'System prompt' },
  { id: 'skill1', name: 'review-checklist.md', label: 'Skill · review-checklist' },
  { id: 'ruleset', name: 'rulesets.md', label: 'Ruleset · blockers' },
];

function EditorTab({ a, toast }) {
  const [file, setFile] = React.useState('prompt');
  const [text, setText] = React.useState(DATA.PROMPT);
  const [platform, setPlatform] = React.useState('macos');
  const [dirty, setDirty] = React.useState(false);
  const vars = (text.match(/\{\{(\w+)\}\}/g) || []).map(v => v.slice(2, -2)).filter((v, i, arr) => arr.indexOf(v) === i);

  return (
    <div className="db-editor">
      <div className="db-editor-bar">
        <div className="db-editor-files">
          {EDITOR_FILES.map(f => (
            <button key={f.id} className={'db-editor-file' + (file === f.id ? ' active' : '')} onClick={() => setFile(f.id)}>
              <Icon name="file-text" size={13} />{f.label}
            </button>
          ))}
        </div>
        <div className="db-editor-bar-r">
          <Segmented value={platform} onChange={setPlatform} options={[
            { value: 'macos', label: 'macOS' }, { value: 'linux', label: 'Linux' }, { value: 'windows', label: 'Windows' },
          ]} />
          <Button variant="primary" icon="save" disabled={!dirty} onClick={() => { setDirty(false); toast({ msg: 'Saved as v13 — pushed to ' + daemonName(a.daemonId), icon: 'check' }); }}>Save version</Button>
        </div>
      </div>

      <div className="db-editor-split">
        <div className="db-editor-pane">
          <div className="db-editor-pane-head db-mono"><Icon name="code" size={13} /> {EDITOR_FILES.find(f => f.id === file).name}{dirty && <span className="db-dirty-dot" />}</div>
          <textarea className="db-editor-text db-mono" value={text} onChange={e => { setText(e.target.value); setDirty(true); }} spellCheck={false} />
        </div>
        <div className="db-editor-pane">
          <div className="db-editor-pane-head db-mono"><Icon name="eye" size={13} /> Live preview</div>
          <div className="db-editor-preview">{renderMd(text)}</div>
        </div>
      </div>

      <div className="db-editor-foot">
        <div className="db-editor-vars">
          <span className="db-sublabel">Template variables</span>
          {vars.length ? vars.map(v => <span key={v} className="db-var-chip db-mono">{'{{' + v + '}}'}</span>) : <span className="db-muted db-mono">none</span>}
          <span className="db-var-ok db-mono"><Icon name="check" size={12} /> all resolved</span>
        </div>
        <div className="db-muted db-mono">Saving never mutates in place — it creates a new version and re-pushes to the daemon.</div>
      </div>
    </div>
  );
}

function VersionsTab({ a, toast }) {
  const [left, setLeft] = React.useState('v11');
  const [right, setRight] = React.useState('v12');
  const DIFF = [
    { t: 'ctx', l: '## Operating rules' },
    { t: 'ctx', l: '- Read `reports/style-guide.md` before commenting on style.' },
    { t: 'del', l: '- Never approve a PR that drops coverage below 75%.' },
    { t: 'add', l: '- Never approve a PR that drops coverage below {{min_coverage}}%.' },
    { t: 'ctx', l: '- Flag any new network call that is not on the allow-list.' },
    { t: 'add', l: '- Summarize findings in `reports/review/{{pr_number}}.md`.' },
  ];
  return (
    <div className="db-versions">
      <div className="db-versions-list">
        {DATA.versions.map(v => (
          <div key={v.id} className={'db-version-row' + (v.current ? ' current' : '')}>
            <div className="db-version-rail"><span className={'db-version-dot' + (v.current ? ' current' : '')} /></div>
            <div className="db-version-meta">
              <div className="db-version-top">
                <span className="db-version-label db-mono">{v.label}</span>
                {v.tags.map(t => <span key={t} className={'db-version-tag ' + t.replace(/\s/g,'-')}>{t}</span>)}
                {v.current && <span className="db-version-tag current">current</span>}
              </div>
              <div className="db-version-msg">{v.msg}</div>
              <div className="db-version-sub db-mono">{v.author} · {v.when}</div>
            </div>
            <div className="db-version-actions">
              <button className={'db-diff-pick' + (left === v.id ? ' active' : '')} onClick={() => setLeft(v.id)}>base</button>
              <button className={'db-diff-pick' + (right === v.id ? ' active' : '')} onClick={() => setRight(v.id)}>compare</button>
              {!v.current && <button className="db-rollback" onClick={() => toast({ msg: `Rolled back to ${v.label} — re-pushed to daemon`, icon: 'rotate-ccw', kind: 'warn' })}><Icon name="rotate-ccw" size={13} /> Roll back</button>}
            </div>
          </div>
        ))}
      </div>

      <div className="db-diff">
        <div className="db-diff-head db-mono"><Icon name="git-commit" size={14} /> diff · <b>{left}</b> → <b>{right}</b></div>
        <div className="db-diff-body db-mono">
          {DIFF.map((d, i) => (
            <div key={i} className={'db-diff-line ' + d.t}>
              <span className="db-diff-gutter">{d.t === 'add' ? '+' : d.t === 'del' ? '−' : ' '}</span>
              <span>{d.l}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ScheduleTab({ a, toast }) {
  const [mode, setMode] = React.useState('webhook');
  const [cron, setCron] = React.useState('0 2 * * *');
  const human = { '0 2 * * *': 'At 02:00, every day', '0 */6 * * *': 'Every 6 hours', '0 9 * * 1': 'At 09:00, every Monday' }[cron] || 'Custom expression';
  return (
    <div className="db-schedule">
      <div className="db-sched-l">
        <div className="db-sublabel">Trigger</div>
        <div className="db-sched-modes">
          {[{ id: 'webhook', icon: 'webhook', name: 'On webhook', desc: 'Start when an external event fires' },
            { id: 'cron', icon: 'calendar', name: 'Cron schedule', desc: 'Recurring on an expression' },
            { id: 'interval', icon: 'refresh-cw', name: 'Fixed interval', desc: 'Every N minutes/hours' },
            { id: 'oneshot', icon: 'zap', name: 'One-shot', desc: 'Run once at a time' }].map(m => (
            <button key={m.id} className={'db-sched-mode' + (mode === m.id ? ' sel' : '')} onClick={() => setMode(m.id)}>
              <span className="db-sched-mode-icon"><Icon name={m.icon} size={16} /></span>
              <div><div className="db-sched-mode-name">{m.name}</div><div className="db-sched-mode-desc">{m.desc}</div></div>
              {mode === m.id && <Icon name="check-circle" size={16} style={{ color: 'var(--accent)', marginLeft: 'auto' }} />}
            </button>
          ))}
        </div>

        {mode === 'cron' && (
          <div className="db-sched-cron">
            <div className="db-sublabel" style={{ marginTop: 18 }}>Expression</div>
            <input className="db-input db-mono" value={cron} onChange={e => setCron(e.target.value)} />
            <div className="db-cron-presets">
              {['0 2 * * *', '0 */6 * * *', '0 9 * * 1'].map(c => <button key={c} className="db-cron-preset db-mono" onClick={() => setCron(c)}>{c}</button>)}
            </div>
            <div className="db-cron-human db-mono"><Icon name="clock" size={13} /> {human} · EST</div>
          </div>
        )}
        <div className="db-sublabel" style={{ marginTop: 18 }}>Missed-run policy</div>
        <Segmented value="skip" onChange={() => {}} options={[{ value: 'skip', label: 'Skip' }, { value: 'once', label: 'Run once' }, { value: 'coalesce', label: 'Coalesce' }]} />
      </div>

      <div className="db-sched-r">
        <div className="db-panel">
          <div className="db-panel-head"><h3 className="db-panel-title">Next fire times</h3></div>
          {mode === 'webhook' ? (
            <div className="db-muted db-mono" style={{ padding: '4px 0' }}>Event-driven · no scheduled fires. Listening on the agent's webhook.</div>
          ) : (
            <div className="db-fire-list">
              {['Tomorrow · 02:00 EST', 'Thu Jun 5 · 02:00 EST', 'Fri Jun 6 · 02:00 EST', 'Sat Jun 7 · 02:00 EST'].map((f, i) => (
                <div key={i} className="db-fire-row db-mono"><Icon name="clock" size={13} /> {f}</div>
              ))}
            </div>
          )}
        </div>
        <Button variant="primary" icon="save" onClick={() => toast({ msg: 'Schedule saved', icon: 'check' })} style={{ marginTop: 16 }}>Save schedule</Button>
      </div>
    </div>
  );
}

Object.assign(window, { EditorTab, VersionsTab, ScheduleTab, renderMd });
