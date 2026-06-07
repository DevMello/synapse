// Synapse Web UI — Settings & RBAC (#21).
// Org profile, members & roles (owner/admin/operator/viewer), billing/usage, and
// API tokens. Roles gate who can deploy, edit, approve HITL, and view secrets.
// Ported from the design prototype's `Settings` (design-reference/app/Views.jsx)
// and deepened with full Profile / Members / Billing / Tokens sub-tabs.
import { useEffect, useMemo, useState } from "react";
import { PageHead, Segmented, ConfirmDialog, MetricCard, SectionRow } from "../components/Common";
import { Button, Icon } from "../components/Primitives";
import {
  useOrg, useMembers, useInvitations, useInviteMember, useUpdateMemberRole, useRemoveMember, useRevokeInvitation,
} from "../api/queries";
import { useUI } from "../store/ui";
import type { Member, Role } from "../types";

type SubTab = "profile" | "members" | "billing" | "tokens";

// What each role is permitted to do — surfaced as RBAC copy so operators
// understand exactly what an invite grants.
const ROLE_RIGHTS: Record<Role, string> = {
  owner: "Full control · billing, members, deploy, approve, view secrets",
  admin: "Deploy & edit agents, manage members, approve HITL, view secrets",
  operator: "Deploy & edit agents, approve HITL gates · no secret values",
  viewer: "Read-only · runs, traces, and alerts · no deploy or secrets",
};

const ROLE_ORDER: Role[] = ["owner", "admin", "operator", "viewer"];

