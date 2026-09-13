import { Sparkles } from 'lucide-react'

export default function InsightCard({ finding, evidence = [] }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-hairline bg-panel p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-signal-soft text-signal">
          <Sparkles size={15} strokeWidth={1.75} />
        </span>
        <p className="text-[0.925rem] leading-relaxed text-ink">{finding}</p>
      </div>
      {evidence.length > 0 && (
        <div className="mt-1 space-y-2 border-l-2 border-evidence pl-4">
          {evidence.map((item, i) => (
            <p key={i} className="text-[0.8rem] leading-relaxed text-ink-soft">
              {item}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}