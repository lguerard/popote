import { createContext, useContext, useEffect, useState } from 'react'
import { api, setAuthToken } from './api'

const CLE = 'popote.token'
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  // Le jeton est lu une seule fois au montage : il vit dans localStorage
  // pour survivre au rechargement de la page.
  const [token, setToken] = useState(() => {
    try { return localStorage.getItem(CLE) } catch { return null }
  })
  const [user, setUser] = useState(null)
  // "chargement" tant qu'on n'a pas tranché : sans lui, l'écran de
  // connexion clignote à chaque rechargement avant que /me réponde.
  const [chargement, setChargement] = useState(Boolean(token))

  useEffect(() => {
    setAuthToken(token)
    if (!token) { setUser(null); setChargement(false); return }
    let annule = false
    api.get('/auth/me')
      .then(r => { if (!annule) setUser(r.data) })
      .catch(() => { if (!annule) deconnexion() })
      .finally(() => { if (!annule) setChargement(false) })
    return () => { annule = true }
  }, [token])

  function memoriser(reponse) {
    try { localStorage.setItem(CLE, reponse.access_token) } catch { /* mode privé */ }
    setUser(reponse.user)
    setToken(reponse.access_token)
  }

  function deconnexion() {
    try { localStorage.removeItem(CLE) } catch { /* mode privé */ }
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, token, chargement, memoriser, deconnexion }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth doit être utilisé dans un AuthProvider')
  return ctx
}
