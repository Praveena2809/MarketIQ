import { Clock, Loader2, CheckCircle2, XCircle } from 'lucide-react'

const STATUS_META = {
  pending: { cls: 'bg-paper text-ink-soft', label: 'Pending', icon: Clock },
  running: { cls: 'bg-signal-soft text-signal', label: 'Running', icon: Loader2 },
  completed: { cls: 'bg-evidence-soft text-evidence', label: 'Completed', icon: CheckCircle2 },
  failed: { cls: 'bg-negative-soft text-negative', label: 'Failed', icon: XCircle },
}

export default function StatusBadge({ status }) {
  const meta = STATUS_META[status] || STATUS_META.pending
  const Icon = meta.icon
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[0.72rem] font-medium uppercase tracking-wide ${meta.cls}`}>
      <Icon size={12} strokeWidth={2} className={status === 'running' ? 'animate-spin' : undefined} />
      {meta.label}
    </span>
  )
}