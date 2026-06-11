import type { ReactNode } from 'react'

/* ------------------------------------------------------------------ *
 * Shared mockup primitives
 * ------------------------------------------------------------------ */
function Window({
  title,
  chip,
  children,
}: {
  title: string
  chip?: { label: string; tone?: 'ok' | 'warn' | 'info' | 'muted' }
  children: ReactNode
}) {
  return (
    <div className="mk">
      <div className="mk-bar">
        <span className="mk-dots">
          <i />
          <i />
          <i />
        </span>
        <span className="mk-title">{title}</span>
        {chip && <span className={`mk-pill mk-pill-${chip.tone ?? 'muted'} mk-bar-chip`}>{chip.label}</span>}
      </div>
      <div className="mk-body">{children}</div>
    </div>
  )
}

function Dot({ tone }: { tone: 'on' | 'off' | 'warn' }) {
  return <span className={`mk-dot mk-dot-${tone}`} aria-hidden="true" />
}

function Toggle({ on = true }: { on?: boolean }) {
  return <span className={`mk-toggle${on ? ' is-on' : ''}`} aria-hidden="true" />
}

/* ------------------------------------------------------------------ *
 * Individual capability mockups
 * ------------------------------------------------------------------ */

const daemons = (
  <Window title="Daemons" chip={{ label: '4 hosts', tone: 'muted' }}>
    <div className="mk-list">
      {[
        ['dev-workstation', 'macOS 14 · Apple M3', 'on', '2 agents', '38 ms'],
        ['prod-eu-1', 'Ubuntu 22.04 · 16 vCPU', 'on', '5 agents', '22 ms'],
        ['edge-rpi', 'Raspbian · arm64', 'on', '1 agent', '64 ms'],
        ['ci-runner', 'Docker · ephemeral', 'off', 'idle', '—'],
      ].map(([name, host, st, agents, lat]) => (
        <div className="mk-row" key={name}>
          <div className="mk-row-main">
            <span className="mk-name">
              <Dot tone={st as 'on' | 'off'} /> {name}
            </span>
            <span className="mk-sub">{host}</span>
          </div>
          <div className="mk-row-meta">
            <span className="mk-pill mk-pill-muted">{agents}</span>
            <span className="mk-mono">{lat}</span>
          </div>
        </div>
      ))}
    </div>
    <div className="mk-foot">
      <span className="mk-mono mk-dim">heartbeat · every 30s · outbound-only</span>
    </div>
  </Window>
)

const approvals = (
  <Window title="Approval gate" chip={{ label: 'paused', tone: 'warn' }}>
    <div className="mk-approval">
      <div className="mk-approval-head">
        <span className="mk-approval-icon">✋</span>
        <div>
          <div className="mk-name">Destructive action requires approval</div>
          <div className="mk-sub">agent: incident-commander · run #3f9a2</div>
        </div>
      </div>
      <div className="mk-code mk-code-danger">$ gh pr merge 482 --squash --delete-branch</div>
      <div className="mk-kv">
        <span className="mk-pill mk-pill-warn">risk: high</span>
        <span className="mk-mono mk-dim">matched rule: branch-protection</span>
      </div>
      <div className="mk-actions">
        <span className="mk-btn mk-btn-primary">Approve</span>
        <span className="mk-btn mk-btn-ghost">Deny</span>
        <span className="mk-btn mk-btn-ghost">Edit &amp; run</span>
      </div>
      <div className="mk-foot">
        <span className="mk-mono mk-dim">routed to</span>
        <span className="mk-pill mk-pill-info">Slack</span>
        <span className="mk-pill mk-pill-info">Web UI</span>
        <span className="mk-pill mk-pill-info">TUI</span>
      </div>
    </div>
  </Window>
)

const alerts = (
  <Window title="Alerts" chip={{ label: '3 active', tone: 'warn' }}>
    <div className="mk-alert">
      <div className="mk-alert-row">
        <span className="mk-alert-icon mk-warn">◆</span>
        <div className="mk-alert-body">
          <div className="mk-name">Daily budget 84% used</div>
          <div className="mk-meter">
            <span className="mk-meter-fill" style={{ width: '84%' }} />
          </div>
          <div className="mk-sub">$42.10 of $50.00 cap · resets in 5h</div>
        </div>
      </div>
      <div className="mk-alert-row">
        <span className="mk-alert-icon mk-danger">▲</span>
        <div className="mk-alert-body">
          <div className="mk-name">Token spike — 3.2× baseline</div>
          <svg className="mk-spark" viewBox="0 0 120 28" preserveAspectRatio="none">
            <polyline
              points="0,22 16,20 32,21 48,18 64,19 80,9 96,3 120,14"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            />
          </svg>
          <div className="mk-sub">agent: data-sync · 14:32 UTC</div>
        </div>
      </div>
      <div className="mk-alert-row">
        <span className="mk-alert-icon mk-ok">●</span>
        <div className="mk-alert-body">
          <div className="mk-name">Cost cap reached — agent paused</div>
          <div className="mk-sub">awaiting human decision · auto-resume off</div>
        </div>
      </div>
    </div>
  </Window>
)

