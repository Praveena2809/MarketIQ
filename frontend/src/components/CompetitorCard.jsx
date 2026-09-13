import { Building2, CircleMinus, CirclePlus } from 'lucide-react'

function BulletList({ items, icon }) {
  if (!items || items.length === 0) {
    return (
      <p className="text-[0.8rem] italic text-ink-soft">Data unavailable</p>
    )
  }
  return (
    <ul className="space-y-1.5">
      {items.map((item, i) => (
        <li key={i} className="flex items-start gap-2 text-[0.82rem] leading-relaxed text-ink-soft">
          {icon}
          <span className="text-ink">{item}</span>
        </li>
      ))}
    </ul>
  )
}

/*
 * Competitor card. `market_share` is a qualitative string from the backend
 * (e.g. "Leading" or a figure the model quoted) - displayed verbatim.
 */
export default function CompetitorCard({ competitor }) {
  const share = competitor.market_share
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-hairline bg-panel p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-paper text-ink-soft">
            <Building2 size={18} strokeWidth={1.75} />
          </span>
          <p className="font-serif text-[1.05rem] font-medium text-ink">{competitor.company}</p>
        </div>
        <span className="rounded-full border border-hairline bg-paper px-3 py-1 text-[0.75rem] text-ink-soft">
          Share: {share || 'Data unavailable'}
        </span>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-[0.72rem] font-medium uppercase tracking-wide text-evidence">
            <CirclePlus size={13} strokeWidth={2} /> Strengths
          </p>
          <BulletList items={competitor.strengths} icon={<CirclePlus size={13} className="mt-0.5 shrink-0 text-evidence" />} />
        </div>
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-[0.72rem] font-medium uppercase tracking-wide text-negative">
            <CircleMinus size={13} strokeWidth={2} /> Weaknesses
          </p>
          <BulletList items={competitor.weaknesses} icon={<CircleMinus size={13} className="mt-0.5 shrink-0 text-negative" />} />
        </div>
      </div>
    </div>
  )
}