export default function Settings() {
  const showToast = useUI((s) => s.showToast);
  const { data: org } = useOrg();
  const [sub, setSub] = useState<SubTab>("profile");

  return (
    <>
      <PageHead
        kicker="Settings"
        title="Your"
        serif="workspace"
        sub="Org profile, members and roles, billing, and API tokens. Roles gate who can deploy, edit, approve HITL, and view secrets-adjacent data."
        actions={
          <span className="db-mono db-muted" style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
            <Icon name="shield-check" size={14} /> {org?.name} · {org?.plan}
          </span>
        }
      />

      <div className="db-subtabs">
        {([
          ["profile", "Org profile"],
          ["members", "Members & RBAC"],
          ["billing", "Billing & usage"],
          ["tokens", "API tokens"],
        ] as [SubTab, string][]).map(([id, label]) => (
          <button
            key={id}
            className={"db-subtab" + (sub === id ? " active" : "")}
            onClick={() => setSub(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {sub === "profile" && <ProfileTab />}
      {sub === "members" && <MembersTab showToast={showToast} />}
      {sub === "billing" && <BillingTab />}
      {sub === "tokens" && <TokensTab showToast={showToast} />}
    </>
  );
}

// ── Org profile ────────────────────────────────────────────────────────────
function ProfileTab() {
  const { data: org } = useOrg();
  const [name, setName] = useState(org?.name ?? "");
  const [region, setRegion] = useState("us-east");
  const showToast = useUI((s) => s.showToast);
  const [saved, setSaved] = useState(true);

  // Adopt the org name once it loads (the query resolves after first render).
  useEffect(() => {
    if (org?.name) setName(org.name);
  }, [org?.name]);

  function save() {
    setSaved(true);
    showToast({ text: "Organization profile saved" });
  }

  return (
    <div className="db-panel" style={{ maxWidth: 560 }}>
      <div className="db-panel-head">
        <h3 className="db-panel-title">Organization</h3>
        <span className="db-mono db-muted" style={{ fontSize: 11 }}>org · {org?.name}</span>
      </div>

      <span className="db-sublabel">Display name</span>
      <input
        className="db-input"
        value={name}
        onChange={(e) => { setName(e.target.value); setSaved(false); }}
      />

      <span className="db-sublabel">Region</span>
      <input
        className="db-input"
        value={region}
        onChange={(e) => { setRegion(e.target.value); setSaved(false); }}
      />

      <div className="db-ov-facts" style={{ marginTop: 8 }}>
        <div className="db-ov-fact">
          <span className="db-ov-fact-l">Org owner</span>
          <span className="db-mono">{org?.operator}</span>
        </div>
        <div className="db-ov-fact">
          <span className="db-ov-fact-l">Plan</span>
          <span className="db-mono">{org?.plan}</span>
        </div>
        <div className="db-ov-fact">
          <span className="db-ov-fact-l">Created</span>
          <span className="db-mono">2025-11-02</span>
        </div>
        <div className="db-ov-fact">
          <span className="db-ov-fact-l">Workspace ID</span>
          <span className="db-mono db-muted">org_8f3a91c2</span>
        </div>
      </div>

      <div style={{ marginTop: 18 }}>
        <Button variant="primary" icon="save" onClick={save} disabled={saved}>
          {saved ? "Saved" : "Save changes"}
        </Button>
      </div>
    </div>
  );
}

// ── Members & RBAC ───────────────────────────────────────────────────────────
function MembersTab({ showToast }: { showToast: (m: { text: string; variant?: "ok" | "warn" }) => void }) {
  // The list is derived directly from the queries (no mirrored local state) — the
  // mutations reconcile via onSettled invalidation. Defaulting to [] here is safe
  // because it's only read during render, never as an effect dependency.
  const { data: members = [] } = useMembers();
  const { data: invites = [] } = useInvitations();
  const inviteMut = useInviteMember();
  const roleMut = useUpdateMemberRole();
  const removeMut = useRemoveMember();
  const revokeMut = useRevokeInvitation();
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<Role>("operator");

  // Real members first, then pending invitations (shown as "invited" rows).
  const rows: Member[] = [...members, ...invites];

  function invite() {
    const email = inviteEmail.trim().toLowerCase();
    if (!email || !email.includes("@")) {
      showToast({ text: "Enter a valid email to invite", variant: "warn" });
      return;
    }
    if (rows.some((m) => m.email === email)) {
      showToast({ text: "That person is already a member or invited", variant: "warn" });
      return;
    }
    setInviteEmail("");
    inviteMut.mutate(
      { email, role: inviteRole },
      {
        onSuccess: () => showToast({ text: `Invited ${email} as ${inviteRole}` }),
        onError: (e) => showToast({ text: (e as Error).message, variant: "warn" }),
      },
    );
  }

  function cycleRole(m: Member) {
    if (m.role === "owner" || m.pending) return; // owner fixed; pending invites not editable here
    const cyclable: Role[] = ["admin", "operator", "viewer"];
    const next = cyclable[(cyclable.indexOf(m.role) + 1) % cyclable.length];
    roleMut.mutate(
      { userId: m.userId, role: next },
      {
        onSuccess: () => showToast({ text: `${m.name} is now ${next}` }),
        onError: (e) => showToast({ text: (e as Error).message, variant: "warn" }),
      },
    );
  }

  function remove(m: Member) {
    if (m.pending) {
      revokeMut.mutate(
        { inviteId: m.userId },
        {
          onSuccess: () => showToast({ text: `Invite to ${m.email} revoked`, variant: "warn" }),
          onError: (e) => showToast({ text: (e as Error).message, variant: "warn" }),
        },
      );
      return;
    }
    removeMut.mutate(
      { userId: m.userId },
      {
        onSuccess: () => showToast({ text: "Member removed from workspace", variant: "warn" }),
        onError: (e) => showToast({ text: (e as Error).message, variant: "warn" }),
      },
    );
  }

  return (
    <>
      <div className="db-toolbar">
        <span className="db-mono db-muted">
          {members.length} members{invites && invites.length > 0 ? ` · ${invites.length} invited` : ""}
        </span>
        <div className="db-toolbar-r">
          <input
            className="db-input"
            style={{ marginBottom: 0, width: 240 }}
            placeholder="invite by email…"
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") invite(); }}
          />
          <Segmented<Role>
            value={inviteRole}
            onChange={setInviteRole}
            options={[
              { value: "admin", label: "Admin" },
              { value: "operator", label: "Operator" },
              { value: "viewer", label: "Viewer" },
            ]}
          />
          <Button variant="primary" icon="plus" onClick={invite}>Invite</Button>
        </div>
      </div>

      <div className="db-table-wrap">
        <table className="db-table">
          <thead>
            <tr><th>Member</th><th>Email</th><th>Role</th><th>Joined</th><th></th></tr>
          </thead>
          <tbody>
            {rows.map((m) => {
              const locked = m.role === "owner" || m.pending;
              return (
                <tr key={m.userId} style={m.pending ? { opacity: 0.7 } : undefined}>
                  <td className="db-cell-primary">
                    <span className="db-member"><span className="db-member-av">{m.init}</span>{m.name}</span>
                  </td>
                  <td className="db-mono db-muted">{m.email}</td>
                  <td>
                    <button
                      className="db-role-pill-btn"
                      style={{ border: "none", background: "none", padding: 0, cursor: locked ? "default" : "pointer" }}
                      onClick={() => cycleRole(m)}
                      title={m.role === "owner" ? "Owner role can't be changed here" : m.pending ? "Pending invite" : "Click to change role"}
                    >
                      <span className={"db-role-pill " + m.role}>{m.role}</span>
                    </button>
                  </td>
                  <td className="db-mono db-muted">{m.active}</td>
                  <td>
                    {m.role === "owner" ? (
                      <span className="db-icon-mini" style={{ opacity: 0.3, cursor: "default" }}><Icon name="lock" size={14} /></span>
                    ) : (
                      <button className="db-icon-mini danger" onClick={() => remove(m)} title={m.pending ? "Revoke invite" : "Remove member"}>
                        <Icon name="trash" size={15} />
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <SectionRow title="What each role can do" />
      <div className="db-panel">
        <div className="db-ov-facts">
          {ROLE_ORDER.map((r) => (
            <div key={r} className="db-ov-fact">
              <span className="db-ov-fact-l" style={{ minWidth: 90 }}>
                <span className={"db-role-pill " + r}>{r}</span>
              </span>
              <span className="db-mono db-muted" style={{ fontSize: 12, textAlign: "right" }}>{ROLE_RIGHTS[r]}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

// ── Billing & usage ──────────────────────────────────────────────────────────
function BillingTab() {
  const invoices = [
    { period: "May 2025", amount: "$418.20", status: "paid" },
    { period: "Apr 2025", amount: "$376.94", status: "paid" },
    { period: "Mar 2025", amount: "$311.08", status: "paid" },
  ];
  return (
    <>
      <div className="db-metric-grid db-metric-grid-3">
        <MetricCard label="Plan" n="Team" sub="$0.00 platform fee · usage billed" />
        <MetricCard label="Spend this month" n="$418" delta="across 6 agents · 5 daemons" dir="up" />
        <MetricCard label="Seats" n="5" unit="/ 10" sub="3 operators · 1 admin · 1 owner" />
      </div>

      <SectionRow title="Invoices" />
      <div className="db-table-wrap">
        <table className="db-table">
          <thead>
            <tr><th>Period</th><th>Amount</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {invoices.map((inv) => (
              <tr key={inv.period}>
                <td className="db-cell-primary">{inv.period}</td>
                <td className="db-mono">{inv.amount}</td>
                <td><span className="db-role-pill operator">{inv.status}</span></td>
                <td>
                  <a className="db-link" href="#" onClick={(e) => e.preventDefault()}>
                    <Icon name="download" size={13} /> PDF
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ── API tokens ───────────────────────────────────────────────────────────────
interface Token {
  id: string;
  name: string;
  prefix: string;
  scope: string;
  created: string;
  lastUsed: string;
}

const SEED_TOKENS: Token[] = [
  { id: "t1", name: "ci-deploy", prefix: "syn_live_9f2a", scope: "deploy", created: "2025-11-08", lastUsed: "2 min ago" },
  { id: "t2", name: "fleet-readonly", prefix: "syn_live_4c7b", scope: "read", created: "2025-12-01", lastUsed: "1 h ago" },
  { id: "t3", name: "mara-laptop", prefix: "syn_live_a13e", scope: "deploy", created: "2026-01-20", lastUsed: "never" },
];

function randomPrefix(): string {
  const hex = Math.random().toString(16).slice(2, 6);
  return `syn_live_${hex}`;
}

function TokensTab({ showToast }: { showToast: (m: { text: string; variant?: "ok" | "warn" }) => void }) {
  const [tokens, setTokens] = useState<Token[]>(SEED_TOKENS);
  const [newName, setNewName] = useState("");
  const [newScope, setNewScope] = useState<"deploy" | "read">("read");
  const [revoking, setRevoking] = useState<Token | null>(null);

  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);

  function create() {
    const name = newName.trim();
    if (!name) {
      showToast({ text: "Name the token before creating it", variant: "warn" });
      return;
    }
    const prefix = randomPrefix();
    setTokens((ts) => [
      { id: "t" + Date.now(), name, prefix, scope: newScope, created: today, lastUsed: "never" },
      ...ts,
    ]);
    setNewName("");
    showToast({ text: `Token created · ${prefix}… (copy it now, shown once)` });
  }

  function confirmRevoke() {
    if (!revoking) return;
    setTokens((ts) => ts.filter((t) => t.id !== revoking.id));
    showToast({ text: `Token ${revoking.name} revoked`, variant: "warn" });
    setRevoking(null);
  }

  function copy(prefix: string) {
    showToast({ text: "Token prefix copied to clipboard" });
    void navigator.clipboard?.writeText(prefix).catch(() => undefined);
  }

  return (
    <>
      <div className="db-toolbar">
        <span className="db-mono db-muted">
          {tokens.length} active token{tokens.length === 1 ? "" : "s"} · scope-gated by role
        </span>
        <div className="db-toolbar-r">
          <input
            className="db-input"
            style={{ marginBottom: 0, width: 200 }}
            placeholder="token name…"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") create(); }}
          />
          <Segmented<"deploy" | "read">
            value={newScope}
            onChange={setNewScope}
            options={[
              { value: "read", label: "Read" },
              { value: "deploy", label: "Deploy" },
            ]}
          />
          <Button variant="primary" icon="key" onClick={create}>Create token</Button>
        </div>
      </div>

      {tokens.length === 0 ? (
        <div className="db-empty">
          <span className="db-empty-icon"><Icon name="key" size={22} /></span>
          <div className="db-empty-caption">
            No API tokens · run <span className="db-empty-cmd">synapse token create</span> to mint one
          </div>
        </div>
      ) : (
        <div className="db-table-wrap">
          <table className="db-table">
            <thead>
              <tr><th>Name</th><th>Token</th><th>Scope</th><th>Created</th><th>Last used</th><th></th></tr>
            </thead>
            <tbody>
              {tokens.map((t) => (
                <tr key={t.id}>
                  <td className="db-cell-primary">{t.name}</td>
                  <td className="db-mono db-muted">
                    <button
                      className="db-icon-mini"
                      style={{ width: "auto", padding: "0 8px", gap: 6, display: "inline-flex" }}
                      onClick={() => copy(t.prefix)}
                      title="Copy token prefix"
                    >
                      {t.prefix}…<Icon name="copy" size={13} />
                    </button>
                  </td>
                  <td><span className={"db-role-pill " + (t.scope === "deploy" ? "admin" : "viewer")}>{t.scope}</span></td>
                  <td className="db-mono db-muted">{t.created}</td>
                  <td className="db-mono db-muted">{t.lastUsed}</td>
                  <td>
                    <button className="db-icon-mini danger" onClick={() => setRevoking(t)} title="Revoke token">
                      <Icon name="trash" size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={revoking != null}
        onClose={() => setRevoking(null)}
        onConfirm={confirmRevoke}
        title="Revoke this token?"
        body={
          <>
            <b>{revoking?.name}</b> ({revoking?.prefix}…) will stop working immediately.
            Any daemon or CI job using it will fail authentication. This can't be undone.
          </>
        }
        confirmLabel="Revoke token"
        danger
      />
    </>
  );
}
