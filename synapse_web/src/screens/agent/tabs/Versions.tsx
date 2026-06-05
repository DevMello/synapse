// Agent Detail — Versions tab. History rail (timeline + tags + per-version
// actions) on the left, a hand-rolled side-by-side diff of the two selected
// versions on the right. Ported from design-reference/app/AgentTabs1.jsx
// (VersionsTab). No Monaco — the diff is plain .db-diff-line add/del/ctx rows.
import { useMemo, useState } from "react";
import { Icon } from "../../../components/Primitives";
import { useVersions } from "../../../api/queries";
import { useUI } from "../../../store/ui";
import type { VersionTag } from "../../../types";

type DiffKind = "add" | "del" | "ctx";
interface DiffLine {
  t: DiffKind;
  l: string;
}

// Illustrative hunks keyed by the "base→compare" pair. The prototype hard-codes
// a single sample diff; we key it on the selected pair so picking two versions
// visibly updates the panel. Falls back to a generic hunk for unknown pairs.
const DIFF_HUNKS: Record<string, DiffLine[]> = {
  "v11→v12": [
    { t: "ctx", l: "## Operating rules" },
    { t: "ctx", l: "- Read `reports/style-guide.md` before commenting on style." },
    { t: "del", l: "- Never approve a PR that drops coverage below 75%." },
    { t: "add", l: "- Never approve a PR that drops coverage below {{min_coverage}}%." },
    { t: "ctx", l: "- Flag any new network call that is not on the allow-list." },
    { t: "add", l: "- Summarize findings in `reports/review/{{pr_number}}.md`." },
  ],
  "v10→v11": [
    { t: "ctx", l: "## Operating rules" },
    { t: "ctx", l: "- Read `reports/style-guide.md` before commenting on style." },
    { t: "add", l: "- Flag any new network call that is not on the allow-list." },
    { t: "ctx", l: "- Never approve a PR that drops coverage below 75%." },
  ],
  "v9→v10": [
    { t: "ctx", l: "## Voice" },
    { t: "del", l: "- Be terse. Bullet points only." },
    { t: "add", l: "- Be direct but collegial; explain the *why* behind each blocker." },
    { t: "ctx", l: "## Operating rules" },
  ],
};

function diffFor(left: string, right: string): DiffLine[] {
  const key = `${left}→${right}`;
  if (DIFF_HUNKS[key]) return DIFF_HUNKS[key];
  const rev = `${right}→${left}`;
  if (DIFF_HUNKS[rev]) {
    // Show the reverse pair by flipping add/del so the panel stays consistent.
    return DIFF_HUNKS[rev].map((d) =>
      d.t === "add" ? { t: "del", l: d.l } : d.t === "del" ? { t: "add", l: d.l } : d,
    );
  }
  return [
    { t: "ctx", l: "## Operating rules" },
    { t: "del", l: `- (rules from ${left})` },
    { t: "add", l: `- (rules from ${right})` },
    { t: "ctx", l: "- Flag any new network call that is not on the allow-list." },
  ];
}

const TAGGABLE: VersionTag[] = ["known-good", "production"];

export default function VersionsTab() {
  const { data: versions = [] } = useVersions();
  const showToast = useUI((s) => s.showToast);

  const [left, setLeft] = useState("v11");
  const [right, setRight] = useState("v12");
  // Local overlay of operator-applied tags on top of the server data.
  const [extraTags, setExtraTags] = useState<Record<string, VersionTag[]>>({});

  const diff = useMemo(() => diffFor(left, right), [left, right]);

  const toggleTag = (id: string, label: string, serverTags: VersionTag[], tag: VersionTag) => {
    const current = extraTags[id] ?? [];
    const has = serverTags.includes(tag) || current.includes(tag);
    setExtraTags((prev) => {
      const base = prev[id] ?? [];
      return {
        ...prev,
        [id]: has ? base.filter((t) => t !== tag) : [...base.filter((t) => t !== tag), tag],
      };
    });
    if (!serverTags.includes(tag)) {
      showToast(has ? `Removed “${tag}” from ${label}` : `Tagged ${label} as “${tag}”`);
    }
  };

  return (
    <div className="db-versions">
      <div className="db-versions-list">
        {versions.map((v) => {
          const tags = [...v.tags, ...(extraTags[v.id] ?? [])].filter(
            (t, i, arr) => arr.indexOf(t) === i,
          );
          return (
            <div key={v.id} className={"db-version-row" + (v.current ? " current" : "")}>
              <div className="db-version-rail">
                <span className={"db-version-dot" + (v.current ? " current" : "")} />
              </div>
              <div className="db-version-meta">
                <div className="db-version-top">
                  <span className="db-version-label db-mono">{v.label}</span>
                  {tags.map((t) => (
                    <span key={t} className={"db-version-tag " + t.replace(/\s/g, "-")}>
                      {t}
                    </span>
                  ))}
                  {v.current && <span className="db-version-tag current">current</span>}
                </div>
                <div className="db-version-msg">{v.msg}</div>
                <div className="db-version-sub db-mono">
                  {v.author} · {v.when}
                </div>
              </div>
              <div className="db-version-actions">
                <button
                  className={"db-diff-pick" + (left === v.id ? " active" : "")}
                  onClick={() => setLeft(v.id)}
                >
                  base
                </button>
                <button
                  className={"db-diff-pick" + (right === v.id ? " active" : "")}
                  onClick={() => setRight(v.id)}
                >
                  compare
                </button>
                {TAGGABLE.map((tag) => {
                  const active = tags.includes(tag);
                  return (
                    <button
                      key={tag}
                      className={"db-diff-pick" + (active ? " active" : "")}
                      title={active ? `Remove “${tag}”` : `Tag as “${tag}”`}
                      onClick={() => toggleTag(v.id, v.label, v.tags, tag)}
                    >
                      <Icon name="tag" size={11} /> {tag}
                    </button>
                  );
                })}
                {!v.current && (
                  <button
                    className="db-rollback"
                    onClick={() =>
                      showToast({
                        text: `Rolled back to ${v.label} — re-pushing to daemon`,
                        variant: "warn",
                      })
                    }
                  >
                    <Icon name="rotate-ccw" size={13} /> Roll back
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="db-diff">
        <div className="db-diff-head db-mono">
          <Icon name="git-commit" size={14} /> diff · <b>{left}</b> → <b>{right}</b>
        </div>
        <div className="db-diff-body db-mono">
          {diff.map((d, i) => (
            <div key={i} className={"db-diff-line " + d.t}>
              <span className="db-diff-gutter">
                {d.t === "add" ? "+" : d.t === "del" ? "−" : " "}
              </span>
              <span>{d.l}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
