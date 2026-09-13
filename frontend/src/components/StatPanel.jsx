export default function StatPanel({ label, value, icon: Icon }) {
  return (
    <div className="border border-hairline bg-panel px-5 py-4">
      <div className="flex items-start justify-between">
        <span className="text-[0.8rem] text-ink-soft">{label}</span>
        {Icon && <Icon size={16} strokeWidth={1.75} className="text-ink-soft" />}
      </div>
      <div className="mt-2 font-mono text-2xl text-ink">{value}</div>
    </div>
  )
}
