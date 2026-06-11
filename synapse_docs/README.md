# Synapse Documentation Site

The official documentation and landing page for **Synapse** — an autonomous agent framework designed for enterprises with security, observability, and human oversight as first-class citizens.

## About Synapse

Synapse enables you to deploy autonomous agents that run on your own infrastructure with military-grade security guarantees:

- **On-Device Execution**: Agents execute on your machines. Raw API keys, model outputs, and PII never leave the host.
- **E2E Encrypted Secrets**: Environment variables are X25519 sealed-box encrypted in your browser before transmission.
- **Human-in-the-Loop**: Configurable approval gates pause agents before risky actions.
- **Durable Runs**: SQLite WAL checkpoints survive machine loss with org recovery key encryption.
- **Real-Time Monitoring**: Live trace viewer, token + cost analytics, anomaly detection, and budget alerts.
- **Marketplace**: One-click install ready-made agent templates, skills, and plugins.

### Key Use Cases

- **DevOps**: Server-side automation for CVE patching, log monitoring, infrastructure scaling.
- **SRE**: Incident response automation with HITL approval for destructive actions.
- **Data Engineering**: Automated pipeline validation with anomaly detection and human gates.
- **Support**: Ticket triage with AI assistance and human approval before response.

## Project Structure

This is a **Next.js 15** documentation site using the App Router. It combines a modern landing page with embedded legacy documentation.

```
synapse_docs/
├── app/
│   ├── page.tsx                 # Landing page with features, security, FAQ
│   ├── layout.tsx               # Root layout with metadata
│   ├── globals.css              # Global styles + search modal styling
│   └── docs/                    # Documentation pages (App Router)
│       ├── agents/
│       ├── cli/
│       ├── concepts/
│       ├── daemon/
│       ├── faq/
│       ├── getting-started/
│       ├── hitl/
│       ├── marketplace/
│       ├── memory/
│       ├── orchestration/
│       ├── scheduling/
│       ├── security/
│       ├── use-cases/
│       └── web-ui/
├── components/
│   ├── SearchCommand.tsx         # CTRL+K search modal
│   ├── Nav.tsx                   # Navigation bar
│   ├── Footer.tsx                # Footer
│   └── fx/                       # Visual effects components
│       ├── Reveal.tsx
│       ├── Magnetic.tsx
│       ├── Counter.tsx
│       └── SynapseField.tsx
├── lib/
│   └── docs.ts                   # Documentation metadata & search
├── public/
│   └── docs_html/                # Legacy HTML documentation
└── package.json
```

## Features

### Search (CTRL+K)
Global keyboard shortcut to search documentation. Press `Ctrl+K` (or `Cmd+K` on Mac) anywhere on the site to open the search modal.

- Real-time search across all documentation pages
- Arrow key navigation (`↑↓`)
- Enter to navigate, Escape to close
- Responsive design (mobile-friendly)
- Accessible with ARIA labels

### Landing Page
Features a dynamic, visually rich landing page with:
- Hero section with product positioning
- Security highlights with architectural invariants
- Use case cards with real-world examples
- FAQ accordion
- Visual effects (smooth reveals, magnetic interactions, animated counters)
- Call-to-action for documentation and getting started

### Documentation
14 comprehensive documentation pages covering:
- **Getting Started**: Installation and quickstart
- **Concepts**: Core ideas and architecture
- **CLI**: Command-line interface reference
- **Daemon**: Daemon configuration and management
- **Agents**: Building and deploying agents
- **Orchestration**: Workflow composition
- **Scheduling**: Cron and scheduled tasks
- **Memory**: Agent memory systems
- **HITL**: Human-in-the-loop workflows
- **Web UI**: Dashboard and monitoring
- **Marketplace**: Extension ecosystem
- **Security**: Encryption, authentication, audit trails
- **Use Cases**: Industry-specific examples
- **FAQ**: Frequently asked questions

## Development

### Prerequisites
- Node.js 18+
- npm or pnpm

### Setup

```bash
# Install dependencies
npm install
# or
pnpm install

# Start development server
npm run dev
# or
pnpm dev
```

The site will be available at `http://localhost:3000`

### Scripts

```bash
npm run dev      # Start development server
npm run build    # Build for production
npm start        # Start production server
npm run lint     # Run TypeScript and ESLint checks
```

### Technologies

- **Next.js 15** — React framework with App Router
- **React 19** — UI framework
- **TypeScript** — Type safety
- **Three.js** — 3D graphics (SynapseField component)
- **GSAP** — Animation library
- **Lenis** — Smooth scrolling

## Architecture

### Security Design

Three core invariants protect user data:

1. **Broker Architecture**: The browser and daemon never talk directly—the cloud brokers every message.
2. **No Cloud Execution**: The cloud never executes agents or holds raw provider keys.
3. **Outbound-Only Connection**: The daemon connects outbound only—no inbound ports on your machine.

### On-Device Redaction

Regex + entropy scanning detects and redacts sensitive data before any byte leaves the host. Optional Presidio PII detection integration.

### Device Authentication

RFC 8628 device flow—`synapse login` prints an 8-char code for browser approval. No passwords typed in the terminal. Per-device tokens are revocable.

## Contributing

This is the official documentation site for Synapse. Changes should reflect the current product state.

When updating documentation:
1. Keep content concise and audience-appropriate
2. Update both the docs pages and landing page if features change
3. Test the search feature after adding new docs
4. Verify responsive design (mobile, tablet, desktop)
5. Check TypeScript compilation: `npm run lint`

## Recent Changes

- ✅ **Next.js 15 Upgrade** — Migrated to latest Next.js with App Router
- ✅ **CTRL+K Search** — Global keyboard shortcut for documentation search
- ✅ **Legacy Docs Integration** — Historic documentation embedded in new framework
- ✅ **Landing Page Redesign** — Modern visual effects and dynamic content

## License

See LICENSE file in the Synapse main repository.

## Support

- 📖 [Synapse Documentation](https://docs.synapse.sh)
- 🐛 [Issue Tracker](https://github.com/devmello/synapse/issues)
- 💬 [Community](https://community.synapse.sh)
