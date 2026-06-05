/** @type {import('tailwindcss').Config} */
// Tailwind is wired to the Synapse design tokens (defined as CSS variables in
// src/styles/colors_and_type.css). Screens primarily use the bespoke `.db-*`
// classes from src/styles/app.css; Tailwind utilities reference the same tokens
// so anything new stays on-system.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 0: "var(--ink-0)", 1: "var(--ink-1)", 2: "var(--ink-2)", DEFAULT: "var(--ink)" },
        bone: { 0: "var(--bone-0)", 1: "var(--bone-1)", DEFAULT: "var(--bone)" },
        paper: "var(--paper)",
        accent: {
          DEFAULT: "var(--accent)",
          soft: "var(--accent-soft)",
          deep: "var(--accent-deep)",
        },
        mute: "var(--mute)",
        "status-ok": "var(--status-ok)",
        "status-warn": "var(--status-warn)",
        "status-info": "var(--status-info)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        serif: ["Instrument Serif", "serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        xs: "6px", sm: "10px", md: "14px", lg: "22px", xl: "28px",
      },
    },
  },
  plugins: [],
};
