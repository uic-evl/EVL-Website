// Checks the built Impact page in _site: every row with one value per year, the collected rows filled in when
// _data/impact_metrics.json exists, and Impact in the top menu. Prints the table.
//
//   node _impact/check.mjs

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const SITE = path.join(ROOT, '_site')
const ROWS = ['publications', 'citations', 'phd-graduates', 'funded-projects', 'new-funding', 'repositories', 'stars', 'downloads']
const COLLECTED = ['citations', 'repositories', 'stars', 'downloads']

const problems = []
const read = (file) => fs.readFileSync(path.join(SITE, file), 'utf8')

const impact = JSON.parse(read('impact/impact.json'))
const collected = fs.existsSync(path.join(ROOT, '_data/impact_metrics.json'))
for (const id of ROWS) {
  const row = impact.rows.find((r) => r.id === id)
  if (!row) {
    problems.push(`impact.json has no ${id} row`)
    continue
  }
  if (row.values.length !== impact.years.length) problems.push(`${id} has ${row.values.length} values for ${impact.years.length} years`)
  if (!COLLECTED.includes(id) || collected) {
    if (row.values.every((v) => v === null)) problems.push(`${id} is "Not available" in every year`)
  }
}
if (!fs.existsSync(path.join(SITE, 'impact/index.html'))) problems.push('_site/impact/index.html is missing')
if (!fs.existsSync(path.join(SITE, 'impact/evl-impact.csv'))) problems.push('_site/impact/evl-impact.csv is missing')
if (!/href="\/impact\/"/.test(read('index.html'))) problems.push('the home page menu has no link to /impact/')

const cell = (v) => String(v ?? 'n/a').padStart(11)
console.log(`${'row'.padEnd(18)}${impact.years.map((y) => cell(y.label)).join('')}`)
for (const row of impact.rows) console.log(`${row.id.padEnd(18)}${row.values.map(cell).join('')}`)

if (problems.length) {
  for (const p of problems) console.log(`::error::${p}`)
  process.exit(1)
}
console.log(`\nThe Impact page is complete (updated ${impact.updated ?? 'never'}).`)
