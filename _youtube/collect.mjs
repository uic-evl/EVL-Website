// Collects the evltube channel's public videos with their view counts and writes _data/youtube.json,
// which the Videos page (/videos/) reads. The youtube workflow runs it weekly and commits the file.
//
//   YOUTUBE_API=<key> node _youtube/collect.mjs
//
// Uses the YouTube Data API v3: the channel's uploads playlist (1 quota unit per 50 videos) and
// videos.list for statistics (1 unit per 50 videos), so a run costs a few dozen units of the
// 10,000 a day a project gets. A failed request stops the script and leaves the previous file.

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const OUT = path.join(ROOT, '_data/youtube.json')
const API = 'https://www.googleapis.com/youtube/v3'
const CHANNEL = process.env.YOUTUBE_CHANNEL || 'UC3GTGwIcQfqqMS-Wt9uMwyQ'   // evltube
const KEY = process.env.YOUTUBE_API
if (!KEY) {
  console.error('YOUTUBE_API is not set')
  process.exit(1)
}

async function get(endpoint, params) {
  const url = new URL(`${API}/${endpoint}`)
  for (const [k, v] of Object.entries({ ...params, key: KEY })) url.searchParams.set(k, v)
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${endpoint}: HTTP ${res.status} ${(await res.text()).slice(0, 300)}`)
  return res.json()
}

// ISO 8601 duration (PT1H2M3S) to seconds.
function seconds(iso) {
  const m = /^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/.exec(iso || '')
  return m ? (+m[1] || 0) * 3600 + (+m[2] || 0) * 60 + (+m[3] || 0) : 0
}

// 1. Every video id in the uploads playlist (UU + channel id without UC).
const uploads = 'UU' + CHANNEL.slice(2)
const ids = []
for (let pageToken = ''; ; ) {
  const page = await get('playlistItems', { part: 'contentDetails', playlistId: uploads, maxResults: 50, pageToken })
  ids.push(...page.items.map((i) => i.contentDetails.videoId))
  if (!page.nextPageToken) break
  pageToken = page.nextPageToken
}

// 2. Title, date, duration, privacy and statistics, 50 at a time.
const videos = []
for (let i = 0; i < ids.length; i += 50) {
  const page = await get('videos', { part: 'snippet,contentDetails,statistics,status', id: ids.slice(i, i + 50).join(',') })
  for (const v of page.items) {
    if (v.status?.privacyStatus !== 'public' || v.snippet?.liveBroadcastContent !== 'none') continue
    videos.push({
      id: v.id,
      title: v.snippet.title,
      published: v.snippet.publishedAt.slice(0, 10),
      seconds: seconds(v.contentDetails?.duration),
      views: +(v.statistics?.viewCount ?? 0),
    })
  }
}
videos.sort((a, b) => (a.published < b.published ? 1 : a.published > b.published ? -1 : 0))

const out = {
  collected: new Date().toISOString().slice(0, 10),
  channel: { id: CHANNEL, url: `https://www.youtube.com/channel/${CHANNEL}` },
  count: videos.length,
  views: videos.reduce((n, v) => n + v.views, 0),
  videos,
}
fs.writeFileSync(OUT, JSON.stringify(out, null, 2) + '\n')
console.log(`${videos.length} public videos, ${out.views} views in total, written to ${path.relative(ROOT, OUT)}`)