const schedules = (
  <Window title="Schedules" chip={{ label: 'cron + webhooks', tone: 'muted' }}>
    <div className="mk-list">
      {[
        ['data-quality-check', '0 2 * * *', 'in 3h 12m', 'on'],
        ['pr-triage', '*/15 * * * *', 'in 4m', 'on'],
        ['weekly-report', '0 9 * * 1', 'Mon 09:00', 'on'],
        ['log-rotate', '0 0 * * *', 'paused', 'off'],
      ].map(([name, cron, next, st]) => (
        <div className="mk-row" key={name}>
          <div className="mk-row-main">
            <span className="mk-name">{name}</span>
            <span className="mk-sub mk-mono">{cron}</span>
          </div>
          <div className="mk-row-meta">
            <span className={`mk-pill ${st === 'on' ? 'mk-pill-ok' : 'mk-pill-muted'}`}>{next}</span>
            <Toggle on={st === 'on'} />
          </div>
        </div>
      ))}
    </div>
    <div className="mk-foot">
      <span className="mk-mono mk-dim">+ trigger on inbound webhook · POST /hooks/&hellip;</span>
    </div>
  </Window>
)

const marketplace = (
  <Window title="Marketplace" chip={{ label: 'one-click install', tone: 'info' }}>
    <div className="mk-grid2">
      {[
        ['pr-reviewer', 'Reviews PRs, posts inline comments', '12.4k', true],
        ['incident-commander', 'Triage + mitigate, Slack-native', '8.1k', false],
        ['browser-use', 'Headless web automation', '21.7k', false],
        ['db-guardian', 'Schema-safe SQL operations', '4.6k', true],
      ].map(([name, desc, installs, installed]) => (
        <div className="mk-card" key={name as string}>
          <div className="mk-card-top">
            <span className="mk-card-glyph">⬡</span>
            <span className="mk-name">{name}</span>
          </div>
          <div className="mk-sub">{desc}</div>
          <div className="mk-card-foot">
            <span className="mk-mono mk-dim">↓ {installs}</span>
            <span className={`mk-btn mk-btn-mini${installed ? ' is-done' : ''}`}>
              {installed ? 'Installed' : 'Install'}
            </span>
          </div>
        </div>
      ))}
    </div>
  </Window>
)

const promptEditor = (
  <Window title="Prompt editor · pr-reviewer" chip={{ label: 'draft', tone: 'warn' }}>
    <div className="mk-editor">
      <div className="mk-editor-toolbar">
        <span className="mk-pill mk-pill-muted">claude-sonnet-4-6</span>
        <span className="mk-mono mk-dim">temp 0.2</span>
        <span className="mk-mono mk-dim">·</span>
        <span className="mk-mono mk-dim">312 tokens</span>
      </div>
      <pre className="mk-editor-code">
        <code>
          <span className="mk-ln">1</span>You are a precise code reviewer.{'\n'}
          <span className="mk-ln">2</span>Repo: <span className="mk-var">{'{{repo}}'}</span> · PR{' '}
          <span className="mk-var">{'{{pr_number}}'}</span>
          {'\n'}
          <span className="mk-ln">3</span>{'\n'}
          <span className="mk-ln">4</span>Flag security issues as <span className="mk-str">BLOCKING</span>.{'\n'}
          <span className="mk-ln">5</span>Never approve changes to <span className="mk-str">/infra</span>.{'\n'}
          <span className="mk-ln">6</span>Output inline comments only.
        </code>
      </pre>
      <div className="mk-actions">
        <span className="mk-btn mk-btn-primary">Save version</span>
        <span className="mk-btn mk-btn-ghost">Test run</span>
      </div>
    </div>
  </Window>
)

