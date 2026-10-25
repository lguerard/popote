// Client du flux NDJSON de POST /api/assistant/chat : une ligne JSON par
// événement (status, delta, recipes, action, error, done).
// fetch() + ReadableStream plutôt qu'EventSource : il faut un POST avec
// l'en-tête Authorization, ce qu'EventSource ne sait pas faire.

const MESSAGES = {
  401: 'Session expirée : reconnecte-toi.',
  409: 'Une réponse est déjà en cours : attends-la ou arrête-la.',
  413: 'Message trop long : raccourcis ta question.',
}

export async function streamChat({ token, messages, context, signal, onEvent }) {
  let res
  try {
    res = await fetch('/api/assistant/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ messages, context }),
      signal,
    })
  } catch (e) {
    if (e?.name === 'AbortError') throw e
    throw new Error('Serveur injoignable : vérifie ta connexion.')
  }
  if (!res.ok) {
    let detail = null
    try { detail = (await res.json()).detail } catch { /* corps vide */ }
    throw new Error(typeof detail === 'string' ? detail : (MESSAGES[res.status] || `Erreur ${res.status}`))
  }

  const emit = (line) => {
    const text = line.trim()
    if (!text) return
    try { onEvent(JSON.parse(text)) } catch { /* ligne illisible ignorée */ }
  }

  // Très vieilles WebView : pas de flux lisible, tout arrive à la fin.
  if (!res.body?.getReader) {
    (await res.text()).split('\n').forEach(emit)
    return
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let cut
    while ((cut = buffer.indexOf('\n')) >= 0) {
      emit(buffer.slice(0, cut))
      buffer = buffer.slice(cut + 1)
    }
  }
  emit(buffer + decoder.decode())
}
