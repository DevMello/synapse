import fs from 'fs'
import path from 'path'

export default function DocsIndex() {
  const filePath = path.join(process.cwd(), 'public', 'docs_html', 'index.html')
  const html = fs.readFileSync(filePath, 'utf8')
  return <article className="legacy-html" dangerouslySetInnerHTML={{ __html: html }} />
}
