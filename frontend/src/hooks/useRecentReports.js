import { useEffect, useState } from 'react'
import { researchApi } from '../services/api'

/*
 * Loads recent research cards and, optionally, the full reports for completed
 * ones. `details` preserves the ordered completed reports only.
 */
export default function useRecentReports({ limit = 20, includeResults = false } = {}) {
  const [cards, setCards] = useState(null)
  const [details, setDetails] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    researchApi
      .recent(limit)
      .then(async (recent) => {
        if (cancelled) return
        setCards(recent)
        if (includeResults) {
          const completed = recent.filter((r) => r.status === 'completed')
          const settled = await Promise.allSettled(completed.map((r) => researchApi.get(r.id)))
          if (cancelled) return
          setDetails(settled.filter((x) => x.status === 'fulfilled').map((x) => x.value))
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || 'Could not load research history.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [limit, includeResults])

  return { cards, details, error, loading }
}