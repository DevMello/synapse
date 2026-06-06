// Agent Detail — Editor tab. A Markdown editor for everything that defines an
// agent's behavior: the system prompt, per-platform skill definitions, and the
// ruleset/blockers. CodeMirror 6 drives the editor; a lightweight renderer powers
// the live preview. Template variables ({{var}}) are detected and validated, and
// Saving never mutates in place — it creates a new version and re-pushes to the
// daemon (surfaced via a toast).
import { useMemo, useState, type ReactNode } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { markdown } from "@codemirror/lang-markdown";
import { EditorView } from "@codemirror/view";
import { Icon, Button } from "../../../components/Primitives";
import { Segmented, daemonName } from "../../../components/Common";
import { useCurrentAgent } from "../context";
import { usePrompt, useSkills } from "../../../api/queries";
import { useUI } from "../../../store/ui";
import type { Skill } from "../../../types";

type Platform = "macos" | "linux" | "windows";

const PLATFORM_OPTIONS: { value: Platform; label: string }[] = [
  { value: "macos", label: "macOS" },
  { value: "linux", label: "Linux" },
  { value: "windows", label: "Windows" },
];

// Skill.scope is human text ("all platforms", "macOS · Linux", "Windows"). A skill
// is available on a platform when its scope is universal or names that platform.
const PLATFORM_LABEL: Record<Platform, string> = { macos: "macOS", linux: "Linux", windows: "Windows" };

function skillOnPlatform(skill: Skill, platform: Platform): boolean {
  const scope = skill.scope.toLowerCase();
  if (scope.includes("all")) return true;
  return scope.includes(PLATFORM_LABEL[platform].toLowerCase());
}

// A seed body for skills/rulesets so the preview and variable detection have
// something real to work with (mock data ships names + scope, not bodies).
function skillSeed(skill: Skill): string {
  return `# ${skill.name}

Scope: **${skill.scope}** · ${skill.size}

## What it does
- Knowledge this agent can draw on when the task matches.
- Edit freely — saving cuts a new version and re-pushes to the daemon.
`;
}

const RULESET_SEED = `# Blockers — northwind

## Hard blocks
- Never \`git push --force\` to a protected branch.
- Never delete files outside the repo root.

## Require approval
- Any outbound payment or refund via {{payment_provider}}.
- Network calls to a host not on the allow-list.
`;

interface EditorFile {
  id: string;
  name: string;
  label: string;
  seed: string;
}

// --- tiny markdown renderer (headings, bold, code, lists, vars) ---
function inlineMd(t: string): string {
  return t
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\{\{(\w+)\}\}/g, '<span class="db-md-var">{{$1}}</span>');
}