const versions = (
  <Window title="Version history · pr-reviewer" chip={{ label: 'v7', tone: 'ok' }}>
    <div className="mk-timeline">
      <div className="mk-tl-row is-current">
        <span className="mk-tl-tag">v7</span>
        <div className="mk-tl-main">
          <span className="mk-name">Tighten /infra guard</span>
          <span className="mk-sub">you · 2h ago · current</span>
        </div>
        <span className="mk-pill mk-pill-ok">live</span>
      </div>
      <div className="mk-diff">
        <div className="mk-diff-add">+ Never approve changes to /infra.</div>
        <div className="mk-diff-del">- Warn on changes to /infra.</div>
      </div>
      <div className="mk-tl-row">
        <span className="mk-tl-tag">v6</span>
        <div className="mk-tl-main">
          <span className="mk-name">Add token budget note</span>
          <span className="mk-sub">you · yesterday</span>
        </div>
        <span className="mk-btn mk-btn-mini">Rollback</span>
      </div>
      <div className="mk-tl-row">
        <span className="mk-tl-tag">v5</span>
        <div className="mk-tl-main">
          <span className="mk-name">Initial reviewer prompt</span>
          <span className="mk-sub">teammate · 3d ago</span>
        </div>
        <span className="mk-btn mk-btn-mini">Rollback</span>
      </div>
    </div>
  </Window>
)

const tools = (
  <Window title="Tools &amp; MCP servers" chip={{ label: '5 connected', tone: 'ok' }}>
    <div className="mk-list">
      {[
        ['GitHub', 'MCP · 12 tools', 'on'],
        ['Postgres', 'read-only · 1 db', 'on'],
        ['Slack', 'post-only · #sre', 'on'],
        ['Filesystem', 'sandboxed · /work', 'off'],
        ['browser-use', 'headless chromium', 'on'],
      ].map(([name, meta, st]) => (
        <div className="mk-row" key={name}>
          <div className="mk-row-main">
            <span className="mk-name">
              <span className="mk-tool-glyph">{'{ }'}</span> {name}
            </span>
            <span className="mk-sub mk-mono">{meta}</span>
          </div>
          <Toggle on={st === 'on'} />
        </div>
      ))}
    </div>
  </Window>
)

const filtering = (
  <Window title="Filtering · ruleset + redaction" chip={{ label: 'on-device', tone: 'info' }}>
    <div className="mk-filter">
      <div className="mk-filter-group">
        <div className="mk-label">Redaction</div>
        <div className="mk-chips">
          <span className="mk-pill mk-pill-info">API keys</span>
          <span className="mk-pill mk-pill-info">emails</span>
          <span className="mk-pill mk-pill-info">JWTs</span>
          <span className="mk-pill mk-pill-info">PII · Presidio</span>
        </div>
        <div className="mk-code">
          ANTHROPIC_API_KEY=<span className="mk-redacted">sk-ant-••••••••••••</span>
        </div>
      </div>
      <div className="mk-filter-group">
        <div className="mk-label">Blockers</div>
        <div className="mk-chips">
          <span className="mk-pill mk-pill-warn">DROP TABLE</span>
          <span className="mk-pill mk-pill-warn">rm -rf /</span>
          <span className="mk-pill mk-pill-warn">force-push</span>
        </div>
        <div className="mk-sub">⛔ Blocked 3 risky actions in the last 24h</div>
      </div>
    </div>
  </Window>
)

const packs = (
  <Window title="Capability packs" chip={{ label: '3 enabled', tone: 'ok' }}>
    <div className="mk-list">
      {[
        ['devops-pack', 'v2.1', 'kubectl · terraform · aws', 'on'],
        ['security-pack', 'v1.4', 'semgrep · trivy · gitleaks', 'on'],
        ['data-pack', 'v3.0', 'dbt · pandas · duckdb', 'on'],
        ['browser-pack', 'v0.9', 'playwright · scraper', 'off'],
      ].map(([name, ver, tools, st]) => (
        <div className="mk-row" key={name}>
          <div className="mk-row-main">
            <span className="mk-name">
              <span className="mk-pack-glyph">▣</span> {name} <span className="mk-ver">{ver}</span>
            </span>
            <span className="mk-sub mk-mono">{tools}</span>
          </div>
          <Toggle on={st === 'on'} />
        </div>
      ))}
    </div>
  </Window>
)

