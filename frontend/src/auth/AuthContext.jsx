import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { getAuthStatus, login as apiLogin, logout as apiLogout, setUnauthorizedHandler } from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // needsSetup : aucun compte n'existe encore, on propose la création du premier.
  const [needsSetup, setNeedsSetup] = useState(false)
  const [loading, setLoading] = useState(true)
  const [unreachable, setUnreachable] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const status = await getAuthStatus()
      setNeedsSetup(status.needs_setup)
      setUser(status.user ?? null)
      setUnreachable(false)
    } catch {
      // /auth/status ne demande pas de session : un échec ici est un vrai
      // problème réseau, pas une déconnexion.
      setUnreachable(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  // Toute réponse 401 d'une autre requête signifie que la session est tombée.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
    return () => setUnauthorizedHandler(() => {})
  }, [])

  const signIn = useCallback(async (email, password) => {
    const { user: signedIn } = await apiLogin(email, password)
    setUser(signedIn)
    setNeedsSetup(false)
    return signedIn
  }, [])

  const signOut = useCallback(async () => {
    try {
      await apiLogout()
    } finally {
      setUser(null)
    }
  }, [])

  const value = { user, needsSetup, loading, unreachable, refresh, signIn, signOut, setUser }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth doit être utilisé dans un <AuthProvider>')
  return ctx
}
