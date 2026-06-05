/* Synapse Web UI — Agents list + New Agent wizard (hero flow) */

function Agents({ nav, state, openWizard, toast }) {
  const [view, setView] = React.useState('grid');
  const [filter, setFilter] = React.useState('all');
  const agents = DATA.agents.filter(a => filter === 'all' ? true : filter === 'running' ? a.status === 'running' : filter === 'offline' ? !a.avail : true);

  return (
    <>
      <PageHead kicker="Agents" title="Everything you" serif="point at a host"
        sub="API models and CLI tools share one control surface. Each runs on a daemon you own; deploy a new one in a single click."
        actions={<Button variant="primary" icon="plus" onClick={() => openWizard()}>New agent</Button>} />

      <div className="db-toolbar">
        <Segmented value={filter} onChange={setFilter} options={[
          { value: 'all', label: 'All' }, { value: 'running', label: 'Running' }, { value: 'offline', label: 'Unavailable' },
        ]} />
        <div className="db-toolbar-r">
          <Segmented value={view} onChange={setView} options={[
            { value: 'grid', icon: 'box', label: '' }, { value: 'list', icon: 'list', label: '' },
          ]} />
        </div>
      </div>

      {view === 'grid' ? (
        <div className="db-agent-grid">
          {agents.map(a => (
            <button key={a.id} className={'db-agent-card' + (!a.avail ? ' dim' : '')} onClick={() => nav({ view: 'agent', agentId: a.id })}>
              <div className="db-agent-top">
                <AgentAvatar engine={a.engine} size={38} />
                <Chip s={a.status} />
              </div>
              <div className="db-agent-name">{a.name}</div>
              <div className="db-agent-kind db-mono">{a.type} · {a.engine}</div>
              <p className="db-agent-desc">{a.desc}</p>
              <div className="db-agent-foot">
                <span className="db-agent-host db-mono"><Icon name="server" size={12} /> {daemonName(a.daemonId)}</span>
                <span className="db-agent-spend db-mono">${a.spendToday.toFixed(2)}</span>
              </div>
            </button>
          ))}
        </div>
      ) : (
        <div className="db-table-wrap">
          <table className="db-table">
            <thead><tr><th>Agent</th><th>Type</th><th>Host</th><th>Last run</th><th>Next</th><th>Today</th><th>Status</th></tr></thead>
            <tbody>
              {agents.map(a => (
                <tr key={a.id} className="clickable-row" onClick={() => nav({ view: 'agent', agentId: a.id })}>
                  <td className="db-cell-primary">{a.name}</td>
                  <td className="db-mono">{a.engine}</td>
                  <td className="db-mono">{daemonName(a.daemonId)}</td>
                  <td className="db-mono">{a.lastRun}</td>
                  <td className="db-mono">{a.nextRun}</td>
                  <td className="db-mono">${a.spendToday.toFixed(2)}</td>
                  <td><Chip s={a.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

/* ---- New Agent Wizard ---- */
const ENGINES = [
  { id: 'claude-code', name: 'Claude Code', type: 'CLI tool', icon: 'terminal', desc: 'Anthropic agentic CLI' },
  { id: 'codex', name: 'Codex', type: 'CLI tool', icon: 'code', desc: 'OpenAI coding CLI' },
  { id: 'gemini', name: 'Gemini CLI', type: 'CLI tool', icon: 'sparkles', desc: 'Google agentic CLI' },
  { id: 'api', name: 'API model', type: 'API model', icon: 'cpu', desc: 'Direct provider API (Claude, GPT, Gemini)' },
];

function NewAgentWizard({ open, onClose, nav, toast }) {
  const [step, setStep] = React.useState(0);
  const [name, setName] = React.useState('');
  const [daemon, setDaemon] = React.useState('d-mbp');
  const [engine, setEngine] = React.useState('claude-code');
  const [template, setTemplate] = React.useState('reviewer');
  const [deploying, setDeploying] = React.useState(0); // 0..steps

  React.useEffect(() => { if (open) { setStep(0); setName(''); setDaemon('d-mbp'); setEngine('claude-code'); setTemplate('reviewer'); setDeploying(0); } }, [open]);

  const DEPLOY_STEPS = ['Reserving slot on ' + daemonName(daemon), 'Pushing agent definition', 'Installing default capabilities', 'Arming gates + redaction', 'Agent is live'];

  function deploy() {
    setStep(4);
    let i = 0;
    const tick = () => {
      i++; setDeploying(i);
      if (i < DEPLOY_STEPS.length) setTimeout(tick, 720);
      else setTimeout(() => {
        onClose();
        toast({ msg: `${name || 'new-agent'} deployed to ${daemonName(daemon)}`, icon: 'check' });
        nav({ view: 'agent', agentId: 'a-prr' });
      }, 900);
    };
    setTimeout(tick, 600);
  }

  const canNext = step === 0 ? name.trim().length > 0 : true;
  const onlineDaemons = DATA.daemons.filter(d => d.status === 'online');

  return (
    <Modal open={open} onClose={onClose} width={680}>
      <div className="db-wizard">
        <div className="db-wizard-head">
          <div className="db-wizard-steps">
            {['Name', 'Host', 'Type', 'Template', 'Deploy'].map((s, i) => (
              <div key={s} className={'db-wstep' + (i === step ? ' active' : '') + (i < step ? ' done' : '')}>
                <span className="db-wstep-dot">{i < step ? <Icon name="check" size={12} stroke={2.5} /> : i + 1}</span>
                <span className="db-wstep-label">{s}</span>
              </div>
            ))}
          </div>
          <button className="db-icon-btn db-wizard-close" onClick={onClose}><Icon name="x" size={16} /></button>
        </div>

        <div className="db-wizard-body">
          {step === 0 && (
            <div className="db-wstep-pane">
              <h2 className="db-wizard-h2">Name your <span className="serif-accent">agent</span></h2>
              <p className="db-wizard-p">A short, lowercase handle. You can change it later.</p>
              <input className="db-input db-input-lg db-mono" autoFocus placeholder="pr-reviewer" value={name}
                onChange={e => setName(e.target.value.replace(/[^a-z0-9-]/g, ''))} />
              <input className="db-input" placeholder="What does it do? (optional)" />
            </div>
          )}

          {step === 1 && (
            <div className="db-wstep-pane">
              <h2 className="db-wizard-h2">Pick a <span className="serif-accent">daemon</span> to host it</h2>
              <p className="db-wizard-p">The agent's keys and execution stay on this machine.</p>
              <div className="db-wiz-daemons">
                {onlineDaemons.map(d => (
                  <button key={d.id} className={'db-wiz-daemon' + (daemon === d.id ? ' sel' : '')} onClick={() => setDaemon(d.id)}>
                    <span className={'db-status-dot ' + d.status} />
                    <div className="db-wiz-daemon-meta">
                      <div className="db-wiz-daemon-name">{d.name}</div>
                      <div className="db-wiz-daemon-os db-mono">{d.os} · {d.activeRuns} active</div>
                    </div>
                    {daemon === d.id && <Icon name="check-circle" size={18} style={{ color: 'var(--accent)' }} />}
                  </button>
                ))}
                <button className={'db-wiz-daemon tag' + (daemon === 'tag' ? ' sel' : '')} onClick={() => setDaemon('tag')}>
                  <span className="db-status-dot tagdot"><Icon name="tag" size={12} /></span>
                  <div className="db-wiz-daemon-meta">
                    <div className="db-wiz-daemon-name">Any daemon tagged <span className="db-mono">ci</span></div>
                    <div className="db-wiz-daemon-os db-mono">scheduler picks a healthy host</div>
                  </div>
                  {daemon === 'tag' && <Icon name="check-circle" size={18} style={{ color: 'var(--accent)' }} />}
                </button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="db-wstep-pane">
              <h2 className="db-wizard-h2">Choose the <span className="serif-accent">type</span></h2>
              <p className="db-wizard-p">A CLI tool runs as a process; an API model calls a provider directly.</p>
              <div className="db-wiz-engines">
                {ENGINES.map(e => (
                  <button key={e.id} className={'db-wiz-engine' + (engine === e.id ? ' sel' : '')} onClick={() => setEngine(e.id)}>
                    <span className="db-wiz-engine-icon"><Icon name={e.icon} size={18} /></span>
                    <div className="db-wiz-engine-name">{e.name}</div>
                    <div className="db-wiz-engine-type db-mono">{e.type}</div>
                    <div className="db-wiz-engine-desc">{e.desc}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="db-wstep-pane">
              <h2 className="db-wizard-h2">Start from a <span className="serif-accent">template</span></h2>
              <p className="db-wizard-p">Blank, or a one-click install from the Marketplace.</p>
              <div className="db-wiz-templates">
                {DATA.templates.map(t => (
                  <button key={t.id} className={'db-wiz-template' + (template === t.id ? ' sel' : '')} onClick={() => setTemplate(t.id)}>
                    <span className="db-wiz-tpl-icon"><Icon name={t.icon} size={16} /></span>
                    <div className="db-wiz-tpl-meta">
                      <div className="db-wiz-tpl-name">{t.name}</div>
                      <div className="db-wiz-tpl-desc">{t.desc}</div>
                    </div>
                    <div className="db-wiz-tpl-right">
                      <span className="db-wiz-tpl-kicker db-mono">{t.kicker}</span>
                      {t.rating && <span className="db-wiz-tpl-rating db-mono"><Icon name="star" size={11} /> {t.rating}</span>}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="db-wstep-pane db-deploy-pane">
              <div className="db-deploy-terminal">
                <div className="term-bar"><span className="term-dots"><i /><i /><i /></span><span className="term-file">deploy · {name || 'new-agent'} → {daemonName(daemon)}</span></div>
                <div className="db-deploy-body">
                  {DEPLOY_STEPS.map((s, i) => (
                    <div key={i} className={'db-deploy-line' + (deploying > i ? ' done' : deploying === i ? ' active' : ' pending')}>
                      {deploying > i ? <span className="db-deploy-tick"><Icon name="check" size={13} stroke={2.5} /></span>
                        : deploying === i ? <span className="db-spin light" />
                        : <span className="db-deploy-dot" />}
                      <span>{s}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {step < 4 && (
          <div className="db-wizard-foot">
            <div className="db-wizard-summary db-mono">
              {name && <span className="db-chip-soft">{name}</span>}
              {step >= 1 && <span className="db-chip-soft">{daemonName(daemon)}</span>}
              {step >= 2 && <span className="db-chip-soft">{ENGINES.find(e => e.id === engine).name}</span>}
            </div>
            <div className="db-wizard-nav">
              {step > 0 && <Button variant="outline-light" onClick={() => setStep(step - 1)}>Back</Button>}
              {step < 3 && <Button variant="primary" disabled={!canNext} onClick={() => setStep(step + 1)}>Continue<Icon name="arrow-right" size={14} stroke={2} /></Button>}
              {step === 3 && <Button variant="primary" icon="zap" onClick={deploy}>Deploy agent</Button>}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

Object.assign(window, { Agents, NewAgentWizard });
