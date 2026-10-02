// Collects the Impact page's numbers that live outside this repository and writes them to
// _data/impact_metrics.json, which the site build reads. The impact workflow runs it and commits the file.
//
//   public repositories, with the day each was created   GitHub REST API, for the organizations the Repositories page lists
//   GitHub stars, by year                                GitHub GraphQL API; star days need a token that can push to the repository
//   PyPI downloads, by year                              ClickHouse's public PyPI dataset (sql-clickhouse.clickhouse.com)
//   npm downloads, by year                               npm's download counts API (api.npmjs.org)
//   citations of each bibliography entry, by year        OpenAlex (api.openalex.org)
//
//   GITHUB_TOKEN=<token> node _impact/collect.mjs
//
// What to collect comes from _data/repositories.yml, _data/impact.yml and the bibliography the Publications page
// renders. The helpers come from urbantk.org's scripts/impact/collect.mjs. Every request is tried three times; a
// source that still fails stops the script and leaves the previous file in place.

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse } from '@retorquere/bibtex-parser'
import yaml from 'js-yaml'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const OUT = path.join(ROOT, '_data/impact_metrics.json')
const CLICKHOUSE = 'https://sql-clickhouse.clickhouse.com/'
const OPENALEX = 'https://api.openalex.org'
const AGENT = 'www.evl.uic.edu impact page'
const TRIES = 3
// npm answers HTTP 429 after about 40 quick requests.
const NPM_PAUSE_MS = 1500
// OpenAlex charges $0.001 per title search out of a $0.10 daily allowance (batches cost $0.0001), so each run
// searches at most this many titles and leaves the rest for the next run.
const TITLE_SEARCHES = 60
const OPENALEX_RESERVE_USD = 0.02
// A title OpenAlex did not find is searched again after this many days.
const RECHECK_DAYS = 180
// Entry types OpenAlex rarely holds; they are looked up only by DOI or arXiv id.
const NO_TITLE_SEARCH = new Set(['misc', 'unpublished', 'phdthesis', 'mastersthesis'])

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function tried(what, fn) {
  for (let attempt = 1; ; attempt++) {
    try {
      return await fn()
    } catch (error) {
      if (attempt === TRIES || error.permanent) throw new Error(`${what}: ${error.message}`)
      await sleep(2000 * attempt)
    }
  }
}

async function get(url, headers = {}, { missingOk = false } = {}) {
  const res = await fetch(url, { headers: { 'User-Agent': AGENT, ...headers } })
  if (missingOk && res.status === 404) return null
  if (!res.ok) {
    const reply = (await res.text().catch(() => '')).slice(0, 200)
    const error = new Error(`HTTP ${res.status} for ${url}${reply ? `: ${reply}` : ''}`)
    // Rate limits and server errors can pass; any other client error will not.
    error.permanent = res.status < 500 && res.status !== 429 && res.status !== 403
    throw error
  }
  return res
}

function github(route) {
  const headers = { Accept: 'application/vnd.github+json', Authorization: `Bearer ${process.env.GITHUB_TOKEN}` }
  return tried(`GitHub ${route}`, () => get(`https://api.github.com/${route}`, headers))
}

function isoDay(date) {
  return date.toISOString().slice(0, 10)
}

