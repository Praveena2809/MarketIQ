import { Activity, CircleAlert } from 'lucide-react'

const LABEL_STYLES = {
  positive: 'bg-evidence-soft text-evidence',
  neutral: 'bg-paper text-ink-soft border border-hairline',
  mixed: 'bg-signal-soft text-signal',
  negative: 'bg-negative-soft text-negative',
  unavailable: 'bg-paper text-ink-soft border border-hairline',
}

const SOURCE_LABELS = {
  web: 'Web evidence',
  news: 'News evidence',
  document: 'Document evidence',
  competitor: 'Competitor evidence',
}

/*
 * Sentiment card. Displays the categorical label, the qualitative summary,
 * the source-type tags, and the verifiable evidence references exactly as the
 * backend reported them. No numeric scores are shown: sentiment is categorical
 * by design, so a chart would only present fabricated data.
 */
export default function SentimentCard({ title, sentiment }) {
  const label = sentiment?.label || 'unavailable'
  const summary = sentiment?.summary || ''
  const sourceTypes = sentiment?.source_types || []
  const evidence = sentiment?.evidence || []
  const badge = LABEL_STYLES[label] || LABEL_STYLES.unavailable
  const isUnavailable = label === 'unavailable'

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-hairline bg-panel p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-paper text-ink-soft">
            {isUnavailable ? <CircleAlert size={18} strokeWidth={1.75} /> : <Activity size={18} strokeWidth={1.75} />}
          </span>
          <p className="font-serif text-[1.05rem] font-medium text-ink">{title}</p>
        </div>
        <span className={`flex items-center rounded-full px-3 py-1 text-[0.72rem] font-medium uppercase tracking-wide ${badge}`}>
          {label}
        </span>
      </div>

      {summary && <p className="text-[0.85rem] leading-relaxed text-ink-soft">{summary}</p>}

      {sourceTypes.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {sourceTypes.map((st) => (
            <span key={st} className="rounded bg-paper px-1.5 py-0.5 text-[0.68rem] uppercase tracking-wide text-ink-soft">
              {SOURCE_LABELS[st] || `${st} evidence`}
            </span>
          ))}
        </div>
      )}

      {evidence.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-hairline pt-3">
          <p className="flex items-center gap-1.5 text-[0.72rem] font-medium uppercase tracking-wide text-ink-soft">
            <Activity size={13} strokeWidth={2} /> Evidence
          </p>
          {evidence.map((id) => (
            <span key={id} className="rounded bg-paper px-1.5 py-0.5 font-mono text-[0.68rem] text-ink-soft">
              {id}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}