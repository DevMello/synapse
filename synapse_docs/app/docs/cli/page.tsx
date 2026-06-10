import fs from 'fs'
import path from 'path'

export default function CLIRef() {
  const filePath = path.join(process.cwd(), 'synapse_docs', 'public', 'docs_html', 'docs', 'cli.html')
  const html = fs.readFileSync(filePath, 'utf8')
  return <article className="legacy-html" dangerouslySetInnerHTML={{ __html: html }} />
}
