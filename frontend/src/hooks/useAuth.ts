import { useCallback, useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import * as api from '../api'
import { jwtSubject } from '../lib/format'

export interface Auth {
  token: string | null
  username: string | null
  signIn: (username: string, password: string) => Promise<void>
  signUp: (username: string, password: string) => Promise<void>
  signOut: () => void
}

export function useAuth(): Auth {
  const [token, setTokenState] = useState<string | null>(() => api.getStoredToken())

  const signOut = useCallback(() => {
    api.setToken(null)
    setTokenState(null)
  }, [])

  // A 401 on an authenticated request means the token expired or is invalid.
  useEffect(() => {
    api.setUnauthorizedHandler(() => {
      signOut()
      toast.error('Your session ended. Sign in again.', { id: 'session-ended' })
    })
    return () => api.setUnauthorizedHandler(null)
  }, [signOut])

  const signIn = useCallback(async (username: string, password: string) => {
    const t = await api.login(username, password)
    api.setToken(t)
    setTokenState(t)
  }, [])

  const signUp = useCallback(
    async (username: string, password: string) => {
      await api.register(username, password)
      await signIn(username, password)
    },
    [signIn],
  )

  const username = useMemo(() => (token ? jwtSubject(token) : null), [token])

  return { token, username, signIn, signUp, signOut }
}
