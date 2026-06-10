import fs from 'fs'
import path from 'path'

export default function Orchestration() {
  const filePath = path.join(process.cwd(), 'public', 'docs_html', 'docs', 'orchestration.html')
  const html = fs.readFileSync(filePath, 'utf8')
  return <article className="legacy-html" dangerouslySetInnerHTML={{ __html: html }} />
}
