import DocsSidebar from '@/components/DocsSidebar'

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="docs-layout">
      <DocsSidebar />
      <main className="docs-content">{children}</main>
    </div>
  )
}
