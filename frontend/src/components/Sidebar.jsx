import { NavLink } from 'react-router-dom'
import { X, LayoutDashboard, SearchCode, FileBarChart, Building2, TrendingUp, Smile, Library, Settings } from 'lucide-react'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/research/new', label: 'New Research', icon: SearchCode },
  { to: '/reports', label: 'History', icon: FileBarChart },
  { to: '/competitors', label: 'Competitors', icon: Building2 },
  { to: '/trends', label: 'Trends', icon: TrendingUp },
  { to: '/sentiment', label: 'Sentiment', icon: Smile },
  { to: '/sources', label: 'Sources', icon: Library },
]

function linkClasses({ isActive }) {
  return [
    'flex items-center gap-3 rounded-md px-3 py-2 text-[0.925rem] transition-colors',
    isActive ? 'bg-evidence-soft text-evidence font-medium' : 'text-ink-soft hover:bg-paper hover:text-ink',
  ].join(' ')
}

function SidebarContent({ onNavigate }) {
  return (
    <>
      <div className="flex items-center justify-between px-6 pt-7 pb-6">
        <span className="font-serif text-[1.35rem] italic text-ink">MarketIQ</span>
        <button onClick={onNavigate} className="rounded p-1 text-ink-soft lg:hidden" aria-label="Close navigation">
          <X size={18} strokeWidth={2} />
        </button>
      </div>

      <nav className="flex-1 space-y-0.5 px-3">
        {navItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} onClick={onNavigate} className={linkClasses}>
            <Icon size={17} strokeWidth={1.75} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-hairline px-3 py-3">
        <NavLink to="/settings" onClick={onNavigate} className={linkClasses}>
          <Settings size={17} strokeWidth={1.75} />
          Settings
        </NavLink>
      </div>
    </>
  )
}

/*
 * Fixed desktop sidebar, and a slide-over drawer on small screens.
 * `open` is only relevant on mobile; on desktop the aside is always visible.
 */
export default function Sidebar({ open = false, onClose = () => {} }) {
  return (
    <>
      {/* Mobile drawer */}
      <div
        className={`fixed inset-0 z-40 bg-black/30 transition-opacity lg:hidden ${
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
        onClick={onClose}
        aria-hidden="true"
      />

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 shrink-0 flex-col border-r border-hairline bg-panel transition-transform lg:static lg:z-auto lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <SidebarContent onNavigate={onClose} />
      </aside>
    </>
  )
}