import fs from 'fs'
import path from 'path'

export default function Scheduling() {
  const filePath = path.join(process.cwd(), 'public', 'docs_html', 'docs', 'scheduling.html')
  const html = fs.readFileSync(filePath, 'utf8')
  return <article className="legacy-html" dangerouslySetInnerHTML={{ __html: html }} />
}
