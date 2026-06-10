// Synapse Web UI — client UI state (Zustand). Cross-cutting interaction state that
// isn't server data: toasts, the command palette, the New Agent wizard, the Tweaks
// panel, and the live HITL approvals queue (which mutates as operators decide).
import { create } from "zustand";
import { approvals as seedApprovals } from "../data/mock";
import type { Approval } from "../types";

export interface ToastMsg {
  text: string;
  variant?: "ok" | "warn";
}

export interface ResolvedApproval {
  id: string;
  agent: string;
  action: string;
  decision: "approve" | "deny";
  reason?: string;
}

interface UIState {
  // command palette
  paletteOpen: boolean;
  setPalette: (open: boolean) => void;
  togglePalette: () => void;

  // new-agent wizard
  wizardOpen: boolean;
  setWizard: (open: boolean) => void;

  // tweaks panel (Density / Accent mood / Liveness)
  tweaksOpen: boolean;
  setTweaks: (open: boolean) => void;

  // toast
  toast: ToastMsg | null;
  showToast: (msg: ToastMsg | string) => void;
  clearToast: () => void;

  // live HITL approvals queue
  approvals: Approval[];
  resolved: ResolvedApproval[];
  resolveApproval: (id: string, decision: "approve" | "deny", reason?: string) => void;
  resetApprovals: () => void;

  // active org context — "personal" or an org UUID
  activeOrgId: string;
  setActiveOrgId: (id: string) => void;
}

let toastTimer: ReturnType<typeof setTimeout> | null = null;

export const useUI = create<UIState>((set, get) => ({
  paletteOpen: false,
  setPalette: (open) => set({ paletteOpen: open }),
  togglePalette: () => set((s) => ({ paletteOpen: !s.paletteOpen })),

  wizardOpen: false,
  setWizard: (open) => set({ wizardOpen: open }),

  tweaksOpen: false,
  setTweaks: (open) => set({ tweaksOpen: open }),

  toast: null,
  showToast: (msg) => {
    const next: ToastMsg = typeof msg === "string" ? { text: msg } : msg;
    set({ toast: next });
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => set({ toast: null }), 2800);
  },
  clearToast: () => set({ toast: null }),

  approvals: seedApprovals,
  resolved: [],
  resolveApproval: (id, decision, reason) => {
    const card = get().approvals.find((a) => a.id === id);
    if (!card) return;
    set((s) => ({
      approvals: s.approvals.filter((a) => a.id !== id),
      resolved: [
        { id, agent: card.agent, action: card.action, decision, reason },
        ...s.resolved,
      ],
    }));
  },
  resetApprovals: () => set({ approvals: seedApprovals, resolved: [] }),

  activeOrgId: "personal",
  setActiveOrgId: (id) => set({ activeOrgId: id }),
}));
