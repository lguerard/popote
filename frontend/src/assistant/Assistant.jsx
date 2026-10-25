import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth'
import Markdown from './Markdown'
import { streamChat } from './stream'
import { loadConversation, saveConversation } from './storage'

// Assistant culinaire : bouton flottant sur toutes les pages, panneau de
// discussion (plein écran sur téléphone, carte en bas à droite ailleurs).
// La conversation est tenue ici et renvoyée à chaque question ; le serveur
// diffuse la réponse mot à mot (voir backend/app/services/assistant.py).

const MAX_CHARS = 4000
const AssistantContext = createContext(null)

export function useAssistant() {
  return useContext(AssistantContext)
}

let nextId = 0
const newId = () => `${Date.now()}-${nextId++}`

export function AssistantProvider({ children }) {
  const [open, setOpen] = useState(false)
  // Recette ouverte quand l'assistant a été appelé depuis sa fiche.
  const [recipe, setRecipe] = useState(null)
  const [draft, setDraft] = useState('')

  const ouvrir = useCallback(({ recipe: r } = {}) => {
    if (r) setRecipe({ id: r.id, title: r.title })
    setOpen(true)
  }, [])

  return (
    <AssistantContext.Provider value={{ open, setOpen, ouvrir, recipe, setRecipe, draft, setDraft }}>
      {children}
      <AssistantPanel />
    </AssistantContext.Provider>
  )
}

/** Bouton « Demander à l'assistant » d'une fiche recette. */
export function BoutonAssistant({ recipe, className = '' }) {
  const { ouvrir } = useAssistant()
  return (
    <button onClick={() => ouvrir({ recipe })} title="Poser une question sur cette recette"
      className={`px-3 py-2 text-sm bg-orange-50 text-orange-700 hover:bg-orange-100 rounded-lg transition-colors ${className}`}>
      💬 Demander à l'assistant
    </button>
  )
}

function suggestions(recipe) {
  const list = [
    { label: "Qu'est-ce que je peux cuisiner avec… ?", fill: "Qu'est-ce que je peux cuisiner avec " },
    { label: 'Planifie mes dîners de la semaine', send: 'Planifie mes dîners de la semaine avec mes recettes.' },
    { label: 'Que reste-t-il sur ma liste de courses ?', send: 'Que reste-t-il sur ma liste de courses ?' },
  ]
  if (recipe) {
    list.unshift(
      { label: 'Adapte cette recette pour 6', send: 'Adapte cette recette pour 6 personnes.' },
      { label: 'Ajoute ses ingrédients aux courses', send: 'Ajoute les ingrédients de cette recette à ma liste de courses.' },
    )
  }
  return list
}

