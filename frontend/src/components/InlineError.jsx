/*
 * Shared inline error banner (Step 13). Replaces the repeated inline copies
 * of the same negative-styled paragraph so error presentation stays
 * consistent across every page.
 */
export default function InlineError({ children, className = '' }) {
  return (
    <div className={`rounded-lg border border-negative-soft bg-negative-soft px-4 py-3 text-[0.875rem] text-negative ${className}`}>
      {children}
    </div>
  )
}