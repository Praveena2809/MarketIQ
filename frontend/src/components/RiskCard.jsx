import { ShieldAlert, Shield, AlertTriangle, CheckCircle2 } from 'lucide-react'

const severityStyles = {
  high: { badge: 'bg-negative-soft text-negative', icon: AlertTriangle },
  medium: { badge: 'bg-signal-soft text-signal', icon: ShieldAlert },
  low: { badge: 'bg-paper text-ink-soft', icon: Shield },
}

export default function RiskCard({ risk }) {
  const style = severityStyles[risk.severity] || severityStyles.low
  const SeverityIcon = style.icon
  const severity = risk.severity || 'unrated'

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-hairline bg-panel p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <SeverityIcon size={16} strokeWidth={1.75} className="text-signal" />
          <p className="font-serif text-[0.95rem] font-medium text-ink">{risk.risk}</p>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-[0.72rem] font-medium uppercase tracking-wide ${style.badge}`}>
          {severity}
        </span>
      </div>
      {risk.mitigation && (
        <div className="flex items-start gap-2 rounded-lg bg-evidence-soft px-3 py-2 text-[0.8rem] leading-relaxed text-ink">
          <CheckCircle2 size={14} strokeWidth={2} className="mt-0.5 shrink-0 text-evidence" />
          <span className="text-ink-soft">
            <span className="font-medium text-evidence">Mitigation:</span> {risk.mitigation}
          </span>
        </div>
      )}
    </div>
  )
}