function AssistantPanel() {
  const { open, setOpen, recipe, setRecipe, draft, setDraft } = useAssistant()
  const { user, token } = useAuth()
  const { pathname } = useLocation()
  const qc = useQueryClient()
  const [messages, setMessages] = useState(() => loadConversation(user?.id))
  const [busy, setBusy] = useState(false)
  const abortRef = useRef(null)
  const listRef = useRef(null)
  const inputRef = useRef(null)
  const stickRef = useRef(true)

  // Autre compte sur le même appareil : sa propre conversation.
  useEffect(() => { setMessages(loadConversation(user?.id)) }, [user?.id])
  useEffect(() => { saveConversation(user?.id, messages) }, [user?.id, messages])
  useEffect(() => () => abortRef.current?.abort(), [])

  // Défilement automatique, sauf si l'utilisateur est remonté lire.
  useEffect(() => {
    const el = listRef.current
    if (el && stickRef.current) el.scrollTop = el.scrollHeight
  }, [messages, open])
  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 50) }, [open])

  const update = (id, fn) => setMessages(ms => ms.map(m => (m.id === id ? fn(m) : m)))

  async function send(text) {
    const question = text.trim()
    if (!question || busy) return
    const history = [...messages.filter(m => m.content && !m.pending), { role: 'user', content: question }]
    const userMsg = { id: newId(), role: 'user', content: question }
    const reply = { id: newId(), role: 'assistant', content: '', pending: true, status: 'Je réfléchis…', actions: [], recipes: [] }
    setMessages(ms => [...ms, userMsg, reply])
    setDraft('')
    setBusy(true)
    stickRef.current = true
    const controller = new AbortController()
    abortRef.current = controller
    try {
      await streamChat({
        token,
        signal: controller.signal,
        messages: history.map(({ role, content }) => ({ role, content })),
        context: { recipe_id: recipe?.id || null, page: pathname },
        onEvent: (ev) => {
          if (ev.type === 'delta') update(reply.id, m => ({ ...m, content: m.content + ev.text, status: null }))
          else if (ev.type === 'status') update(reply.id, m => ({ ...m, status: ev.text }))
          else if (ev.type === 'action') {
            update(reply.id, m => ({ ...m, actions: [...m.actions, { kind: ev.kind, label: ev.label }] }))
            qc.invalidateQueries({ queryKey: ev.kind === 'planning' ? ['meal-plans'] : ['shopping-items'] })
          } else if (ev.type === 'recipes') {
            update(reply.id, m => {
              const seen = new Set(m.recipes.map(r => r.id))
              return { ...m, recipes: [...m.recipes, ...ev.recipes.filter(r => !seen.has(r.id))].slice(0, 8) }
            })
          } else if (ev.type === 'error') update(reply.id, m => ({ ...m, error: ev.message }))
        },
      })
    } catch (e) {
      if (e?.name === 'AbortError') update(reply.id, m => ({ ...m, stopped: true }))
      else update(reply.id, m => ({ ...m, error: e.message || 'Erreur inattendue.' }))
    } finally {
      update(reply.id, m => ({ ...m, pending: false, status: null }))
      abortRef.current = null
      setBusy(false)
    }
  }

  function stop() { abortRef.current?.abort() }

  // La recette en contexte reste (✕ pour l'enlever) : on repart de zéro
  // sur la même fiche.
  function reset() {
    stop()
    setMessages([])
    setDraft('')
  }

  function choisir(s) {
    if (s.send) send(s.send)
    else { setDraft(s.fill); setTimeout(() => inputRef.current?.focus(), 0) }
  }

  // Lien vers une recette sur téléphone : on referme pour la montrer.
  const closeOnPhone = () => { if (window.matchMedia('(max-width: 639px)').matches) setOpen(false) }

  if (!user) return null
  // Mode cuisine : plein écran, pas de bouton par-dessus.
  const hidden = /\/cuisine$/.test(pathname)

  if (!open) {
    if (hidden) return null
    return (
      <button onClick={() => setOpen(true)} title="Assistant culinaire"
        style={{ bottom: 'calc(1rem + env(safe-area-inset-bottom))' }}
        className="print:hidden fixed right-4 z-40 flex items-center gap-2 h-14 pl-4 pr-5 rounded-full bg-orange-600 text-white shadow-lg hover:bg-orange-700 active:scale-95 transition">
        <span className="text-xl">💬</span>
        <span className="hidden sm:inline font-medium">Assistant</span>
      </button>
    )
  }

  return (
    <div role="dialog" aria-label="Assistant culinaire"
      className="print:hidden fixed z-50 inset-0 sm:inset-auto sm:right-4 sm:bottom-4 sm:w-[26rem] sm:h-[min(42rem,calc(100vh-6rem))] flex flex-col bg-white sm:rounded-2xl shadow-2xl sm:border border-orange-100 overflow-hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)', paddingTop: 'env(safe-area-inset-top)' }}>
      <header className="flex items-center gap-2 px-4 h-14 border-b border-orange-100 bg-orange-50/60 flex-shrink-0">
        <span className="text-xl">🧑‍🍳</span>
        <h2 className="font-semibold text-gray-900 flex-1">Assistant</h2>
        <button onClick={reset} disabled={!messages.length}
          className="px-2.5 py-1.5 text-xs font-medium rounded-lg text-gray-600 hover:bg-orange-100 disabled:opacity-40">
          Nouvelle conversation
        </button>
        <button onClick={() => setOpen(false)} title="Fermer"
          className="w-9 h-9 flex items-center justify-center rounded-lg text-gray-500 hover:bg-orange-100 text-lg">✕</button>
      </header>

      {recipe && (
        <div className="px-4 py-2 border-b border-orange-50 flex items-center gap-2 text-xs flex-shrink-0">
          <span className="text-gray-500">À propos de</span>
          <Link to={`/recettes/${recipe.id}`} onClick={closeOnPhone}
            className="flex-1 truncate font-medium text-orange-700 hover:underline">📖 {recipe.title}</Link>
          <button onClick={() => setRecipe(null)} title="Ne plus parler de cette recette"
            className="text-gray-400 hover:text-gray-600 px-1">✕</button>
        </div>
      )}

      <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4"
        onScroll={(e) => {
          const el = e.currentTarget
          stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
        }}>
        {!messages.length && (
          <div className="text-sm text-gray-600 space-y-4">
            <p>
              Bonjour {user.display_name} ! Je connais tes recettes, ton planning et ta liste de courses.
              Je peux chercher, adapter des quantités, planifier des repas et compléter tes courses.
            </p>
            <div className="flex flex-col items-start gap-2">
              {suggestions(recipe).map(s => (
                <button key={s.label} onClick={() => choisir(s)}
                  className="text-left px-3 py-2 rounded-xl border border-orange-200 bg-orange-50/50 text-orange-800 hover:bg-orange-100 transition-colors">
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map(m => (m.role === 'user' ? (
          <div key={m.id} className="flex justify-end">
            <div className="max-w-[85%] px-3.5 py-2 rounded-2xl rounded-br-md bg-orange-600 text-white text-sm whitespace-pre-wrap break-words">
              {m.content}
            </div>
          </div>
        ) : (
          <Reponse key={m.id} message={m} onRecipe={closeOnPhone} />
        )))}
      </div>

      <form className="border-t border-orange-100 p-3 flex items-end gap-2 flex-shrink-0 bg-white"
        onSubmit={(e) => { e.preventDefault(); send(draft) }}>
        <div className="flex-1">
          <textarea ref={inputRef} value={draft} rows={1} maxLength={MAX_CHARS}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(draft) }
            }}
            placeholder={recipe ? 'Une question sur cette recette ?' : 'Pose ta question…'}
            className="w-full resize-none max-h-32 px-3 py-2.5 rounded-xl border border-gray-200 focus:border-orange-400 focus:ring-2 focus:ring-orange-100 outline-none text-[16px] sm:text-sm"
            style={{ fieldSizing: 'content' }} />
          {draft.length > MAX_CHARS - 500 && (
            <p className="text-[11px] text-gray-400 text-right">{draft.length}/{MAX_CHARS}</p>
          )}
        </div>
        {busy ? (
          <button type="button" onClick={stop} title="Arrêter la réponse"
            className="h-11 px-4 rounded-xl bg-gray-800 text-white text-sm font-medium hover:bg-gray-900 flex-shrink-0">
            ■ Stop
          </button>
        ) : (
          <button type="submit" disabled={!draft.trim()} title="Envoyer"
            className="h-11 px-4 rounded-xl bg-orange-600 text-white text-sm font-medium hover:bg-orange-700 disabled:opacity-40 flex-shrink-0">
            Envoyer
          </button>
        )}
      </form>
    </div>
  )
}

