// Conversation de l'assistant gardée dans le navigateur, une par compte
// (rien côté serveur). localStorage peut être indisponible (navigation
// privée, stockage plein) : chaque accès est protégé, l'assistant marche
// alors sans mémoire.

const PREFIX = 'popote.assistant.'
const MAX_KEPT = 40

export function loadConversation(userId) {
  if (!userId) return []
  try {
    const data = JSON.parse(localStorage.getItem(PREFIX + userId) || '[]')
    return Array.isArray(data) ? data.filter(m => m && typeof m.content === 'string') : []
  } catch {
    return []
  }
}

export function saveConversation(userId, messages) {
  if (!userId) return
  try {
    // Jamais un message en cours : il serait figé à moitié au rechargement.
    const kept = messages.filter(m => !m.pending).slice(-MAX_KEPT)
    localStorage.setItem(PREFIX + userId, JSON.stringify(kept))
  } catch { /* stockage indisponible ou plein */ }
}

// À la déconnexion : les conversations de tous les comptes de cet appareil.
export function clearConversations() {
  try {
    const keys = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key?.startsWith(PREFIX)) keys.push(key)
    }
    keys.forEach(k => localStorage.removeItem(k))
  } catch { /* stockage indisponible */ }
}
