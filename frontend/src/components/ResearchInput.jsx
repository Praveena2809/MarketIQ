import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Compass, Loader2 } from 'lucide-react'

/*
 * Large research intake input used on the Dashboard hero.
 * Either runs an inline `onSubmit(query)` or navigates to the
 * dedicated New Research page with the query pre-filled.
 */
export default function ResearchInput({
  initialQuery = '',
  submitting = false,
  submitLabel = 'Start Research',
  onSubmit,
  placeholder = 'Analyze a market, company or industry...',
}) {
  const navigate = useNavigate()
  const [query, setQuery] = useState(initialQuery)

  function handleSubmit(e) {
    e.preventDefault()
    if (!query.trim() || submitting) return
    if (onSubmit) {
      onSubmit(query.trim())
    } else {
      navigate('/research/new', { state: { query: query.trim() } })
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-6">
      <div className="flex items-center gap-3 rounded-xl border border-hairline bg-panel px-4 py-3 shadow-sm focus-within:border-evidence">
        <Compass size={18} strokeWidth={1.75} className="shrink-0 text-ink-soft" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={placeholder}
          aria-label="Research query"
          className="w-full bg-transparent text-[0.95rem] text-ink placeholder:text-ink-soft focus:outline-none"
        />
        <button
          type="submit"
          disabled={submitting || !query.trim()}
          className="flex items-center gap-2 rounded-lg bg-evidence px-5 py-2.5 text-[0.85rem] font-medium text-white transition-colors hover:bg-evidence-dark disabled:opacity-50"
        >
          {submitting ? (
            <>
              <Loader2 size={15} strokeWidth={2} className="animate-spin" />
              Analyzing…
            </>
          ) : (
            <>
              {submitLabel}
              <ArrowRight size={15} strokeWidth={2} />
            </>
          )}
        </button>
      </div>
    </form>
  )
}