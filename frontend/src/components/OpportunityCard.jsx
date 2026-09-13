import { Target } from 'lucide-react'

/*
 * Market opportunity card. `potential_impact` is a qualitative label from the
 * backend - never invent a numeric score or dollar figure here.
 */
export default function OpportunityCard({ opportunity }) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-hairline bg-panel p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-evidence-soft text-evidence">
          <Target size={15} strokeWidth={1.75} />
        </span>
        <div className="min-w-0">
          <p className="font-serif text-[0.95rem] font-medium leading-snug text-ink">{opportunity.opportunity}</p>
          {opportunity.potential_impact && (
            <span className="mt-1.5 inline-block rounded-full bg-signal-soft px-2.5 py-1 text-[0.72rem] font-medium uppercase tracking-wide text-signal">
              {opportunity.potential_impact}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}