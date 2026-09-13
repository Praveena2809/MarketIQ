import { TrendingUp, Equal, Minus, ArrowUp, ArrowDown, MoveUpRight } from 'lucide-react'

const impactIcons = {
  high: TrendingUp,
  medium: Equal,
  low: Minus,
}

const impactStyles = {
  high: 'bg-signal-soft text-signal',
  medium: 'bg-signal-soft/60 text-signal',
  low: 'bg-paper text-ink-soft',
}

const directionMeta = {
  rising: { Icon: ArrowUp, label: 'Rising' },
  stable: { Icon: Equal, label: 'Stable' },
  declining: { Icon: ArrowDown, label: 'Declining' },
  mixed: { Icon: MoveUpRight, label: 'Mixed' },
}

const sourceTypeLabel = {
  web: 'Web',
  news: 'News',
  document: 'Document',
  competitor: 'Competitor',
}

/*
 * Trend card. Displays the impact level the backend reported and, when present,
 * the evidence-grounded provenance: an optional direction label (rising/stable/
 * declining/mixed), server-derived source-type tags, and the research evidence
 * IDs the trend is anchored to. Direction is a qualitative label only - there
 * is no numeric confidence or momentum score.
 */
export default function TrendCard({ trend }) {
  const Icon = impactIcons[trend.impact] || Minus
  const badge = impactStyles[trend.impact] || impactStyles.low
  const direction = trend.direction && directionMeta[trend.direction]
  const sourceTypes = trend.source_types ?? []
  const evidence = trend.evidence ?? []
  const asOf = trend.as_of

  return (
    <div className="flex flex-col gap-2.5 rounded-xl border border-hairline bg-panel p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-serif text-[0.975rem] font-medium text-ink">{trend.trend}</p>
        <span className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-[0.72rem] font-medium uppercase tracking-wide ${badge}`}>
          <Icon size={12} strokeWidth={2} />
          {trend.impact}
        </span>
      </div>

      {trend.description && <p className="text-[0.825rem] leading-relaxed text-ink-soft">{trend.description}</p>}

      {(direction || asOf) && (
        <div className="flex flex-wrap items-center gap-2 text-[0.72rem]">
          {direction && (
            <span className="inline-flex items-center gap-1 rounded-md border border-hairline bg-paper px-2 py-0.5 font-medium text-ink-soft">
              <direction.Icon size={12} strokeWidth={2} />
              {direction.label}
            </span>
          )}
          {asOf && <span className="text-ink-soft/80">As of {asOf.replace('T', ' ').replace('Z', '').replace('+00:00', ' UTC')}</span>}
        </div>
      )}

      {sourceTypes.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {sourceTypes.map((st) => (
            <span key={st} className="rounded-md bg-signal-soft/50 px-2 py-0.5 text-[0.68rem] font-medium uppercase tracking-wide text-signal">
              {sourceTypeLabel[st] ?? st}
            </span>
          ))}
        </div>
      )}

      {evidence.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[0.68rem] uppercase tracking-wide text-ink-soft">Evidence</span>
          {evidence.map((id) => (
            <code key={id} className="rounded border border-hairline bg-paper px-1.5 py-0.5 font-mono text-[0.68rem] text-ink-soft">
              {id}
            </code>
          ))}
        </div>
      )}
    </div>
  )
}