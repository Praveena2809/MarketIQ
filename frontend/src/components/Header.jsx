import { useLocation } from 'react-router-dom'
import { Menu } from 'lucide-react'

const TITLES = {
  '/': 'Dashboard',
  '/research/new': 'New Research',
  '/reports': 'Research Reports',
  '/competitors': 'Competitor Analysis',
  '/trends': 'Industry Trends',
  '/sentiment': 'Sentiment Insights',
  '/sources': 'Sources',
  '/settings': 'Settings',
}

export default function Header({ onMenuClick }) {
  const { pathname } = useLocation()
  const title = TITLES[pathname] || 'MarketIQ'

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-hairline bg-paper/90 px-6 backdrop-blur">
      <button
        onClick={onMenuClick}
        className="rounded-md p-1.5 text-ink-soft hover:bg-paper lg:hidden"
        aria-label="Open navigation"
      >
        <Menu size={18} strokeWidth={2} />
      </button>
      <h1 className="font-serif text-[1.05rem] font-medium text-ink">{title}</h1>
    </header>
  )
}