import { useCallback, useEffect, useState } from 'react'
import { getDashboard, type DashboardData } from '../api'

interface LinksState {
  data: DashboardData | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

export function useLinks(): LinksState {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setData(await getDashboard())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load your links.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { data, loading, error, refresh }
}
