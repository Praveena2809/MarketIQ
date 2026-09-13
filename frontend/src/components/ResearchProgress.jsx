import { Loader2, CheckCircle2 } from 'lucide-react'

const STAGES = [
  'Understanding research question',
  'Searching the knowledge base',
  'Analyzing available evidence',
  'Generating insights',
  'Preparing the report',
]

/*
 * Loading state shown while the synchronous POST /api/research request runs.
 *
 * The Phase 3 backend performs the full pipeline in a single synchronous
 * request, so the frontend cannot observe intermediate progress. This panel
 * shows an honest loading state plus the pipeline stages the engine performs -
 * it never fakes backend progress or sequential step completion.
 */
export default function ResearchProgress({ status = 'running', message = 'Researching your query…' }) {
  const done = status === 'completed'
  const failed = status === 'failed'

  return (
    <div className="mt-6 rounded-xl border border-hairline bg-panel p-6 shadow-sm">
      <div className="flex items-center gap-3">
        {done ? (
          <CheckCircle2 size={22} strokeWidth={2} className="text-evidence" />
        ) : (
          <Loader2 size={22} className="animate-spin text-evidence" />
        )}
        <div>
          <p className="font-serif text-[1.1rem] text-ink">{message}</p>
          <p className="mt-0.5 text-[0.8rem] text-ink-soft">
            The backend runs this pipeline synchronously - the report is generated in one pass.
          </p>
        </div>
      </div>

      {!failed && (
        <ul className="mt-5 space-y-2.5">
          {STAGES.map((stage, i) => {
            const index = i + 1
            return (
              <li key={stage} className="flex items-center gap-3 text-[0.875rem]">
                <span
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[0.7rem] ${
                    done
                      ? 'border-evidence bg-evidence-soft text-evidence'
                      : 'border-hairline text-ink-soft'
                  }`}
                >
                  {done ? <CheckCircle2 size={13} strokeWidth={2.5} /> : index}
                </span>
                <span className={done ? 'text-ink' : 'text-ink-soft'}>{stage}</span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}