import { useEffect, useState } from 'react'
import { FileBarChart, Library, Building2, TrendingUp, Search } from 'lucide-react'
import { getStats, getRecentResearch } from '../services/api'
import StatPanel from '../components/StatPanel'
import ResearchInput from '../components/ResearchInput'
import { RecentResearchCard, RecentResearchEmpty } from '../components/RecentResearchCard'

const statItems = [
  { label: 'Researches completed', key: 'researches_completed', icon: FileBarChart },
  { label: 'Sources analyzed', key: 'sources_analyzed', icon: Library },
  { label: 'Companies analyzed', key: 'companies_analyzed', icon: Building2 },
  { label: 'Trends detected', key: 'trends_detected', icon: TrendingUp },
]

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

  return (
    <div className="mx-auto max-w-4xl px-6 py-12 lg:px-10">
      <section className="text-center">
        <p className="font-serif text-3xl leading-tight text-ink">
          Market intelligence,
          <br />
          <span className="italic text-evidence">powered by AI.</span>
        </p>
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
        <p className="mt-8 rounded-lg border border-negative-soft bg-negative-soft px-4 py-3 text-[0.875rem] text-negative">
          {error}
        </p>
      )}

      <section className="mt-12">
        <h2 className="text-[0.8rem] font-medium uppercase tracking-wider text-ink-soft">Quick statistics</h2>
        <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {statItems.map(({ label, key, icon }) => (
            <StatPanel key={key} label={label} value={stats ? stats[key] : '—'} icon={icon} />
          ))}
        </div>
      </section>

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