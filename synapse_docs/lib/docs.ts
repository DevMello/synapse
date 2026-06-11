export interface DocItem {
  id: string
  title: string
  description: string
  path: string
  category?: string
}

export const docs: DocItem[] = [
  {
    id: 'getting-started',
    title: 'Getting Started',
    description: 'Install the Synapse daemon, connect it to the cloud, and run your first agent',
    path: '/docs/getting-started',
    category: 'Docs',
  },
  {
    id: 'concepts',
    title: 'Concepts',
    description: 'Learn the core concepts behind Synapse',
    path: '/docs/concepts',
    category: 'Docs',
  },
  {
    id: 'cli',
    title: 'CLI',
    description: 'Command-line interface reference for Synapse',
    path: '/docs/cli',
    category: 'Docs',
  },
  {
    id: 'daemon',
    title: 'Daemon',
    description: 'Understanding and configuring the Synapse daemon',
    path: '/docs/daemon',
    category: 'Docs',
  },
  {
    id: 'agents',
    title: 'Agents',
    description: 'Building and deploying intelligent agents with Synapse',
    path: '/docs/agents',
    category: 'Docs',
  },
  {
    id: 'orchestration',
    title: 'Orchestration',
    description: 'Orchestrating agents and workflows',
    path: '/docs/orchestration',
    category: 'Docs',
  },
  {
    id: 'scheduling',
    title: 'Scheduling',
    description: 'Schedule agents to run on specific intervals',
    path: '/docs/scheduling',
    category: 'Docs',
  },
  {
    id: 'memory',
    title: 'Memory',
    description: 'Agent memory and context persistence',
    path: '/docs/memory',
    category: 'Docs',
  },
  {
    id: 'hitl',
    title: 'Human-in-the-Loop',
    description: 'Implementing human-in-the-loop workflows',
    path: '/docs/hitl',
    category: 'Docs',
  },
  {
    id: 'security',
    title: 'Security',
    description: 'Security considerations and best practices',
    path: '/docs/security',
    category: 'Docs',
  },
  {
    id: 'web-ui',
    title: 'Web UI',
    description: 'Managing agents through the web interface',
    path: '/docs/web-ui',
    category: 'Docs',
  },
  {
    id: 'marketplace',
    title: 'Marketplace',
    description: 'Discover and integrate community agents',
    path: '/docs/marketplace',
    category: 'Docs',
  },
  {
    id: 'use-cases',
    title: 'Use Cases',
    description: 'Real-world examples and applications of Synapse',
    path: '/docs/use-cases',
    category: 'Docs',
  },
  {
    id: 'faq',
    title: 'FAQ',
    description: 'Frequently asked questions',
    path: '/docs/faq',
    category: 'Docs',
  },
]

export function searchDocs(query: string): DocItem[] {
  if (!query.trim()) return []

  const lowerQuery = query.toLowerCase()

  return docs.filter((doc) => {
    return (
      doc.title.toLowerCase().includes(lowerQuery) ||
      doc.description.toLowerCase().includes(lowerQuery) ||
      doc.id.toLowerCase().includes(lowerQuery)
    )
  })
}
