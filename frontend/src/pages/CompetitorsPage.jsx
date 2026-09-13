import { useMemo } from 'react'
import { Building2 } from 'lucide-react'
import useRecentReports from '../hooks/useRecentReports'
import CompetitorCard from '../components/CompetitorCard'
import EmptyState from '../components/EmptyState'

function uniq(items) {
  const seen = new Set()
  const out = []
  for (const item of items) {
    const key = String(item).trim().toLowerCase()
    if (!key || seen.has(key)) continue
    seen.add(key)
    out.push(item)
  }
  return out
}

/*
 * Aggregates competitor profiles across completed reports. Share is shown
 * verbatim as the backend reported it (a qualitative string, not a fabricated
 * percentage). Strengths/weaknesses are unioned and deduplicated across runs.
 */
export default function CompetitorsPage() {
  const { details, error, loading } = useRecentReports({ limit: 20, includeResults: true })

  const competitors = useMemo(() => {
    const map = new Map()
    for (const report of details ?? []) {
      for (const c of report.result?.competitors ?? []) {
        if (!c.company) continue
        const entry = map.get(c.company) || { company: c.company, strengths: [], weaknesses: [], shares: [] }
        entry.strengths = uniq([...entry.strengths, ...(c.strengths || [])])
        entry.weaknesses = uniq([...entry.weaknesses, ...(c.weaknesses || [])])
        if (c.market_share && !entry.shares.includes(c.market_share)) entry.shares.push(c.market_share)
        map.set(c.company, entry)
      }
    }
    return [...map.values()].map((c) => ({ ...c, market_share: c.shares.join(' / ') || null }))
  }, [details])

  return (
    <div className="mx-auto max-w-4xl px-6 py-10 lg:px-10">
      <h2 className="font-serif text-2xl text-ink">Competitor Analysis</h2>
      <p className="mt-1 max-w-2xl text-[0.9rem] text-ink-soft">
        Competitor profiles aggregated across your research history. Market share reflects only what
        the engine reported from its sources - it is never estimated here.
      </p>

      {error && (
        <p className="mt-6 rounded-lg border border-negative-soft bg-negative-soft px-4 py-3 text-[0.875rem] text-negative">
          {error}
        </p>
      )}

      <div className="mt-7">
        {loading ? (
          <div className="animate-pulse space-y-3">
            {[0, 1].map((i) => (
              <div key={i} className="h-40 rounded-xl border border-hairline bg-panel" />
            ))}
          </div>
        ) : competitors.length === 0 ? (
          <EmptyState
            title="Competitor data unavailable"
            description="Run competitor or market research to build profiles. The backend reports ties between competitors and their reported strengths and weaknesses when evidence supports it."
            icon={Building2}
          />
        ) : (
          <div className="grid gap-4">
            {competitors.map((c, i) => (
              <CompetitorCard key={c.company || i} competitor={c} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}