import fs from 'fs'
import path from 'path'

export default function Marketplace() {
  const filePath = path.join(process.cwd(), 'synapse_docs', 'public', 'docs_html', 'docs', 'marketplace.html')
  const html = fs.readFileSync(filePath, 'utf8')
  return <article className="legacy-html" dangerouslySetInnerHTML={{ __html: html }} />
}
