import { MessageCircleMore, Info } from 'lucide-react'

/*
 * Follow-up box, prepared for a future conversational follow-up backend.
 * The Phase 3 backend has no follow-up endpoint, so this component is inert:
 * it shows the intended surface but explicitly refuses to fake a request.
 */
export default function FollowUpBox({ query }) {
  return (
    <div className="rounded-xl border border-dashed border-hairline bg-panel/60 p-5">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-paper text-ink-soft">
          <MessageCircleMore size={17} strokeWidth={1.75} />
        </span>
        <div>
          <p className="font-serif text-[0.975rem] font-medium text-ink">Ask a follow-up</p>
          <p className="text-[0.8rem] text-ink-soft">Continuing research on “{query}”</p>
        </div>
      </div>
      <div className="mt-4 flex items-start gap-2 rounded-lg bg-paper px-3.5 py-3 text-[0.82rem] leading-relaxed text-ink-soft">
        <Info size={15} strokeWidth={1.75} className="mt-0.5 shrink-0 text-signal" />
        <p>
          Follow-up research isn’t available yet. Start a new research to investigate this topic
          further — the full history is kept in Reports.
        </p>
      </div>
    </div>
  )
}