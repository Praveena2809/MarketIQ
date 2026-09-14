import { useEffect, useState, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, FileUp, FileText, CheckCircle2, Loader2 } from 'lucide-react'
import { researchApi, documentsApi } from '../services/api'
import { RESEARCH_TYPES } from '../lib/format'
import ResearchProgress from '../components/ResearchProgress'
import InlineError from '../components/InlineError'

const DOC_STATUS = {
  completed: { label: 'Ready', cls: 'bg-evidence-soft text-evidence' },
  processing: { label: 'Processing', cls: 'bg-signal-soft text-signal' },
  uploaded: { label: 'Uploaded', cls: 'bg-paper text-ink-soft' },
  failed: { label: 'Failed', cls: 'bg-negative-soft text-negative' },
}

export default function NewResearchPage() {
  const { state } = useLocation()
  const navigate = useNavigate()

  const [query, setQuery] = useState(state?.query ?? '')
  const [focusInput, setFocusInput] = useState('')
  const [researchType, setResearchType] = useState('market_analysis')
  const [selectedDocIds, setSelectedDocIds] = useState([])
  const [documents, setDocuments] = useState(null)
  const [docError, setDocError] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [phase, setPhase] = useState('idle') // idle | running | failed
  const [runError, setRunError] = useState(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    documentsApi
      .list()
      .then((docs) => !cancelled && setDocuments(docs))
      .catch(() => !cancelled && setDocError('Could not load your documents.'))
    return () => {
      cancelled = true
    }
  }, [])

  const readyDocuments = (documents ?? []).filter((d) => d.status === 'completed')
  const usableCount = readyDocuments.length

  function toggleDocument(id) {
    setSelectedDocIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }

  async function handleUpload(file) {
    if (!file) return
    setUploading(true)
    setDocError(null)
    try {
      const created = await documentsApi.upload(file)
      const updated = await documentsApi.list()
      setDocuments(updated)
      if (created.status === 'completed') {
        setSelectedDocIds((prev) => (prev.includes(created.id) ? prev : [...prev, created.id]))
        return
      }
      if (created.status === 'failed' && created.error_message) {
        setDocError(`“${created.filename}” could not be parsed: ${created.error_message}`)
      }
    } catch {
      setDocError('Upload failed. Please try again.')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const trimmed = query.trim()
    if (!trimmed || phase === 'running') return

    // Competitor / focus context is composed into the query text itself -
    // the backend request schema has no dedicated competitors field.
    const focus = focusInput.trim()
    const fullQuery = focus ? `${trimmed}\n\nFocus: ${focus}` : trimmed

    setPhase('running')
    setRunError(null)
    try {
      const created = await researchApi.create({
        query: fullQuery,
        researchType,
        documentIds: selectedDocIds,
      })
      navigate(`/research/${created.research_id}`, { replace: true })
    } catch {
      setRunError('Research could not be completed right now. Please try again.')
      setPhase('failed')
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 lg:px-10">
      <h2 className="font-serif text-2xl text-ink">New Research</h2>
      <p className="mt-1 max-w-2xl text-[0.9rem] text-ink-soft">
        Describe what you want to understand. The research engine searches grounded sources and your
        uploaded documents, then compiles a structured briefing.
      </p>

      {runError && (
        <InlineError className="mt-6">{runError}</InlineError>
      )}

      {phase === 'running' ? (
        <ResearchProgress status="running" message="Analyzing market…" />
      ) : (
        <form onSubmit={handleSubmit} className="mt-6 grid gap-8 lg:grid-cols-[1.6fr_1fr]">
          <div className="space-y-6">
            <div className="rounded-xl border border-hairline bg-panel p-5 shadow-sm">
              <label className="text-[0.8rem] font-medium uppercase tracking-wider text-ink-soft">
                Research question
              </label>
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') handleSubmit(e)
                }}
                rows={3}
                placeholder="Analyze the Indian electric vehicle market for the next 12 months…"
                className="mt-2 w-full resize-y border border-hairline bg-paper px-3.5 py-3 text-[0.95rem] text-ink placeholder:text-ink-soft focus:border-evidence focus:outline-none"
              />
              <p className="mt-1.5 text-[0.75rem] text-ink-soft">
                Tip: press ⌘/Ctrl + Enter to run.
              </p>

              <label className="mt-5 block text-[0.8rem] font-medium uppercase tracking-wider text-ink-soft">
                Competitors or focus areas <span className="normal-case tracking-normal">(optional)</span>
              </label>
              <input
                value={focusInput}
                onChange={(e) => setFocusInput(e.target.value)}
                placeholder="e.g. Tata Motors, Ola Electric, Ather — regional outlook"
                className="mt-2 w-full border border-hairline bg-paper px-3.5 py-2.5 text-[0.925rem] text-ink placeholder:text-ink-soft focus:border-evidence focus:outline-none"
              />
              <p className="mt-1.5 text-[0.75rem] text-ink-soft">
                Added to the query as direction — the engine decides its own scope.
              </p>
            </div>

            <div className="rounded-xl border border-hairline bg-panel p-5 shadow-sm">
              <label className="text-[0.8rem] font-medium uppercase tracking-wider text-ink-soft">
                Research type
              </label>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {RESEARCH_TYPES.map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={researchType === value}
                    onClick={() => setResearchType(value)}
                    className={`rounded-lg border px-3.5 py-3 text-left text-[0.9rem] transition-colors ${
                      researchType === value
                        ? 'border-evidence bg-evidence-soft font-medium text-evidence'
                        : 'border-hairline bg-paper text-ink hover:border-ink-soft'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-6">
            <div className="rounded-xl border border-hairline bg-panel p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <label className="text-[0.8rem] font-medium uppercase tracking-wider text-ink-soft">
                  Your documents
                </label>
                <span className="text-[0.75rem] text-ink-soft">{usableCount} ready</span>
              </div>

              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-hairline py-2.5 text-[0.85rem] text-ink-soft transition-colors hover:border-evidence hover:text-evidence"
              >
                {uploading ? (
                  <>
                    <Loader2 size={15} className="animate-spin" /> Uploading…
                  </>
                ) : (
                  <>
                    <FileUp size={15} /> Upload a document (PDF, TXT, Markdown)
                  </>
                )}
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.txt,.md,.markdown"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
              />

              {docError && (
                <p className="mt-3 rounded-lg bg-negative-soft px-3 py-2 text-[0.78rem] text-negative">{docError}</p>
              )}

              <div className="mt-3 max-h-64 space-y-2 overflow-y-auto pr-1">
                {documents === null && (
                  <p className="animate-pulse py-3 text-[0.82rem] text-ink-soft">Loading documents…</p>
                )}
                {documents !== null && documents.length === 0 && (
                  <p className="py-3 text-[0.82rem] text-ink-soft">
                    No documents yet. Upload a PDF or text file to give research access to your own
                    materials.
                  </p>
                )}
                {documents !== null &&
                  documents.map((doc) => {
                    const meta = DOC_STATUS[doc.status] || DOC_STATUS.uploaded
                    const checked = selectedDocIds.includes(doc.id)
                    const eligible = doc.status === 'completed'
                    return (
                      <label
                        key={doc.id}
                        className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors ${
                          checked ? 'border-evidence bg-evidence-soft' : 'border-hairline hover:border-ink-soft'
                        } ${eligible ? '' : 'opacity-60'}`}
                      >
                        <input
                          type="checkbox"
                          className="accent-evidence"
                          disabled={!eligible}
                          checked={checked}
                          onChange={() => toggleDocument(doc.id)}
                        />
                        <FileText size={15} strokeWidth={1.75} className="shrink-0 text-ink-soft" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[0.85rem] text-ink">{doc.filename}</span>
                          <span className={`mt-0.5 inline-block rounded px-1.5 py-0.5 text-[0.68rem] font-medium uppercase ${meta.cls}`}>
                            {meta.label}
                          </span>
                        </span>
                        {checked && <CheckCircle2 size={15} className="shrink-0 text-evidence" />}
                      </label>
                    )
                  })}
              </div>
            </div>

            <button
              type="submit"
              disabled={!query.trim() || phase === 'running'}
              className="flex items-center justify-center gap-2 rounded-lg bg-evidence px-5 py-3 text-[0.9rem] font-medium text-white transition-colors hover:bg-evidence-dark disabled:opacity-50"
            >
              Generate Research
              <ArrowRight size={16} strokeWidth={2} />
            </button>
            {selectedDocIds.length > 0 && (
              <p className="text-center text-[0.78rem] text-ink-soft">
                {selectedDocIds.length} document{selectedDocIds.length > 1 ? 's' : ''} will be grounded into this research.
              </p>
            )}
          </div>
        </form>
      )}
    </div>
  )
}