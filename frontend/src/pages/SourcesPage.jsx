import { useMemo, useState } from 'react'
import { Library, Search } from 'lucide-react'
import useRecentReports from '../hooks/useRecentReports'
import SourceCard from '../components/SourceCard'
import EmptyState from '../components/EmptyState'

const typeFilters = [
  { value: 'all', label: 'All' },
  { value: 'web', label: 'Web' },
  { value: 'document', label: 'Documents' },
]

/*
 * Aggregates every recorded source across recent reports. Source provenance is
 * exactly what the backend recorded (or an own-document source) - no URLs,
 * titles, or source names are synthesized here.
 */
export default function SourcesPage() {
  const { details, error, loading } = useRecentReports({ limit: 20, includeResults: true })
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')

  const sources = useMemo(() => {
    const out = []
    for (const report of details ?? []) {
      for (const source of report.sources ?? []) {
        out.push({ ...source, reportQuery: report.query })
      }
    }
    const q = search.trim().toLowerCase()
    return out
      .filter((s) => (filter === 'all' ? true : s.source_type === filter))
      .filter((s) => !q || (s.title || '').toLowerCase().includes(q) || (s.source_name || '').toLowerCase().includes(q))
  }, [details, filter, search])

  return (
    <div className="mx-auto max-w-4xl px-6 py-10 lg:px-10">
      <h2 className="font-serif text-2xl text-ink">Sources</h2>
      <p className="mt-1 max-w-2xl text-[0.9rem] text-ink-soft">
        The grounded sources MarketIQ has recorded across your research - live web citations and the
        documents you’ve uploaded. An empty or sparse list means research ran without enough
        accessible evidence.
      </p>

      {error && (
        <p className="mt-6 rounded-lg border border-negative-soft bg-negative-soft px-4 py-3 text-[0.875rem] text-negative">
          {error}
        </p>
      )}

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 rounded-lg border border-hairline bg-panel px-3 py-2 focus-within:border-evidence sm:w-72">
          <Search size={15} strokeWidth={2} className="shrink-0 text-ink-soft" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search sources…"
            aria-label="Search sources"
            className="w-full bg-transparent text-[0.875rem] text-ink placeholder:text-ink-soft focus:outline-none"
          />
        </div>
        <div className="flex rounded-lg border border-hairline bg-panel p-0.5">
          {typeFilters.map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`rounded-md px-3 py-1.5 text-[0.78rem] transition-colors ${
                filter === f.value ? 'bg-evidence-soft font-medium text-evidence' : 'text-ink-soft hover:text-ink'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-6">
        {loading ? (
          <div className="animate-pulse space-y-3">
            {[0, 1].map((i) => (
              <div key={i} className="h-20 rounded-xl border border-hairline bg-panel" />
            ))}
          </div>
        ) : sources.length === 0 ? (
          <EmptyState
            title={search || filter !== 'all' ? 'No matching sources' : 'No sources recorded'}
            description={
              search || filter !== 'all'
                ? 'Try clearing the search or choosing a different type.'
                : 'Live web citations were unavailable during recent research, and no documents have grounded reports. Upload documents or retry research when the search provider is available.'
            }
            icon={Library}
          />
        ) : (
          <div className="space-y-3">
            {sources.map((s) => (
              <div key={s.id}>
                <p className="mb-1.5 pl-1 text-[0.72rem] uppercase tracking-wide text-ink-soft">
                  {s.reportQuery}
                </p>
                <SourceCard source={s} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}