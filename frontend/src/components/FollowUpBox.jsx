import { useState } from 'react'
import { MessageCircleMore, ExternalLink, Loader2, AlertTriangle, Info } from 'lucide-react'
import { researchApi } from '../services/api'

/*
 * Follow-up Q&A box (Step 12).
 *
 * Sends the user's follow-up question to the backend, which answers it using
 * ONLY the stored research context (the original ResearchResult plus the
 * recorded Source metadata) via a single Gemini call. The box is stateless in
 * the UI: each new question replaces the previous answer.
 *
 * The sources rendered below the answer are the complete set of research
 * sources recorded for the research run. They are deliberately labeled
 * "Research sources" - the backend does NOT map each sentence of the answer to
 * a specific source, and the frontend must not imply that every source
 * directly supports the specific answer.
 */
export default function FollowUpBox({ researchId, query }) {
  const [question, setQuestion] = useState('')
  const [status, setStatus] = useState('idle') // idle | loading | ready | error
  const [answer, setAnswer] = useState('')
  const [insufficient, setInsufficient] = useState(false)
  const [sources, setSources] = useState([])
  const [error, setError] = useState(null)

  const canAsk = question.trim().length > 0 && status !== 'loading'

  async function handleAsk(e) {
    e.preventDefault()
    if (!canAsk) return
    setStatus('loading')
    setError(null)
    try {
      const data = await researchApi.followUp(researchId, question.trim())
      setAnswer(data.answer)
      setInsufficient(Boolean(data.insufficient_evidence))
      setSources(data.sources || [])
      setStatus('ready')
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          'The follow-up could not be answered. Please try again.',
      )
      setStatus('error')
    }
  }

  return (
    <div className="rounded-xl border border-hairline bg-panel/60 p-5">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-paper text-ink-soft">
          <MessageCircleMore size={17} strokeWidth={1.75} />
        </span>
        <div>
          <p className="font-serif text-[0.975rem] font-medium text-ink">Ask a follow-up</p>
          <p className="text-[0.8rem] text-ink-soft">Continuing research on “{query}”</p>
        </div>
      </div>

      <form onSubmit={handleAsk} className="mt-4 flex items-center gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about this research…"
          aria-label="Follow-up question"
          className="min-w-0 flex-1 rounded-lg border border-hairline bg-paper px-3.5 py-2.5 text-[0.85rem] text-ink placeholder:text-ink-soft focus:border-evidence focus:outline-none"
        />
        <button
          type="submit"
          disabled={!canAsk}
          className="shrink-0 rounded-lg bg-evidence px-4 py-2.5 text-[0.85rem] font-medium text-white transition-colors hover:bg-evidence-dark disabled:cursor-not-allowed disabled:opacity-40"
        >
          {status === 'loading' ? 'Thinking…' : 'Ask'}
        </button>
      </form>

      {status === 'loading' && (
        <div className="mt-4 flex items-center gap-2 text-[0.82rem] text-ink-soft">
          <Loader2 size={15} strokeWidth={1.75} className="animate-spin text-evidence" />
          Answering from the research context…
        </div>
      )}

      {status === 'error' && (
        <div className="mt-4 flex items-start gap-2 rounded-lg bg-negative-soft px-3.5 py-3 text-[0.82rem] leading-relaxed text-negative">
          <AlertTriangle size={15} strokeWidth={1.75} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-medium">The follow-up could not be answered.</p>
            <p className="mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {status === 'ready' && (
        <div className="mt-4">
          {insufficient && (
            <div className="mb-3 flex items-start gap-2 rounded-lg bg-signal-soft px-3.5 py-3 text-[0.82rem] leading-relaxed text-ink-soft">
              <Info size={15} strokeWidth={1.75} className="mt-0.5 shrink-0 text-signal" />
              <p>
                The stored research context does not contain enough evidence to fully answer this
                question. The model response below states what is missing.
              </p>
            </div>
          )}

          <div className="rounded-lg bg-paper px-4 py-3.5">
            <p className="font-serif text-[0.975rem] leading-relaxed text-ink">{answer}</p>
          </div>

          {sources.length > 0 && (
            <div className="mt-3">
              <p className="text-[0.75rem] uppercase tracking-wider text-ink-soft">Research sources</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {sources.map((s) =>
                  s.url ? (
                    <a
                      key={s.id}
                      href={s.url}
                      target="_blank"
                      rel="noreferrer"
                      className="group flex items-center gap-1.5 rounded-md border border-hairline bg-paper px-2.5 py-1.5 text-[0.78rem] text-ink-soft transition-colors hover:border-evidence hover:text-evidence"
                    >
                      <span className="max-w-56 truncate">{s.title || s.source_name}</span>
                      <ExternalLink size={12} strokeWidth={1.75} className="shrink-0 text-evidence" />
                    </a>
                  ) : (
                    <span
                      key={s.id}
                      className="flex items-center gap-1.5 rounded-md border border-hairline bg-paper px-2.5 py-1.5 text-[0.78rem] text-ink-soft"
                    >
                      <span className="max-w-56 truncate">{s.title || s.source_name}</span>
                    </span>
                  ),
                )}
              </div>
              <p className="mt-2 text-[0.72rem] text-ink-soft">
                Sources recorded for this research run. Not every source directly supports this
                specific answer.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}