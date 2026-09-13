import { TrendingUp, Equal, Minus } from 'lucide-react'

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

/*
 * Trend card. Displays the impact the backend reported. If the backend ever
 * returns a numeric confidence score this card can surface it - for now impact
 * ("high"/"medium"/"low") is the only signal the backend provides.
 */
export default function TrendCard({ trend }) {
  const Icon = impactIcons[trend.impact] || Minus
  const badge = impactStyles[trend.impact] || impactStyles.low

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
    </div>
  )
}