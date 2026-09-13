import { useMemo } from 'react'
import { Smile, PieChart } from 'lucide-react'
import useRecentReports from '../hooks/useRecentReports'
import { typeLabel, formatDate } from '../lib/format'
import EmptyState from '../components/EmptyState'

/*
 * Sentiment view.
 *
 * The backend stores sentiment qualitatively - the market overview and
 * conclusion language it synthesized - and does not expose numeric sentiment
 * percentages or category counts. This page therefore surfaces the qualitative
 * view per report and explicitly explains that no chart data exists yet. A
 * donut/score chart is intentionally omitted until the backend provides
 * numeric sentiment (spec: charts only from real data).
 */
export default function SentimentPage() {
  const { details, error, loading } = useRecentReports({ limit: 20, includeResults: true })

  const sentiment = useMemo(
    () =>
      (details ?? [])
        .map((r) => ({
          id: r.research_id,
          query: r.query,
          type: r.research_type,
          updatedAt: r.updated_at,
          overview: r.result?.market_overview,
          conclusion: r.result?.conclusion,
        }))
        .filter((s) => s.overview || s.conclusion),
    [details],
  )

  return (
    <div className="mx-auto max-w-4xl px-6 py-10 lg:px-10">
      <h2 className="font-serif text-2xl text-ink">Sentiment Insights</h2>

      <div className="mt-4 flex items-start gap-3 rounded-xl border border-hairline bg-panel px-4 py-3.5">
        <PieChart size={17} strokeWidth={1.75} className="mt-0.5 shrink-0 text-signal" />
        <p className="text-[0.85rem] leading-relaxed text-ink-soft">
          MarketIQ currently expresses sentiment <span className="font-medium text-ink">qualitatively</span> —
          through the language of each report’s market overview and conclusion. Numeric sentiment scoring
          isn’t provided by the backend yet, so a percentage breakdown chart isn’t shown.
        </p>
      </div>

      {error && (
        <p className="mt-5 rounded-lg border border-negative-soft bg-negative-soft px-4 py-3 text-[0.875rem] text-negative">
          {error}
        </p>
      )}

      <div className="mt-6">
        {loading ? (
          <div className="animate-pulse space-y-3">
            {[0, 1].map((i) => (
              <div key={i} className="h-32 rounded-xl border border-hairline bg-panel" />
            ))}
          </div>
        ) : sentiment.length === 0 ? (
          <EmptyState
            title="No sentiment insights yet"
            description="Completed reports appear here with their qualitative market outlook. Run research to populate this view."
            icon={Smile}
          />
        ) : (
          <div className="space-y-4">
            {sentiment.map((s) => (
              <article key={s.id} className="rounded-xl border border-hairline bg-panel p-5 shadow-sm">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <p className="font-serif text-[1rem] font-medium text-ink">{s.query}</p>
                  <span className="rounded-full border border-hairline bg-paper px-2 py-0.5 text-[0.72rem] text-ink-soft">
                    {typeLabel(s.type)}
                  </span>
                  <span className="text-[0.75rem] text-ink-soft">{formatDate(s.updatedAt)}</span>
                </div>
                <div className="mt-4 space-y-4">
                  {s.overview && (
                    <blockquote className="border-l-[3px] border-evidence pl-4">
                      <p className="text-[0.8rem] font-medium uppercase tracking-wider text-ink-soft">Market outlook</p>
                      <p className="mt-1 font-serif text-[0.95rem] leading-relaxed text-ink">{s.overview}</p>
                    </blockquote>
                  )}
                  {s.conclusion && (
                    <blockquote className="border-l-[3px] border-signal pl-4">
                      <p className="text-[0.8rem] font-medium uppercase tracking-wider text-ink-soft">Conclusion</p>
                      <p className="mt-1 font-serif text-[0.95rem] leading-relaxed text-ink">{s.conclusion}</p>
                    </blockquote>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}