function addDays(day, n) {
  const d = new Date(`${day}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return isoDay(d)
}

// Counts per year of a list of days.
function byYear(days) {
  const years = {}
  for (const day of days) years[day.slice(0, 4)] = (years[day.slice(0, 4)] ?? 0) + 1
  return years
}

// The public repositories of an organization, as the Repositories page lists them: all of them, or only the
// ones its `github_organization_repos` entry names.
async function orgRepos(org, only) {
  const list = []
  for (let page = 1; ; page++) {
    const repos = await (await github(`orgs/${org}/repos?type=public&per_page=100&page=${page}`)).json()
    list.push(...repos)
    if (repos.length < 100) break
  }
  return list
    .filter((repo) => !only || only.includes(repo.name))
    .map((repo) => ({ repo: repo.full_name, org, created: repo.created_at.slice(0, 10), fork: repo.fork, stars: repo.stargazers_count }))
}

// Why GitHub refused a stargazer list, per organization, for the run log.
const starsRefusals = {}

// The same list from the REST API, which some tokens GraphQL refuses may read. `expected` is the count GraphQL
// reported, if any: an empty REST list then means the list is hidden, not that there are no stars.
async function starsRest(repo, token, expected = 0) {
  const headers = { 'User-Agent': AGENT, Accept: 'application/vnd.github.star+json', Authorization: `Bearer ${token}` }
  const days = []
  let url = `https://api.github.com/repos/${repo}/stargazers?per_page=100`
  while (url) {
    const res = await tried(`stars of ${repo}`, async () => {
      const r = await fetch(url, { headers })
      if (r.status >= 500 || r.status === 429) throw new Error(`HTTP ${r.status} for ${url}`)
      return r
    })
    if (!res.ok) {
      const message = ((await res.json().catch(() => ({}))).message ?? '').slice(0, 120)
      starsRefusals[repo.split('/')[0]] ??= `REST: HTTP ${res.status} ${message}`
      return null
    }
    for (const star of await res.json()) days.push(star.starred_at.slice(0, 10))
    url = /<([^>]+)>;\s*rel="next"/.exec(res.headers.get('link') ?? '')?.[1] ?? null
  }
  if (expected > 0 && days.length === 0) {
    starsRefusals[repo.split('/')[0]] ??= 'GraphQL and REST show the count but list no stars'
    return null
  }
  return days
}

// The day of each star, through GitHub's GraphQL API, or null when GitHub does not list them to this token.
// GitHub lists stargazers only to tokens that can push to the repository.
async function stars(repo) {
  const token = process.env.STARS_TOKEN || process.env.GITHUB_TOKEN
  const [owner, name] = repo.split('/')
  const query = `query($owner: String!, $name: String!, $after: String) {
    repository(owner: $owner, name: $name) {
      stargazerCount
      stargazers(first: 100, after: $after, orderBy: { field: STARRED_AT, direction: ASC }) {
        pageInfo { hasNextPage endCursor }
        edges { starredAt }
      }
    }
  }`
  const days = []
  let after = null
  do {
    const body = await tried(`stars of ${repo}`, async () => {
      const res = await fetch('https://api.github.com/graphql', {
        method: 'POST',
        headers: { 'User-Agent': AGENT, Authorization: `Bearer ${token}` },
        body: JSON.stringify({ query, variables: { owner, name, after } }),
      })
      const json = await res.json().catch(() => ({}))
      const refused = json.errors?.find((e) => e.type === 'FORBIDDEN')
      if (refused) {
        starsRefusals[owner] ??= refused.message
        return null
      }
      if (!res.ok || json.errors) {
        const error = new Error(`HTTP ${res.status}: ${JSON.stringify(json.errors ?? json).slice(0, 300)}`)
        error.permanent = res.status < 500 && res.status !== 429
        throw error
      }
      return json
    })
    if (!body) return starsRest(repo, token)
    const { stargazerCount, stargazers: page } = body.data.repository
    // Some tokens see the count but an empty list; the REST list is the second chance.
    if (!after && stargazerCount > 0 && page.edges.length === 0) return starsRest(repo, token, stargazerCount)
    days.push(...page.edges.map((edge) => edge.starredAt.slice(0, 10)))
    after = page.pageInfo.hasNextPage ? page.pageInfo.endCursor : null
  } while (after)
  return days
}

// The last day ClickHouse's PyPI dataset holds. A package without downloads that day still has data for it.
async function pypiThrough() {
  const query = 'SELECT toString(max(date)) FROM pypi.pypi_downloads_per_day FORMAT JSONCompact'
  const res = await tried('PyPI dataset', () => get(`${CLICKHOUSE}?${new URLSearchParams({ user: 'demo', query })}`))
  return (await res.json()).data[0][0]
}

// ClickHouse returns no rows for a name PyPI does not have, so the name is checked on PyPI first.
async function pypi(pkg, start, through) {
  const exists = await tried(`PyPI package ${pkg}`, () => get(`https://pypi.org/pypi/${encodeURIComponent(pkg)}/json`, {}, { missingOk: true }))
  if (!exists) throw new Error(`PyPI has no package ${pkg}, which _data/impact.yml lists`)
  const query =
    'SELECT toString(toYear(date)) AS year, sum(count) AS n FROM pypi.pypi_downloads_per_day ' +
    'WHERE project = {p:String} AND date >= {s:Date} AND date <= {t:Date} GROUP BY year ORDER BY year FORMAT JSONCompact'
  const url = `${CLICKHOUSE}?${new URLSearchParams({ user: 'demo', query, param_p: pkg, param_s: start, param_t: through })}`
  const res = await tried(`PyPI downloads of ${pkg}`, () => get(url))
  const years = {}
  for (const [year, n] of (await res.json()).data) if (Number(n)) years[year] = Number(n)
  return years
}

// The packages an npm organization owns, scoped or not.
async function npmOwned(org) {
  const res = await tried(`npm packages of ${org}`, () => get(`https://registry.npmjs.org/-/org/${org}/package`))
  return Object.keys(await res.json()).sort()
}

// `*` in a name matches any run of characters, among the packages the organization owns.
function npmNames(names, owned) {
  const escape = (part) => part.replace(/[.+?^${}()|[\]\\]/g, '\\$&')
  const glob = (name) => new RegExp(`^${name.split('*').map(escape).join('.*')}$`)
  return names.flatMap((name) => (name.includes('*') ? owned.filter((pkg) => glob(name).test(pkg)) : [name]))
}

// A package's first day and the GitHub repository its registry entry names, if any.
async function npmPackage(pkg) {
  const res = await tried(`npm package ${pkg}`, () => get(`https://registry.npmjs.org/${pkg.replace('/', '%2F')}`, {}, { missingOk: true }))
  if (!res) throw new Error(`npm has no package ${pkg}, which _data/impact.yml lists`)
  const doc = await res.json()
  const url = typeof doc.repository === 'string' ? doc.repository : doc.repository?.url ?? doc.versions?.[doc['dist-tags']?.latest]?.repository?.url
  const repo = /github\.com[/:]([^/]+\/[^/#]+?)(?:\.git)?(?:[/#]|$)/i.exec(url ?? '')?.[1]?.toLowerCase() ?? null
  return { created: doc.time.created.slice(0, 10), repo }
}

// One request per calendar year; npm answers at most 18 months per request.
async function npm(pkg, from, through) {
  const years = {}
  let last = null
  for (let year = Number(from.slice(0, 4)); year <= Number(through.slice(0, 4)); year++) {
    const a = `${year}-01-01` < from ? from : `${year}-01-01`
    const b = `${year}-12-31` > through ? through : `${year}-12-31`
    await sleep(NPM_PAUSE_MS)
    const res = await tried(`npm downloads of ${pkg}`, () => get(`https://api.npmjs.org/downloads/range/${a}:${b}/${pkg}`))
    for (const { day, downloads } of (await res.json()).downloads ?? []) {
      if (!downloads) continue
      years[year] = (years[year] ?? 0) + downloads
      if (!last || day > last) last = day
    }
  }
  return { years, last }
}

// LaTeX accents, commands and braces removed, for comparing titles.
function plain(text) {
  return String(text ?? '')
    .replace(/\\[a-zA-Z]+\s*/g, '')
    .replace(/\\./g, '')
    .replace(/[{}]/g, '')
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

function doiOf(fields) {
  const raw = [fields.doi, fields.url].map((v) => (typeof v === 'string' ? v.trim() : '')).find((v) => /10\.\d{4,9}\//.test(v))
  return raw ? raw.slice(raw.search(/10\.\d{4,9}\//)).toLowerCase() : null
}

function arxivOf(fields) {
  const prefix = String(fields.archiveprefix ?? fields.eprinttype ?? '').toLowerCase()
  const candidates = [fields.arxiv, prefix === 'arxiv' ? fields.eprint : null, fields.url].map((v) => (typeof v === 'string' ? v : ''))
  for (const value of candidates) {
    const m = /(?:arxiv\.org\/(?:abs|pdf)\/|^|\s|arxiv:)(\d{4}\.\d{4,5})(?:v\d+)?/i.exec(value.trim())
    if (m) return m[1]
  }
  return null
}

// The bibliography the Publications page renders, as `scholar.source` and `scholar.bibliography` name it.
function bibliography() {
  const scholar = yaml.load(fs.readFileSync(path.join(ROOT, '_config.yml'), 'utf8')).scholar
  const file = path.join(ROOT, scholar.source.replace(/^\/+/, ''), scholar.bibliography)
  const library = parse(fs.readFileSync(file, 'utf8'), {
    sentenceCase: false,
    caseProtection: false,
    verbatimFields: ['url', 'doi', 'eprint', 'arxiv', /^file$/],
  })
  return library.entries.map(({ key, type, fields }) => ({
    key,
    type: type.toLowerCase(),
    year: Number.parseInt(fields.year, 10) || null,
    title: typeof fields.title === 'string' ? fields.title : '',
    doi: doiOf(fields),
    arxiv: arxivOf(fields),
  }))
}

// OpenAlex, with the allowance left today read from its headers.
const openalexBudget = { usd: Infinity }
async function openalex(route, params) {
  const query = new URLSearchParams(params)
  if (process.env.OPENALEX_KEY) query.set('api_key', process.env.OPENALEX_KEY)
  const res = await tried(`OpenAlex ${route}`, () => get(`${OPENALEX}/${route}?${query}`))
  const left = Number.parseFloat(res.headers.get('x-ratelimit-remaining-usd'))
  if (Number.isFinite(left)) openalexBudget.usd = left
  return res.json()
}

const WORK_FIELDS = 'id,doi,display_name,publication_year,counts_by_year'
const workId = (work) => work.id.replace('https://openalex.org/', '')
const workCounts = (work, start) =>
  Object.fromEntries(work.counts_by_year.filter((c) => c.year >= start && c.cited_by_count).map((c) => [String(c.year), c.cited_by_count]))

// Works by DOI, 50 to a request. A DOI with a comma or pipe would split the filter, so it is asked on its own.
async function worksByDoi(dois) {
  const found = new Map()
  const plainDois = dois.filter((d) => !/[,|]/.test(d))
  for (let i = 0; i < plainDois.length; i += 50) {
    const batch = plainDois.slice(i, i + 50)
    const json = await openalex('works', { filter: `doi:${batch.join('|')}`, per_page: '100', select: WORK_FIELDS })
    for (const work of json.results) if (work.doi) found.set(work.doi.replace(/^https:\/\/doi\.org\//, '').toLowerCase(), work)
  }
  for (const doi of dois.filter((d) => /[,|]/.test(d))) {
    const res = await tried(`OpenAlex DOI ${doi}`, () => get(`${OPENALEX}/works/doi:${encodeURIComponent(doi)}?select=${WORK_FIELDS}`, {}, { missingOk: true }))
    if (res) found.set(doi, await res.json())
  }
  return found
}

async function worksById(ids) {
  const found = new Map()
  for (let i = 0; i < ids.length; i += 50) {
    const json = await openalex('works', { filter: `openalex:${ids.slice(i, i + 50).join('|')}`, per_page: '100', select: WORK_FIELDS })
    for (const work of json.results) found.set(workId(work), work)
  }
  return found
}

// A work whose title is the entry's title, apart from case, accents and punctuation.
async function workByTitle(entry) {
  const wanted = plain(entry.title)
  if (wanted.split(' ').length < 3) return null
  const json = await openalex('works', { filter: `title.search:${wanted}`, per_page: '5', select: WORK_FIELDS })
  return json.results.find((work) => plain(work.display_name) === wanted) ?? null
}

// Each entry's OpenAlex work: by DOI, then arXiv id, then exact title. Title matches are kept from the previous
// file, so a later run looks them up by id; titles not found are searched again after RECHECK_DAYS.
async function citations(entries, previous, start, today) {
  const lookups = {}
  const works = {}
  const keep = (key, work, via, checked) => {
    lookups[key] = { id: work ? workId(work) : null, via, ...(checked ? { checked } : {}) }
    if (work) works[workId(work)] = workCounts(work, start)
  }

  const byDoi = entries.filter((e) => e.doi || e.arxiv)
  const doiOfEntry = (e) => e.doi ?? `10.48550/arxiv.${e.arxiv}`
  const found = await worksByDoi([...new Set(byDoi.map(doiOfEntry))])
  for (const e of byDoi) keep(e.key, found.get(doiOfEntry(e)) ?? null, e.doi ? 'doi' : 'arxiv')

  const rest = entries.filter((e) => !lookups[e.key] && !NO_TITLE_SEARCH.has(e.type))
  const known = rest.filter((e) => previous[e.key]?.via === 'title' && previous[e.key].id)
  const knownWorks = await worksById(known.map((e) => previous[e.key].id))
  for (const e of known) keep(e.key, knownWorks.get(previous[e.key].id) ?? null, 'title', previous[e.key].checked)

  let searched = 0
  for (const e of rest.filter((x) => !lookups[x.key])) {
    const before = previous[e.key]
    const due = !before?.checked || addDays(before.checked, RECHECK_DAYS) <= today
    if (!due) {
      lookups[e.key] = before
      continue
    }
    if (searched >= TITLE_SEARCHES || openalexBudget.usd < OPENALEX_RESERVE_USD) continue
    searched++
    keep(e.key, await workByTitle(e), 'title', today)
  }
  return { searched, lookups, works }
}

// Object keys sorted at every level, so an unchanged collection writes the same file.
function sorted(value) {
  if (Array.isArray(value)) return value.map(sorted)
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map((k) => [k, sorted(value[k])]))
  return value
}

async function main() {
  if (!process.env.GITHUB_TOKEN) throw new Error('GitHub answers these requests only with a token: set GITHUB_TOKEN')
  const config = yaml.load(fs.readFileSync(path.join(ROOT, '_data/impact.yml'), 'utf8'))
  const listed = yaml.load(fs.readFileSync(path.join(ROOT, '_data/repositories.yml'), 'utf8'))
  const previous = fs.existsSync(OUT) ? JSON.parse(fs.readFileSync(OUT, 'utf8')) : {}
  const start = Number(config.start)
  const today = isoDay(new Date())
  const year = today.slice(0, 4)
  const yesterday = addDays(today, -1)

  const repos = []
  for (const org of listed.github_organizations ?? []) {
    console.log(`github  ${org}`)
    repos.push(...(await orgRepos(org, listed.github_organization_repos?.[org])))
  }
  repos.sort((a, b) => (a.repo < b.repo ? -1 : 1))

  // Stars by year where GitHub lists their days; otherwise the repository's count, kept for each year from the
  // first collection on.
  const starSnapshots = {}
  for (const repo of repos) {
    const days = repo.stars > 0 ? await stars(repo.repo) : []
    if (days) {
      repo.starred = byYear(days)
      continue
    }
    repo.starred = null
    const before = previous.starSnapshots?.[repo.repo]
    starSnapshots[repo.repo] = { first: before?.first ?? today, years: { ...before?.years, [year]: repo.stars } }
  }
  const snapshotted = Object.keys(starSnapshots)
  if (snapshotted.length) {
    const orgs = [...new Set(snapshotted.map((r) => r.split('/')[0]))]
    const why = orgs.map((org) => `${org}: ${starsRefusals[org] ?? 'refused'}`).join('; ')
    console.log(
      `::warning::GitHub did not list the star days of ${snapshotted.length} repositories to this token (${why}). ` +
        'Their stars count from the first collection on. Star days need a token that can push to the repository.',
    )
  }

  const listedRepos = new Set(repos.map((r) => r.repo.toLowerCase()))
  const pypiDay = await pypiThrough()
  const owned = {}
  const out = { pypi: { through: pypiDay, packages: {} }, npm: { through: null, packages: {} } }
  for (const entry of config.packages ?? []) {
    const repo = entry.repo.toLowerCase()
    if (!listedRepos.has(repo)) throw new Error(`_data/impact.yml lists ${entry.repo}, which the Repositories page does not list`)
    for (const pkg of entry.pypi ?? []) {
      console.log(`pypi    ${pkg}`)
      out.pypi.packages[pkg] = { repo: entry.repo, years: await pypi(pkg, `${start}-01-01`, pypiDay) }
    }
    for (const pattern of entry.npm ?? []) {
      const scope = /^@([^/]+)\//.exec(pattern)?.[1]
      if (pattern.includes('*') && !scope) throw new Error(`npm pattern ${pattern} in _data/impact.yml has no @scope`)
      if (scope && !owned[scope]) owned[scope] = await npmOwned(scope)
      const names = pattern.includes('*') ? npmNames([pattern], owned[scope]) : [pattern]
      let counted = 0
      for (const pkg of names) {
        const info = await npmPackage(pkg)
        // A package whose registry entry names another repository belongs to that repository.
        if (pattern.includes('*') && info.repo && info.repo !== repo) continue
        console.log(`npm     ${pkg}`)
        const from = info.created > `${start}-01-01` ? info.created : `${start}-01-01`
        const { years, last } = await npm(pkg, from, yesterday)
        out.npm.packages[pkg] = { repo: entry.repo, years }
        if (last && (!out.npm.through || last > out.npm.through)) out.npm.through = last
        counted++
      }
      if (!counted) throw new Error(`npm has no package matching ${pattern} from ${entry.repo}, which _data/impact.yml lists`)
    }
  }

  console.log('openalex citations')
  const entries = bibliography()
  const cited = await citations(entries, previous.citations?.lookups ?? {}, start, today)

  const metrics = {
    collected: today,
    start,
    repos,
    starSnapshots,
    pypi: out.pypi,
    npm: out.npm,
    citations: { through: today, lookups: cited.lookups, works: cited.works },
  }
  fs.writeFileSync(OUT, `${JSON.stringify(sorted(metrics), null, 1)}\n`)

  const found = Object.values(cited.lookups).filter((l) => l.id).length
  const pending = entries.filter((e) => !cited.lookups[e.key] && !NO_TITLE_SEARCH.has(e.type)).length
  const citedYears = {}
  for (const counts of Object.values(cited.works)) for (const [y, n] of Object.entries(counts)) citedYears[y] = (citedYears[y] ?? 0) + n
  const downloads = {}
  for (const { years } of [...Object.values(out.pypi.packages), ...Object.values(out.npm.packages)]) {
    for (const [y, n] of Object.entries(years)) downloads[y] = (downloads[y] ?? 0) + n
  }
  console.log(`\nrepositories  ${repos.length} (${repos.filter((r) => r.fork).length} forks), ${repos.reduce((n, r) => n + r.stars, 0)} stars today`)
  console.log(`downloads     ${JSON.stringify(downloads)} (PyPI through ${pypiDay}, npm through ${out.npm.through})`)
  console.log(`citations     ${found} of ${entries.length} entries found, ${cited.searched} titles searched, ${pending} titles left for a later run`)
  console.log(`              all entries, by year cited: ${JSON.stringify(citedYears)}`)
  console.log(`Wrote ${path.relative(ROOT, OUT)}`)
}

main().catch((error) => {
  console.error(error.message)
  process.exit(1)
})
