import { Inbox } from 'lucide-react'

export default function EmptyState({ title = 'No data yet', description, icon: Icon = Inbox }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 border border-dashed border-hairline bg-panel px-6 py-12 text-center">
      <Icon size={22} strokeWidth={1.5} className="text-ink-soft" />
      <p className="text-[0.925rem] font-medium text-ink">{title}</p>
      {description && <p className="mx-auto max-w-sm text-[0.825rem] text-ink-soft">{description}</p>}
    </div>
  )
}