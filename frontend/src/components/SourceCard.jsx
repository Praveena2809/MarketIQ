import { ExternalLink, FileText } from 'lucide-react'

function formatDate(iso) {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

/*
 * Displays a source returned by the backend. Every field shown here maps to
 * SourceSchema from the backend. When a value is absent the backend did not
 * provide it - we display the field as unavailable rather than inventing it.
 */
export default function SourceCard({ source }) {
  const relevance =
    typeof source.relevance === 'number' && Number.isFinite(source.relevance)
      ? `${Math.round(source.relevance * 100)}%`
      : null

  const isDocument = source.source_type === 'document'
  const provider = source.source_name || (isDocument ? 'Uploaded document' : 'Source')

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-hairline bg-panel p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-evidence-soft text-evidence">
          {isDocument ? <FileText size={16} strokeWidth={1.75} /> : <ExternalLink size={16} strokeWidth={1.75} />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-serif text-[0.975rem] leading-snug text-ink">{source.title}</p>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.75rem] text-ink-soft">
            <span className="uppercase tracking-wide">{provider}</span>
            <span className="rounded bg-paper px-1.5 py-0.5 uppercase tracking-wide text-ink-soft">
              {source.source_type}
            </span>
            {formatDate(source.published_at) && <span>{formatDate(source.published_at)}</span>}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3">
        <p className="text-[0.8rem] text-ink-soft">
          {relevance ? (
            <>Relevance: <span className="font-medium text-ink">{relevance}</span></>
          ) : (
            <span>Source from {provider}</span>
          )}
        </p>
        {source.url ? (
          <a
            href={source.url}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 rounded-md border border-hairline px-3 py-1.5 text-[0.8rem] font-medium text-evidence transition-colors hover:border-evidence hover:bg-evidence-soft"
          >
            View Source
            <ExternalLink size={13} strokeWidth={1.75} />
          </a>
        ) : (
          <span className="text-[0.75rem] italic text-ink-soft">No URL provided by the source</span>
        )}
      </div>
    </div>
  )
}