const memory = (
  <Window title="Memory editor" chip={{ label: 'org + agent', tone: 'muted' }}>
    <div className="mk-mem">
      {[
        ['Prod DB is read-replica pg-eu-2', 'project'],
        ['Deploy freeze every Fri after 17:00', 'rule'],
        ['On-call escalates to #sre then PagerDuty', 'reference'],
        ['Prefer squash-merge on all repos', 'feedback'],
      ].map(([fact, type]) => (
        <div className="mk-mem-row" key={fact}>
          <span className={`mk-pill mk-pill-${type === 'rule' ? 'warn' : type === 'feedback' ? 'ok' : 'muted'}`}>
            {type}
          </span>
          <span className="mk-mem-fact">{fact}</span>
          <span className="mk-mem-edit" aria-hidden="true">✎</span>
        </div>
      ))}
      <div className="mk-mem-add">
        <span className="mk-mono mk-dim">+ add a fact the agent should remember&hellip;</span>
      </div>
    </div>
  </Window>
)

/* ------------------------------------------------------------------ *
 * Capability registry
 * ------------------------------------------------------------------ */
export type Capability = {
  id: string
  label: string
  tag: string
  blurb: string
  href: string
  mock: ReactNode
}

export const capabilities: Capability[] = [
  {
    id: 'daemons',
    label: 'Daemons',
    tag: 'Your fleet, one pane',
    blurb:
      'Run the worker daemon on laptops, servers, containers, or edge devices. Every host stays outbound-only and reports live status, load, and heartbeat latency.',
    href: '/docs/daemon',
    mock: daemons,
  },
  {
    id: 'approvals',
    label: 'Approvals',
    tag: 'Human-in-the-loop gates',
    blurb:
      'Pause an agent before any risky action and route the decision to Slack, the Web UI, or the TUI. Approve, deny, or edit the command — every choice is audited.',
    href: '/docs/hitl',
    mock: approvals,
  },
  {
    id: 'alerts',
    label: 'Alerts',
    tag: 'Budgets & anomalies',
    blurb:
      'Token-spike detection, budget burn-down, and hard cost caps. When a threshold trips, the agent pauses and you get notified before the bill does.',
    href: '/docs/agents',
    mock: alerts,
  },
  {
    id: 'schedules',
    label: 'Schedules',
    tag: 'Cron & webhooks',
    blurb:
      'Trigger agents on a cron expression or an inbound webhook. See the next fire time for every job and pause any of them with a single toggle.',
    href: '/docs/scheduling',
    mock: schedules,
  },
  {
    id: 'marketplace',
    label: 'Marketplace',
    tag: 'Install in one click',
    blurb:
      'A library of ready-made agents, skills, and plugins. Install a battle-tested pr-reviewer or incident-commander and customise from there.',
    href: '/docs/marketplace',
    mock: marketplace,
  },
  {
    id: 'prompt-editor',
    label: 'Prompt editor',
    tag: 'Author with variables',
    blurb:
      'A first-class editor for system prompts with template variables, model and temperature controls, live token counts, and a test-run button.',
    href: '/docs/agents',
    mock: promptEditor,
  },
  {
    id: 'versions',
    label: 'Versions',
    tag: 'Diff & rollback',
    blurb:
      'Every prompt and config change is versioned. Compare diffs, see who changed what, and roll back to any previous version instantly.',
    href: '/docs/agents',
    mock: versions,
  },
  {
    id: 'tools',
    label: 'Tools & MCPs',
    tag: 'Connect capabilities',
    blurb:
      'Wire agents to MCP servers and native tools — GitHub, Postgres, Slack, the filesystem, headless browsers — and scope each one with a flip of a switch.',
    href: '/docs/agents',
    mock: tools,
  },
  {
    id: 'filtering',
    label: 'Filtering',
    tag: 'Redaction & blockers',
    blurb:
      'On-device redaction strips secrets and PII before any byte is uploaded, while the ruleset engine blocks destructive commands outright.',
    href: '/docs/security',
    mock: filtering,
  },
  {
    id: 'packs',
    label: 'Capability packs',
    tag: 'Plugins, bundled',
    blurb:
      'Bundle related tools into versioned packs — devops, security, data — and enable or disable a whole capability set per agent.',
    href: '/docs/marketplace',
    mock: packs,
  },
  {
    id: 'memory',
    label: 'Memory editor',
    tag: 'Curate what agents know',
    blurb:
      'Read and edit the facts your agents carry between runs. Scope memories to an agent or the whole org, and tag them as rules, references, or feedback.',
    href: '/docs/memory',
    mock: memory,
  },
]

export function CapabilityMock({ id }: { id: string }) {
  const cap = capabilities.find((c) => c.id === id)
  return cap ? <div className="mk-standalone">{cap.mock}</div> : null
}
