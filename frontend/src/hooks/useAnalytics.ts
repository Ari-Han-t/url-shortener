import { useEffect, useState } from 'react'
import { getAnalytics, type AnalyticsData } from '../api'

interface AnalyticsState {
  data: AnalyticsData | null
  error: string | null
  loading: boolean
}

export function useAnalytics(shortId: string | null): AnalyticsState {
  const [state, setState] = useState<AnalyticsState & { forId: string | null }>({
    data: null,
    error: null,
    loading: false,
    forId: null,
  })

  useEffect(() => {
    if (!shortId) return
    let cancelled = false
    getAnalytics(shortId)
      .then((data) => {
        if (!cancelled) setState({ data, error: null, loading: false, forId: shortId })
      })
      .catch((e: unknown) => {
        if (cancelled) return
        const error = e instanceof Error ? e.message : 'Could not load analytics.'
        setState({ data: null, error, loading: false, forId: shortId })
      })
    return () => {
      cancelled = true
    }
  }, [shortId])

  if (!shortId) return { data: null, error: null, loading: false }
  // Until the response for this id arrives, report loading.
  if (state.forId !== shortId) return { data: null, error: null, loading: true }
  return state
}
