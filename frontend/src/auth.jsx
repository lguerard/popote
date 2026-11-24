import { createContext, useContext, useEffect, useState } from 'react'
import { api, setAuthToken, updateLanguage } from './api'
import { translate } from './i18n'
import { clearConversations } from './assistant/storage'

const CLE = 'popote.token'
// Langue choisie avant connexion (pas encore de compte où la ranger).
const CLE_LANGUE = 'popote.lang'

function langueNavigateur() {
  try {
    const langues = navigator.languages?.length ? navigator.languages : [navigator.language]
    return String(langues[0] || '').toLowerCase().startsWith('en') ? 'en' : 'fr'
  } catch {
    return 'fr'
  }
}
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  // Le jeton est lu une seule fois au montage : il vit dans localStorage
  // pour survivre au rechargement de la page.
  const [token, setToken] = useState(() => {
    try { return localStorage.getItem(CLE) } catch { return null }
  })
  const [user, setUser] = useState(null)
  const [langueInvite, setLangueInvite] = useState(() => {
    try {
      const memo = localStorage.getItem(CLE_LANGUE)
      if (memo === 'fr' || memo === 'en') return memo
    } catch { /* mode privé */ }
    return langueNavigateur()
  })
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
    // Conversations de l'assistant : elles citent recettes, planning et
    // courses du compte, à ne pas laisser au suivant sur cet appareil.
    clearConversations()
    setToken(null)
    setUser(null)
  }

  async function changerLangue(langue) {
    const maj = await updateLanguage(langue)
    setUser(u => (u ? { ...u, language: maj.language } : u))
  }

  // Écran de connexion : choix local uniquement, aucun appel API.
  function choisirLangueInvite(langue) {
    try { localStorage.setItem(CLE_LANGUE, langue) } catch { /* mode privé */ }
    setLangueInvite(langue)
  }

  // Connecté, la langue du compte fait foi ; avant, celle du navigateur
  // ou celle choisie sur l'écran de connexion.
  const lang = user ? (user.language || 'fr') : langueInvite
  const t = (key, vars) => translate(lang, key, vars)

  return (
    <AuthContext.Provider value={{ user, token, chargement, memoriser, deconnexion, lang, t, changerLangue, choisirLangueInvite }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth doit être utilisé dans un AuthProvider')
  return ctx
}
