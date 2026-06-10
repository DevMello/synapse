import fs from 'fs'
import path from 'path'

export default function Agents() {
  const filePath = path.join(process.cwd(), 'public', 'docs_html', 'docs', 'agents.html')
  const html = fs.readFileSync(filePath, 'utf8')
  return <article className="legacy-html" dangerouslySetInnerHTML={{ __html: html }} />
}
