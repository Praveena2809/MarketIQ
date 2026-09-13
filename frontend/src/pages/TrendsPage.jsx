import { useMemo } from 'react'
import { TrendingUp } from 'lucide-react'
import useRecentReports from '../hooks/useRecentReports'
import TrendCard from '../components/TrendCard'
import EmptyState from '../components/EmptyState'

/*
 * Aggregates trends across completed reports, deduplicated by name. The backend
 * reports impact as a qualitative label ("high"/"medium"/"low") only - there is
 * no numeric confidence or momentum score, so this page never fabricates one.
 */
export default function TrendsPage() {
  const { details, error, loading } = useRecentReports({ limit: 20, includeResults: true })

  const trends = useMemo(() => {
    const map = new Map()
    for (const report of details ?? []) {
      for (const t of report.result?.trends ?? []) {
        if (!t.trend) continue
        const entry = map.get(t.trend) || {
          trend: t.trend,
          impact: t.impact,
          description: t.description,
          evidence: [],
          source_types: [],
          direction: t.direction,
          as_of: t.as_of,
          mentions: 0,
        }
        entry.mentions += 1
        if (!entry.description && t.description) entry.description = t.description
        if (t.evidence?.length) entry.evidence = Array.from(new Set([...entry.evidence, ...t.evidence]))
        if (t.source_types?.length) entry.source_types = Array.from(new Set([...entry.source_types, ...t.source_types]))
        if (t.direction) entry.direction = t.direction
        map.set(t.trend, entry)
      }
    }
    const order = { high: 0, medium: 1, low: 2 }
    return [...map.values()].sort((a, b) => (order[a.impact] ?? 3) - (order[b.impact] ?? 3))
  }, [details])

  return (
    <div className="mx-auto max-w-4xl px-6 py-10 lg:px-10">
      <h2 className="font-serif text-2xl text-ink">Industry Trends</h2>
      <p className="mt-1 max-w-2xl text-[0.9rem] text-ink-soft">
        Trends surfaced by the research engine across your reports, ranked by the impact level the
        engine assigned. Momentum is shown as a qualitative label, not a numeric score.
      </p>

      {error && (
        <p className="mt-6 rounded-lg border border-negative-soft bg-negative-soft px-4 py-3 text-[0.875rem] text-negative">
          {error}
        </p>
      )}

      <div className="mt-7">
        {loading ? (
          <div className="animate-pulse space-y-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-24 rounded-xl border border-hairline bg-panel" />
            ))}
          </div>
        ) : trends.length === 0 ? (
          <EmptyState
            title="Trend data unavailable"
            description="Run market or industry-trend research to surface trends. The engine reports trends only when grounded evidence supports them."
            icon={TrendingUp}
          />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {trends.map((t, i) => (
              <div key={t.trend || i}>
                <TrendCard trend={t} />
                {t.mentions > 1 && (
                  <p className="mt-1 pl-1 text-[0.72rem] text-ink-soft">Mentioned in {t.mentions} reports</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}