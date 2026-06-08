# Org structure: Members/RBAC + team hierarchy (live)

Merged to main via PR #26 (merge commit `925cea1`). Built on top of the Web UI →
Supabase migration ([[web_supabase_migration]]). Lives in Settings (`synapse_web/src/screens/Settings.tsx`).

**What the Web UI now models for "organization as a business":**
- **Org** = the tenant boundary (already existed; `organizations`, `memberships`, RLS by org_id).
- **Members & RBAC** (Part 1, wired to Supabase): `useMembers` reads `memberships ⋈ users`;
  role-change + remove are real mutations (owner-locked); 4-tier roles owner/admin/operator/viewer.
- **Invitations** (migration 0013 `org_invitations`): invite-by-email creates a pending row
  (browser can't resolve arbitrary email→user_id — RLS on `users` blocks enumeration, by design).
  Pending invites show as "invited" rows; remove revokes. Accept/link-on-signup is a backend TODO.
- **Team hierarchy** (Part 2, migration 0014 `teams` self-nesting via `parent_team_id` +
  `team_memberships`): Settings → **Teams** sub-tab renders the nested tree (Engineering →
  Platform/Support; Operations), create/delete team, add/remove member. Org-scoped RLS.
  NOTE: team membership is org-structure only — it does NOT yet scope agent/run data access
  (that stays org-level RLS). Team-level data isolation is a future change.

**Code:** `api/queries/members.ts` + `api/queries/teams.ts` (+ adapters), barrel
`api/queries.ts`, types `Member`/`Role`/`TeamNode`/`TeamMemberLite` in `src/types.ts`.
Migrations 0013 + 0014 applied to live project `gpxfylwhwdsswbgicgby`.

**Gotchas learned:**
- Mirroring a react-query array into local state via `useEffect([data])` caused an infinite
  render loop (Maximum update depth). Fix: derive the list directly from the query; do optimistic
  reconcile via mutation `onSettled` invalidate. Applied to MembersTab.
- Manually-inserted `auth.users` rows must set the token text columns (confirmation_token,
  recovery_token, email_change*, phone_change*, reauthentication_token) to '' or GoTrue login
  returns "Database error querying schema". seed.sql does this.
- Preview console buffer is NOT cleared by `window.location.reload()` — to confirm a fix,
  preview_stop + preview_start for a fresh console.

**Demo data on live:** org northwind has 4 members (avery owner / jin admin / mara operator /
theo admin — theo was viewer, bumped during a role-change test) + priya (invitable, no
membership) and the 4-team hierarchy. Logins all `synapse123`.