function Reponse({ message: m, onRecipe }) {
  return (
    <div className="flex flex-col items-start gap-2 max-w-[92%]">
      {(m.content || (!m.pending && !m.error && !m.stopped)) && (
        <div className="px-3.5 py-2.5 rounded-2xl rounded-bl-md bg-gray-50 border border-gray-100 text-sm text-gray-800">
          <Markdown text={m.content || '…'} onRecipe={onRecipe} />
        </div>
      )}
      {m.pending && m.status && (
        <p className="text-xs text-gray-500 flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-orange-400 animate-pulse" />{m.status}
        </p>
      )}
      {m.actions?.map((a, i) => (
        <span key={i} className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
          a.kind === 'planning' ? 'bg-sky-50 text-sky-700 border-sky-200' : 'bg-green-50 text-green-700 border-green-200'
        }`}>
          {a.kind === 'planning' ? '📅' : '🛒'} {a.label}
          <Link to={a.kind === 'planning' ? '/planning' : '/courses'} onClick={onRecipe} className="underline ml-1">Voir</Link>
        </span>
      ))}
      {m.recipes?.length > 0 && (
        <div className="w-full">
          <p className="text-[11px] uppercase tracking-wide text-gray-400 mb-1">Recettes trouvées</p>
          <div className="flex gap-2 overflow-x-auto scrollbar-hide pb-1 -mx-1 px-1">
            {m.recipes.map(r => (
              <Link key={r.id} to={`/recettes/${r.id}`} onClick={onRecipe}
                className="flex-shrink-0 w-36 bg-white rounded-xl border border-gray-100 shadow-sm hover:shadow overflow-hidden">
                <div className="h-20 bg-orange-50 flex items-center justify-center text-2xl overflow-hidden">
                  {r.thumbnail_url ? <img src={r.thumbnail_url} alt="" className="w-full h-full object-cover" /> : '🍽️'}
                </div>
                <div className="p-2">
                  <p className="text-xs font-medium text-gray-800 line-clamp-2">{r.title}</p>
                  {r.minutes && <p className="text-[11px] text-gray-400 mt-0.5">⏱ {r.minutes} min</p>}
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
      {m.stopped && <p className="text-xs text-gray-400">Réponse arrêtée.</p>}
      {m.error && (
        <p className="text-xs text-red-700 bg-red-50 border border-red-100 rounded-lg px-3 py-2">{m.error}</p>
      )}
    </div>
  )
}
