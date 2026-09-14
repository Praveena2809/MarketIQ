import { useNavigate } from 'react-router-dom'
import { FileSearch } from 'lucide-react'
import { typeLabel } from '../lib/format'

function timeAgo(isoString) {
  const diffMs = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} hour${hours > 1 ? 's' : ''} ago`
  const days = Math.floor(hours / 24)
  return `${days} day${days > 1 ? 's' : ''} ago`
}

export function RecentResearchCard({ research }) {
  const navigate = useNavigate()
  return (
    <button
      className="w-full border border-hairline bg-panel px-5 py-4 text-left transition-colors hover:border-ink-soft"
      onClick={() => navigate(`/research/${research.id}`)}
    >
      <p className="font-serif text-[1.05rem] text-ink">{research.query}</p>
      <div className="mt-2 flex items-center justify-between text-[0.8rem] text-ink-soft">
        <span>{typeLabel(research.research_type)}</span>
        <span>Updated {timeAgo(research.updated_at)}</span>
      </div>
    </button>
  )
}

export function RecentResearchEmpty() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 border border-dashed border-hairline px-6 py-10 text-center">
      <FileSearch size={22} strokeWidth={1.5} className="text-ink-soft" />
      <p className="text-[0.925rem] text-ink">No research yet</p>
      <p className="text-[0.825rem] text-ink-soft">
        Start your first market, competitor, or trend analysis to see it appear here.
      </p>
    </div>
  )
}
