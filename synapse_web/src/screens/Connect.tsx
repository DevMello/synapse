// Synapse Web UI — Connect a device (OAuth 2.0 Device Authorization Grant).
// Full-bleed, ember-lit verification stage. The app shell renders /connect outside
// the padded content area, so this component owns its own absolute `.db-connect-stage`.
// Flow: enter the 8-char user_code → verify the requesting device's metadata
// (a security step against phished codes) → approve (success) or deny.
import { useRef, useState, type ClipboardEvent, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Icon, HatchCorners } from "../components/Primitives";
import { useUI } from "../store/ui";
import { data } from "../api/queries";

type Step = "enter" | "verify" | "approved";

// The device requesting authorization. No live device-auth backend exists, so this is
// a plausible new machine running `synapse login` (identity shape mirrors data.daemons).
const REQ = {
  hostname: "jin-thinkpad",
  os: "Ubuntu 24.04 LTS",
  ip: "73.202.88.42",
  platform: "linux/amd64",
  when: "just now",
  city: "San Francisco, US",
} as const;

const EMPTY: string[] = ["", "", "", "", "", "", "", ""];

export default function Connect() {
  const navigate = useNavigate();
  const showToast = useUI((s) => s.showToast);
  const setWizard = useUI((s) => s.setWizard);

  const [step, setStep] = useState<Step>("enter");
  const [digits, setDigits] = useState<string[]>(EMPTY);
  const refs = useRef<Array<HTMLInputElement | null>>([]);

  const orgName = data.ORG.name;
  const code = digits.join("");
  const full = code.length === 8;

  function setDigit(i: number, raw: string) {
    const v = raw.replace(/[^a-zA-Z0-9]/g, "").toUpperCase().slice(0, 1);
    setDigits((prev) => {
      const next = [...prev];
      next[i] = v;
      return next;
    });
    if (v && i < 7) refs.current[i + 1]?.focus();
  }

  function onKey(i: number, e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace" && !digits[i] && i > 0) refs.current[i - 1]?.focus();
  }

  // Pre-fill from a pasted `verification_uri_complete` / printed code (e.g. ABCD-1234).
  function onPaste(e: ClipboardEvent<HTMLDivElement>) {
    const txt = (e.clipboardData.getData("text") || "")
      .replace(/[^a-zA-Z0-9]/g, "").toUpperCase().slice(0, 8).split("");
    if (!txt.length) return;
    e.preventDefault();
    setDigits((prev) => prev.map((_, i) => txt[i] || ""));
    refs.current[Math.min(txt.length, 7)]?.focus();
  }

  // Mimic the link / QR pre-fill affordance: drop in the demo code ABCD-1234.
  function prefillFromLink() {
    setDigits(["A", "B", "C", "D", "1", "2", "3", "4"]);
  }

  function approve() {
    setStep("approved");
    showToast({ text: `${REQ.hostname} paired — now online` });
  }

  function deny() {
    showToast({ text: "Device denied", variant: "warn" });
    navigate("/daemons");
  }

  return (
    <div className="db-connect-stage">
      <div className="db-connect-bg">
        <div className="fx-grid-dark" style={{ position: "absolute", inset: 0, opacity: 0.6 }} />
        <div className="fx-aurora" />
        <div className="fx-noise" />
      </div>

      <div className="db-connect-card panel-dark">
        <HatchCorners />
        <div className="db-connect-top">
          <span className="eyebrow"><span className="eyebrow-pulse" /> Device authorization · OAuth 2.0</span>
        </div>

        {step === "enter" && (
          <div className="db-connect-pane">
            <h1 className="db-connect-h1">Connect a <span className="serif-accent">new device</span></h1>
            <p className="db-connect-sub">
              A machine running <span className="db-mono">synapse login</span> printed an 8-character code.
              Enter it to bind that device to <b>{orgName}</b>.
            </p>
            <div className="db-code-input" onPaste={onPaste}>
              {digits.map((d, i) => (
                <span key={i} style={{ display: "contents" }}>
                  <input
                    ref={(el) => { refs.current[i] = el; }}
                    className="db-code-box"
                    value={d}
                    maxLength={1}
                    inputMode="text"
                    autoFocus={i === 0}
                    aria-label={`Code character ${i + 1}`}
                    onChange={(e) => setDigit(i, e.target.value)}
                    onKeyDown={(e) => onKey(i, e)}
                  />
                  {i === 3 && <span className="db-code-dash">—</span>}
                </span>
              ))}
            </div>
            <div className="db-connect-actions">
              <button className="btn btn-primary" disabled={!full} onClick={() => setStep("verify")}>
                Continue <Icon name="arrow-right" size={14} stroke={2} />
              </button>
              <button className="btn btn-ghost-dark" onClick={prefillFromLink}>
                <Icon name="qr-code" size={15} />Use the link / QR
              </button>
            </div>
            <p className="db-connect-foot db-mono">
              Codes expire ~10 min after <span className="db-accent">synapse login</span> · single-use
            </p>
          </div>
        )}

        {step === "verify" && (
          <div className="db-connect-pane">
            <h1 className="db-connect-h1">Is this <span className="serif-accent">your device?</span></h1>
            <p className="db-connect-sub">
              Code{" "}
              <span className="db-mono db-accent">{digits.slice(0, 4).join("")}-{digits.slice(4).join("")}</span>{" "}
              was requested by the machine below. Approve only if you recognise it.
            </p>
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
            <div className="db-verify-warn db-mono">
              <Icon name="shield-alert" size={14} /> If you didn&apos;t start this, deny it — a code may have
              been phished onto the wrong device.
            </div>
            <div className="db-connect-actions">
              <button className="btn btn-primary" onClick={approve}>
                <Icon name="shield-check" size={15} stroke={2} />Approve device
              </button>
              <button className="btn btn-ghost-dark" onClick={deny}>Deny</button>
              <button className="db-text-link" onClick={() => setStep("enter")}>Back</button>
            </div>
          </div>
        )}

        {step === "approved" && (
          <div className="db-connect-pane db-connect-done">
            <span className="db-connect-check"><Icon name="check" size={34} stroke={2.5} /></span>
            <h1 className="db-connect-h1">{REQ.hostname} is <span className="serif-accent">live</span></h1>
            <p className="db-connect-sub">
              The device is bound to <b>{orgName}</b> and now appears in your Daemons list as online.
              The CLI session has been authorized.
            </p>
            <div className="db-connect-actions">
              <button className="btn btn-primary" onClick={() => navigate("/daemons")}>
                View daemons<Icon name="arrow-right" size={14} stroke={2} />
              </button>
              <button
                className="btn btn-ghost-dark"
                onClick={() => { setWizard(true); navigate("/agents"); }}
              >
                Deploy an agent to it
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