function renderMd(src: string): ReactNode[] {
  const lines = src.split("\n");
  const out: ReactNode[] = [];
  let list: ReactNode[] | null = null;
  const flush = () => {
    if (list) { out.push(<ul key={"ul" + out.length} className="db-md-ul">{list}</ul>); list = null; }
  };
  lines.forEach((ln, i) => {
    if (/^#\s/.test(ln)) { flush(); out.push(<h1 key={i} className="db-md-h1" dangerouslySetInnerHTML={{ __html: inlineMd(ln.slice(2)) }} />); }
    else if (/^##\s/.test(ln)) { flush(); out.push(<h2 key={i} className="db-md-h2" dangerouslySetInnerHTML={{ __html: inlineMd(ln.slice(3)) }} />); }
    else if (/^-\s/.test(ln)) { const item = <li key={i} dangerouslySetInnerHTML={{ __html: inlineMd(ln.slice(2)) }} />; if (!list) list = []; list.push(item); }
    else { flush(); if (ln.trim()) out.push(<p key={i} className="db-md-p" dangerouslySetInnerHTML={{ __html: inlineMd(ln) }} />); }
  });
  flush();
  return out;
}

// CodeMirror theme that blends into the .db-editor-pane chrome.
const editorTheme = EditorView.theme({
  "&": { height: "100%", fontSize: "13px", background: "var(--paper)", color: "var(--ink)" },
  ".cm-scroller": { fontFamily: "var(--font-mono)", lineHeight: "1.7", padding: "8px 6px" },
  ".cm-content": { padding: "10px 14px" },
  "&.cm-focused": { outline: "none" },
  ".cm-gutters": { background: "var(--paper)", border: "none", color: "var(--mute)" },
  ".cm-activeLine": { background: "rgba(0,0,0,0.02)" },
  ".cm-activeLineGutter": { background: "transparent" },
});

export default function EditorTab() {
  const agent = useCurrentAgent();
  const prompt = usePrompt().data ?? "";
  const skills = useSkills().data ?? [];
  const showToast = useUI((s) => s.showToast);

  const [platform, setPlatform] = useState<Platform>("macos");

  // The file list depends on the platform: skills are platform-scoped, so a
  // different OS surfaces a different set of skill files.
  const files = useMemo<EditorFile[]>(() => {
    const skillFiles: EditorFile[] = skills
      .filter((s) => skillOnPlatform(s, platform))
      .map((s) => ({
        id: "skill:" + s.name,
        name: s.name + ".md",
        label: "Skill · " + s.name,
        seed: skillSeed(s),
      }));
    return [
      { id: "prompt", name: "system-prompt.md", label: "System prompt", seed: prompt },
      ...skillFiles,
      { id: "ruleset", name: "rulesets.md", label: "Ruleset · blockers", seed: RULESET_SEED },
    ];
  }, [skills, platform, prompt]);

  const [fileId, setFileId] = useState<string>("prompt");
  // Per-file edited text + dirty tracking. Keyed by file id so switching files
  // (or platforms) preserves in-flight edits.
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  // Resolve the active file, falling back to the first file when the current
  // selection drops out of the list (e.g. after a platform switch).
  const active = files.find((f) => f.id === fileId) ?? files[0];
  const text = drafts[active.id] ?? active.seed;
  const dirty = drafts[active.id] !== undefined && drafts[active.id] !== active.seed;

  const vars = useMemo(() => {
    const matches = text.match(/\{\{(\w+)\}\}/g) ?? [];
    return [...new Set(matches.map((v) => v.slice(2, -2)))];
  }, [text]);

  const onChange = (value: string) => {
    setDrafts((d) => ({ ...d, [active.id]: value }));
  };

  const onSave = () => {
    setDrafts((d) => {
      const next = { ...d };
      delete next[active.id]; // committed — drop the draft so it's clean again
      return next;
    });
    showToast({ text: `Saved as v13 — pushed to ${daemonName(agent.daemonId)}` });
  };

  return (
    <div className="db-editor">
      <div className="db-editor-bar">
        <div className="db-editor-files">
          {files.map((f) => (
            <button
              key={f.id}
              className={"db-editor-file" + (active.id === f.id ? " active" : "")}
              onClick={() => setFileId(f.id)}
            >
              <Icon name="file-text" size={13} />{f.label}
            </button>
          ))}
        </div>
        <div className="db-editor-bar-r">
          <Segmented value={platform} onChange={setPlatform} options={PLATFORM_OPTIONS} />
          <Button variant="primary" icon="save" disabled={!dirty} onClick={onSave}>Save version</Button>
        </div>
      </div>

      <div className="db-editor-split">
        <div className="db-editor-pane">
          <div className="db-editor-pane-head db-mono">
            <Icon name="code" size={13} /> {active.name}{dirty && <span className="db-dirty-dot" />}
          </div>
          <CodeMirror
            value={text}
            onChange={onChange}
            extensions={[markdown(), EditorView.lineWrapping, editorTheme]}
            basicSetup={{ lineNumbers: false, foldGutter: false, highlightActiveLine: true }}
            style={{ flex: 1, overflow: "auto" }}
          />
        </div>
        <div className="db-editor-pane">
          <div className="db-editor-pane-head db-mono"><Icon name="eye" size={13} /> Live preview</div>
          <div className="db-editor-preview">{renderMd(text)}</div>
        </div>
      </div>

      <div className="db-editor-foot">
        <div className="db-editor-vars">
          <span className="db-sublabel">Template variables</span>
          {vars.length
            ? vars.map((v) => <span key={v} className="db-var-chip db-mono">{"{{" + v + "}}"}</span>)
            : <span className="db-muted db-mono">none</span>}
          {vars.length > 0 && (
            <span className="db-var-ok db-mono"><Icon name="check" size={12} /> all resolved</span>
          )}
        </div>
        <div className="db-muted db-mono">Saving never mutates in place — it creates a new version and re-pushes to the daemon.</div>
      </div>
    </div>
  );
}
