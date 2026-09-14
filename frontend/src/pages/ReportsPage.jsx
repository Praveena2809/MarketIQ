import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, FileBarChart } from 'lucide-react'
import useResearchHistory from '../hooks/useResearchHistory'
import { RESEARCH_TYPES, typeLabel, formatDate } from '../lib/format'
import StatusBadge from '../components/StatusBadge'
import EmptyState from '../components/EmptyState'
import InlineError from '../components/InlineError'

const sortOptions = [
  { value: 'newest', label: 'Newest first' },
  { value: 'oldest', label: 'Oldest first' },
  { value: 'az', label: 'A–Z' },
]

const statusFilters = [
  { value: 'all', label: 'All' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]

const typeFilters = [{ value: 'all', label: 'All' }, ...RESEARCH_TYPES]

export default function ReportsPage() {
  const navigate = useNavigate()
  const { cards, error, loading, loadingMore, hasMore, loadMore } = useResearchHistory({ pageSize: 25 })
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('newest')
  const [statusFilter, setStatusFilter] = useState('all')
  const [typeFilter, setTypeFilter] = useState('all')

  const filtered = useMemo(() => {
    if (!cards) return []
    const q = search.trim().toLowerCase()
    return cards
      .filter((r) => (statusFilter === 'all' ? true : r.status === statusFilter))
      .filter((r) => (typeFilter === 'all' ? true : r.research_type === typeFilter))
      .filter((r) => !q || r.query.toLowerCase().includes(q))
      .sort((a, b) => {
        if (sort === 'az') return a.query.localeCompare(b.query)
        if (sort === 'oldest') return new Date(a.updated_at) - new Date(b.updated_at)
        return new Date(b.updated_at) - new Date(a.updated_at)
      })
  }, [cards, search, sort, statusFilter, typeFilter])

  return (
    <div className="mx-auto max-w-4xl px-6 py-10 lg:px-10">
      <h2 className="font-serif text-2xl text-ink">Research History</h2>
      <p className="mt-1 text-[0.9rem] text-ink-soft">
        Every research run, stored with its full synthesis and sources.
      </p>

      {error && (
        <InlineError className="mt-6">{error}</InlineError>
      )}

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 rounded-lg border border-hairline bg-panel px-3 py-2 focus-within:border-evidence sm:w-80">
          <Search size={15} strokeWidth={2} className="shrink-0 text-ink-soft" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search reports…"
            aria-label="Search reports"
            className="w-full bg-transparent text-[0.875rem] text-ink placeholder:text-ink-soft focus:outline-none"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-hairline bg-panel p-0.5">
            {statusFilters.map((f) => (
              <button
                key={f.value}
                aria-pressed={statusFilter === f.value}
                onClick={() => setStatusFilter(f.value)}
                className={`rounded-md px-3 py-1.5 text-[0.78rem] transition-colors ${
                  statusFilter === f.value ? 'bg-evidence-soft font-medium text-evidence' : 'text-ink-soft hover:text-ink'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="rounded-lg border border-hairline bg-panel px-3 py-2 text-[0.82rem] text-ink focus:border-evidence focus:outline-none"
          >
            {sortOptions.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {typeFilters.map((t) => (
          <button
            key={t.value}
            aria-pressed={typeFilter === t.value}
            onClick={() => setTypeFilter(t.value)}
            className={`rounded-full border px-3 py-1 text-[0.78rem] transition-colors ${
              typeFilter === t.value
                ? 'border-evidence bg-evidence-soft font-medium text-evidence'
                : 'border-hairline bg-panel text-ink-soft hover:text-ink'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="mt-6 space-y-3">
        {loading && (
          <div className="animate-pulse space-y-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-16 rounded-lg border border-hairline bg-panel" />
            ))}
          </div>
        )}
        {!loading && !error && filtered.length === 0 && (
          <EmptyState
            title={search || statusFilter !== 'all' || typeFilter !== 'all' ? 'No matching reports' : 'No reports yet'}
            description={
              search || statusFilter !== 'all' || typeFilter !== 'all'
                ? 'Try a different search or filter.'
                : 'Run a research from the dashboard and it will be saved here.'
            }
            icon={FileBarChart}
          />
        )}
        {filtered.map((r) => (
          <button
            key={r.id}
            onClick={() => navigate(`/research/${r.id}`)}
            className="flex w-full flex-col gap-2 rounded-xl border border-hairline bg-panel px-5 py-4 text-left shadow-sm transition-colors hover:border-ink-soft"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <p className="font-serif text-[1.05rem] leading-snug text-ink">{r.query}</p>
              <StatusBadge status={r.status} />
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.78rem] text-ink-soft">
              <span className="rounded-full border border-hairline bg-paper px-2 py-0.5">
                {typeLabel(r.research_type)}
              </span>
              <span>Generated {formatDate(r.updated_at)}</span>
            </div>
          </button>
        ))}
        {hasMore && !error && !loading && (
          <button
            onClick={loadMore}
            disabled={loadingMore}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-hairline bg-panel px-4 py-3 text-[0.85rem] font-medium text-ink-soft transition-colors hover:border-evidence hover:text-evidence disabled:opacity-60"
          >
            {loadingMore ? 'Loading more…' : 'Load more'}
          </button>
        )}
      </div>
    </div>
  )
}