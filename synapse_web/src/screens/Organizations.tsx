// Synapse Web UI — Organizations page: list, switch, and create orgs.
// Users manage all their organizations from here. Each org has its own members,
// billing, and settings. The personal workspace is always shown first.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageHead, SectionRow } from "../components/Common";
import { Button } from "../components/Primitives";
import { useOrgs, useCreateOrg } from "../api/queries";
import { useUI } from "../store/ui";
import type { OrgSummary } from "../types";

// ── OrgCard ───────────────────────────────────────────────────────────────────
interface OrgCardProps {
  org: OrgSummary;
  isActive: boolean;
  onSwitch: () => void;
  onSettings?: () => void;
}

function planPillClass(plan: string): string {
  const p = plan.toLowerCase();
  if (p === "team" || p === "business" || p === "enterprise") return "admin";
  if (p === "pro") return "operator";
  return "viewer";
}

function OrgCard({ org, isActive, onSwitch, onSettings }: OrgCardProps) {
  return (
    <div
      className="db-panel"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 16,
        marginBottom: 12,
        padding: "14px 18px",
      }}
    >
      {/* Initials avatar */}
      <span className="db-ws-avatar" style={{ width: 38, height: 38, borderRadius: 10, fontSize: 15, flexShrink: 0 }}>
        {org.initials}
      </span>

      {/* Name + plan */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)" }}>{org.name}</span>
          {org.isPersonal && (
            <span className="db-tag" style={{ fontSize: 10 }}>personal</span>
          )}
          {isActive && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                fontSize: 11,
                fontFamily: "var(--font-mono)",
                color: "var(--status-ok)",
                background: "var(--status-ok-bg)",
                padding: "2px 8px",
                borderRadius: 999,
              }}
            >
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--status-ok)", flexShrink: 0 }} />
              Active
            </span>
          )}
        </div>
        <div style={{ fontSize: 12, color: "var(--mute)", marginTop: 3, fontFamily: "var(--font-mono)" }}>
          {org.isPersonal
            ? `Your default workspace · ${org.plan} plan`
            : `${org.plan} plan`}
        </div>
      </div>

      {/* Plan pill */}
      <span className={"db-role-pill " + planPillClass(org.plan)} style={{ flexShrink: 0 }}>
        {org.plan}
      </span>

      {/* Actions */}
      <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
        {onSettings && (
          <Button variant="outline-light" icon="settings" onClick={onSettings}>
            Open settings
          </Button>
        )}
        <Button
          variant={isActive ? "ghost-dark" : "primary"}
          icon="chevrons-up-down"
          onClick={onSwitch}
          disabled={isActive}
        >
          {isActive ? "Active" : "Switch to"}
        </Button>
      </div>
    </div>
  );
}

// ── Organizations page ────────────────────────────────────────────────────────
export default function Organizations() {
  const navigate = useNavigate();
  const showToast = useUI((s) => s.showToast);
  const activeOrgId = useUI((s) => s.activeOrgId);
  const setActiveOrgId = useUI((s) => s.setActiveOrgId);

  const { data: orgs = [], isLoading } = useOrgs();
  const createMut = useCreateOrg();

  const [name, setName] = useState("");

  function switchOrg(org: OrgSummary | "personal") {
    if (org === "personal") {
      setActiveOrgId("personal");
      showToast({ text: "Switched to personal workspace" });
    } else {
      setActiveOrgId(org.id);
      showToast({ text: `Switched to ${org.name}` });
    }
  }

  function create() {
    const n = name.trim();
    if (!n) {
      showToast({ text: "Enter an organization name", variant: "warn" });
      return;
    }
    createMut.mutate(
      { name: n },
      {
        onSuccess: (newOrgId) => {
          showToast({ text: `Organization "${n}" created` });
          setName("");
          if (newOrgId) navigate(`/org/${String(newOrgId)}/settings`);
        },
        onError: (e) => showToast({ text: (e as Error).message, variant: "warn" }),
      },
    );
  }

  // Separate personal sentinel from real orgs
  const realOrgs = orgs.filter((o) => !o.isPersonal);

  return (
    <>
      <PageHead
        kicker="Account"
        title="Your"
        serif="organizations"
        sub="Manage your organizations. Each organization has its own members, billing, and settings."
      />

      <SectionRow title="Your workspaces" />

      {/* Personal workspace — always shown first */}
      <OrgCard
        org={{
          id: "personal",
          name: "Personal workspace",
          plan: "personal",
          initials: "P",
          isPersonal: true,
        }}
        isActive={activeOrgId === "personal"}
        onSwitch={() => switchOrg("personal")}
      />

      {/* Real org cards */}
      {realOrgs.map((org) => (
        <OrgCard
          key={org.id}
          org={org}
          isActive={activeOrgId === org.id}
          onSwitch={() => switchOrg(org)}
          onSettings={() => navigate(`/org/${org.id}/settings`)}
        />
      ))}

      {!isLoading && realOrgs.length === 0 && (
        <div className="db-mono db-muted" style={{ fontSize: 13, padding: "8px 0 16px" }}>
          No additional organizations yet.
        </div>
      )}

      <SectionRow title="Create an organization">
        <span className="db-mono db-muted">Premium feature</span>
      </SectionRow>

      <div className="db-panel" style={{ maxWidth: 520 }}>
        <span className="db-sublabel">Organization name</span>
        <input
          className="db-input"
          placeholder="e.g. Acme Corp"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") create(); }}
        />
        <div style={{ marginTop: 12 }}>
          <Button variant="primary" icon="plus" onClick={create} disabled={createMut.isPending}>
            {createMut.isPending ? "Creating…" : "Create organization"}
          </Button>
        </div>
        <p style={{ fontSize: 13, color: "var(--mute)", marginTop: 10, lineHeight: 1.5 }}>
          Organizations let you separate workspaces, billing, and team members.
          Additional organizations require a Team or Enterprise plan.
        </p>
      </div>
    </>
  );
}
