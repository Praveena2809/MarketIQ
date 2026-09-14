import { useMemo } from 'react'
import { Smile } from 'lucide-react'
import useRecentReports from '../hooks/useRecentReports'
import { typeLabel, formatDate } from '../lib/format'
import EmptyState from '../components/EmptyState'
import SentimentCard from '../components/SentimentCard'
import InlineError from '../components/InlineError'

/*
 * Sentiment view backed by the backend's categorical, evidence-grounded
 * sentiment data (Step 7). Each completed report shows an overall sentiment
 * card plus one card per identified competitor the evidence supported.
 *
 * Sentiment is categorical and qualitative only (positive / neutral /
 * negative / mixed / unavailable) - the backend never emits numeric scores,
 * so no charts or numeric visualizations are shown here by design.
 */
export default function SentimentPage() {
  const { details, error, loading } = useRecentReports({ limit: 20, includeResults: true })

  const reports = useMemo(
    () => (details ?? []).filter((r) => r.result?.sentiment),
    [details],
  )

  return (
    <div className="mx-auto max-w-4xl px-6 py-10 lg:px-10">
      <h2 className="font-serif text-2xl text-ink">Sentiment Insights</h2>

      <div className="mt-4 flex items-start gap-3 rounded-xl border border-hairline bg-panel px-4 py-3.5">
        <Smile size={17} strokeWidth={1.75} className="mt-0.5 shrink-0 text-signal" />
        <p className="text-[0.85rem] leading-relaxed text-ink-soft">
          MarketIQ reports sentiment <span className="font-medium text-ink">categorically</span> —
          positive, neutral, negative, mixed, or unavailable — grounded only in each report’s
          sources. Labels are corroborated by verifiable evidence references; numeric scores are
          never fabricated, so charts aren’t shown.
        </p>
      </div>

      {error && (
        <InlineError className="mt-5">{error}</InlineError>
      )}

      <div className="mt-6">
        {loading ? (
          <div className="animate-pulse space-y-3">
            {[0, 1].map((i) => (
              <div key={i} className="h-32 rounded-xl border border-hairline bg-panel" />
            ))}
          </div>
        ) : !error && reports.length === 0 ? (
          <EmptyState
            title="No sentiment insights yet"
            description="Reports with categorical sentiment data appear here. Run research to populate this view."
            icon={Smile}
          />
        ) : (
          <div className="space-y-6">
            {reports.map((r) => {
              const sentiment = r.result.sentiment
              return (
                <article key={r.research_id}>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <p className="font-serif text-[1rem] font-medium text-ink">{r.query}</p>
                    <span className="rounded-full border border-hairline bg-paper px-2 py-0.5 text-[0.72rem] text-ink-soft">
                      {typeLabel(r.research_type)}
                    </span>
                    <span className="text-[0.75rem] text-ink-soft">{formatDate(r.updated_at)}</span>
                  </div>
                  <div className="mt-3 space-y-3">
                    <SentimentCard title="Overall sentiment" sentiment={sentiment.overall} />
                    {(sentiment.entities ?? []).map((entity) => (
                      <SentimentCard
                        key={entity.entity}
                        title={`${entity.entity} sentiment`}
                        sentiment={entity}
                      />
                    ))}
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}