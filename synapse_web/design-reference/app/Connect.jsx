/* Synapse Web UI — Connect a device (OAuth device-code verification) */

function Connect({ nav, toast }) {
  const [step, setStep] = React.useState('enter'); // enter | verify | approved
  const [digits, setDigits] = React.useState(['', '', '', '', '', '', '', '']);
  const refs = React.useRef([]);

  const REQ = { hostname: 'jin-thinkpad', os: 'Ubuntu 24.04 LTS', ip: '73.202.88.42', platform: 'linux/amd64', when: 'just now', city: 'San Francisco, US' };

  function setDigit(i, v) {
    v = v.replace(/[^a-zA-Z0-9]/g, '').toUpperCase().slice(0, 1);
    setDigits(prev => { const n = [...prev]; n[i] = v; return n; });
    if (v && i < 7) refs.current[i + 1] && refs.current[i + 1].focus();
  }
  function onKey(i, e) {
    if (e.key === 'Backspace' && !digits[i] && i > 0) refs.current[i - 1].focus();
  }
  function onPaste(e) {
    const txt = (e.clipboardData.getData('text') || '').replace(/[^a-zA-Z0-9]/g, '').toUpperCase().slice(0, 8).split('');
    if (txt.length) { e.preventDefault(); setDigits(d => d.map((_, i) => txt[i] || '')); refs.current[Math.min(txt.length, 7)].focus(); }
  }
  const code = digits.join('');
  const full = code.length === 8;

  function approve() {
    setStep('approved');
    toast({ msg: `${REQ.hostname} paired — now online`, icon: 'check' });
  }

  return (
    <div className="db-connect-stage">
      <div className="db-connect-bg">
        <div className="fx-grid-dark" style={{ position: 'absolute', inset: 0, opacity: 0.6 }} />
        <div className="fx-aurora" />
        <div className="fx-noise" />
      </div>

      <div className="db-connect-card panel-dark">
        <HatchCorners />
        <div className="db-connect-top">
          <span className="eyebrow"><span className="eyebrow-pulse" /> Device authorization · OAuth 2.0</span>
        </div>

        {step === 'enter' && (
          <div className="db-connect-pane">
            <h1 className="db-connect-h1">Connect a <span className="serif-accent">new device</span></h1>
            <p className="db-connect-sub">A machine running <span className="db-mono">synapse login</span> printed an 8-character code. Enter it to bind that device to <b>{DATA.ORG.name}</b>.</p>
            <div className="db-code-input" onPaste={onPaste}>
              {digits.map((d, i) => (
                <React.Fragment key={i}>
                  <input ref={el => refs.current[i] = el} className="db-code-box" value={d} maxLength={1}
                    inputMode="text" autoFocus={i === 0}
                    onChange={e => setDigit(i, e.target.value)} onKeyDown={e => onKey(i, e)} />
                  {i === 3 && <span className="db-code-dash">—</span>}
                </React.Fragment>
              ))}
            </div>
            <div className="db-connect-actions">
              <button className="btn btn-primary" disabled={!full} onClick={() => setStep('verify')}>
                Continue <Icon name="arrow-right" size={14} stroke={2} />
              </button>
              <button className="btn btn-ghost-dark" onClick={() => setDigits(['A','B','C','D','1','2','3','4'])}>
                <Icon name="qr-code" size={15} />Use the link / QR
              </button>
            </div>
            <p className="db-connect-foot db-mono">Codes expire ~10 min after <span className="db-accent">synapse login</span> · single-use</p>
          </div>
        )}

        {step === 'verify' && (
          <div className="db-connect-pane">
            <h1 className="db-connect-h1">Is this <span className="serif-accent">your device?</span></h1>
            <p className="db-connect-sub">Code <span className="db-mono db-accent">{digits.slice(0,4).join('')}-{digits.slice(4).join('')}</span> was requested by the machine below. Approve only if you recognise it.</p>
            <div className="db-device-card">
              <span className="db-device-glyph"><Icon name="monitor" size={20} /></span>
              <div className="db-device-meta">
                <div className="db-device-name">{REQ.hostname}</div>
                <div className="db-device-rows db-mono">
                  <span><Icon name="cpu" size={12} /> {REQ.os} · {REQ.platform}</span>
                  <span><Icon name="globe" size={12} /> {REQ.ip} · {REQ.city}</span>
                  <span><Icon name="clock" size={12} /> requested {REQ.when}</span>
                </div>
              </div>
            </div>
            <div className="db-verify-warn db-mono"><Icon name="shield-alert" size={14} /> If you didn't start this, deny it — a code may have been phished onto the wrong device.</div>
            <div className="db-connect-actions">
              <button className="btn btn-primary" onClick={approve}><Icon name="shield-check" size={15} stroke={2} />Approve device</button>
              <button className="btn btn-ghost-dark" onClick={() => { toast({ msg: 'Device denied', kind: 'warn', icon: 'x' }); nav({ view: 'daemons' }); }}>Deny</button>
              <button className="db-text-link" onClick={() => setStep('enter')}>Back</button>
            </div>
          </div>
        )}

        {step === 'approved' && (
          <div className="db-connect-pane db-connect-done">
            <span className="db-connect-check"><Icon name="check" size={34} stroke={2.5} /></span>
            <h1 className="db-connect-h1">{REQ.hostname} is <span className="serif-accent">live</span></h1>
            <p className="db-connect-sub">The device is bound to <b>{DATA.ORG.name}</b> and now appears in your Daemons list as online. The CLI session has been authorized.</p>
            <div className="db-connect-actions">
              <button className="btn btn-primary" arrow onClick={() => nav({ view: 'daemons' })}>View daemons<Icon name="arrow-right" size={14} stroke={2} /></button>
              <button className="btn btn-ghost-dark" onClick={() => nav({ view: 'agents', newAgent: true })}>Deploy an agent to it</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { Connect });
