import { useEffect, useMemo, useState } from 'react'
import {
  FileBarChart,
  Library,
  Building2,
  TrendingUp,
  Lightbulb,
  Target,
  ShieldAlert,
  Search,
} from 'lucide-react'
import { getStats, getRecentResearch } from '../services/api'
import { typeLabel } from '../lib/format'
import StatPanel from '../components/StatPanel'
import ResearchInput from '../components/ResearchInput'
import InlineError from '../components/InlineError'
import { RecentResearchCard, RecentResearchEmpty } from '../components/RecentResearchCard'

const statItems = [
  { label: 'Researches completed', key: 'researches_completed', icon: FileBarChart },
  { label: 'Sources analyzed', key: 'sources_analyzed', icon: Library },
  { label: 'Companies analyzed', key: 'companies_analyzed', icon: Building2 },
  { label: 'Trends detected', key: 'trends_detected', icon: TrendingUp },
  { label: 'Insights synthesized', key: 'insights_synthesized', icon: Lightbulb },
  { label: 'Opportunities identified', key: 'opportunities_identified', icon: Target },
  { label: 'Risks identified', key: 'risks_identified', icon: ShieldAlert },
]

function titleCase(value) {
  if (!value) return 'Unknown'
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function MixChips({ title, chips, emptyText }) {
  if (chips.length === 0) {
    return (
      <section>
        <h3 className="text-[0.8rem] font-medium uppercase tracking-wider text-ink-soft">{title}</h3>
        <p className="mt-3 rounded-lg border border-hairline bg-panel px-4 py-3 text-[0.85rem] text-ink-soft">
          {emptyText}
        </p>
      </section>
    )
  }
  return (
    <section>
      <h3 className="text-[0.8rem] font-medium uppercase tracking-wider text-ink-soft">{title}</h3>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {chips.map(({ label, count }) => (
          <span
            key={label}
            className="flex items-baseline gap-1.5 rounded-full border border-hairline bg-panel px-3 py-1 text-[0.78rem] text-ink-soft"
          >
            <span className="font-mono text-[0.9rem] font-medium text-ink">{count}</span>
            {label}
          </span>
        ))}
      </div>
    </section>
  )
}

export default function DashboardPage() {
  const [stats, setStats] = useState(null)
  const [recent, setRecent] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([getStats(), getRecentResearch(6)])
      .then(([statsData, recentData]) => {
        if (cancelled) return
        setStats(statsData)
        setRecent(recentData)
      })
      .catch(() => {
        if (!cancelled) setError('Could not reach the MarketIQ backend. Is the API running on port 8000?')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const chips = useMemo(() => {
    if (!stats) return null
    const byCount = (a, b) => b.count - a.count
    return {
      sentiment: Object.entries(stats.sentiment_counts ?? {})
        .map(([label, count]) => ({ label: titleCase(label), count }))
        .sort(byCount),
      research: Object.entries(stats.research_type_counts ?? {})
        .map(([type, count]) => ({ label: typeLabel(type), count }))
        .sort(byCount),
      source: Object.entries(stats.source_type_counts ?? {})
        .map(([type, count]) => ({ label: titleCase(type), count }))
        .sort(byCount),
    }
  }, [stats])

  return (
    <div className="mx-auto max-w-4xl px-6 py-12 lg:px-10">
      <section className="text-center">
        <h2 className="font-serif text-3xl leading-tight text-ink">
          Market intelligence,
          <br />
          <span className="italic text-evidence">powered by AI.</span>
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-[0.95rem] leading-relaxed text-ink-soft">
          Ask about a market, industry, competitor, or product — MarketIQ grounds its research in
          live sources and your own uploaded documents, then synthesizes an actionable briefing.
        </p>
        <ResearchInput />
        <p className="mt-3 text-[0.8rem] text-ink-soft">
          e.g. “Analyze the electric vehicle market in India for the next 12 months”
        </p>
      </section>

      {error && (
        <InlineError className="mt-8">{error}</InlineError>
      )}

      <section className="mt-12">
        <h2 className="text-[0.8rem] font-medium uppercase tracking-wider text-ink-soft">Quick statistics</h2>
        <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {statItems.map(({ label, key, icon }) => (
            <StatPanel key={key} label={label} value={stats ? stats[key] : '—'} icon={icon} />
          ))}
        </div>
      </section>

      {chips && (
        <section className="mt-10 grid gap-x-10 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
          <MixChips title="Sentiment mix" chips={chips.sentiment} emptyText="No sentiment data yet." />
          <MixChips title="Research mix" chips={chips.research} emptyText="No research types yet." />
          <MixChips title="Source mix" chips={chips.source} emptyText="No sources recorded yet." />
        </section>
      )}

      <section className="mt-12">
        <div className="flex items-center justify-between">
          <h2 className="text-[0.8rem] font-medium uppercase tracking-wider text-ink-soft">Recent research</h2>
          <Search size={15} strokeWidth={1.75} className="text-ink-soft" />
        </div>
        <div className="mt-3 space-y-3">
          {recent === null && !error && (
            <div className="animate-pulse border border-hairline bg-panel px-5 py-4 text-[0.85rem] text-ink-soft">
              Loading recent research…
            </div>
          )}
          {recent !== null && recent.length === 0 && <RecentResearchEmpty />}
          {recent !== null && recent.map((r) => <RecentResearchCard key={r.id} research={r} />)}
        </div>
      </section>
    </div>
  )
}