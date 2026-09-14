import { useEffect, useState } from 'react'
import { researchApi } from '../services/api'

/*
 * Server-side paginated research history. Loads the first page on mount and
 * appends subsequent pages via offset with a Load-more button. `hasMore` is a
 * heuristic: a full page suggests more rows may exist.
 */
export default function useResearchHistory({ pageSize = 25 } = {}) {
  const [cards, setCards] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState(null)
  const [hasMore, setHasMore] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    researchApi
      .history({ limit: pageSize, offset: 0 })
      .then((page) => {
        if (cancelled) return
        setCards(page)
        setHasMore(page.length === pageSize)
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
  }, [pageSize])

  async function loadMore() {
    if (loadingMore || !cards) return
    setLoadingMore(true)
    try {
      const page = await researchApi.history({ limit: pageSize, offset: cards.length })
      setCards((prev) => [...(prev ?? []), ...page])
      setHasMore(page.length === pageSize)
    } catch (err) {
      setError(err?.message || 'Could not load more research.')
    } finally {
      setLoadingMore(false)
    }
  }

  return { cards, error, loading, loadingMore, hasMore, loadMore }
}