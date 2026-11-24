import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { submitBatchExtraction, getTasksStatus } from '../api'
import { useAuth } from '../auth'

// Liens d'un texte collé : même détection approximative que le serveur,
// seulement pour annoncer « 12 liens détectés » avant l'envoi.
export const countLinks = (text) =>
  new Set((text || '').match(/(?:https?:\/\/|www\.)[^\s<>"']+|^[a-z0-9-]+(?:\.[a-z0-9-]+)+\/\S*/gim) || []).size

const ETAT = {
  pending: { icone: '⏳', texte: 'importGroupe.state.pending' },
  processing: { icone: '🔄', texte: 'importGroupe.state.processing' },
  done: { icone: '✅', texte: 'importGroupe.state.done' },
  failed: { icone: '⚠️', texte: 'importGroupe.state.failed' },
}

/** Import de plusieurs liens (reels enregistrés, favoris…) avec leur suivi. */
export default function ImportGroupe({ initialText = '' }) {
  const { t } = useAuth()
  const [texte, setTexte] = useState(initialText)
  const [envoi, setEnvoi] = useState(false)
  const [erreur, setErreur] = useState(null)
  const [lot, setLot] = useState(null) // { items, already_saved, ignored }
  const [etats, setEtats] = useState({}) // recipe_id → recette

  const ids = lot?.items.map(i => i.recipe_id) ?? []
  const termines = ids.filter(id => ['done', 'failed'].includes(etats[id]?.status)).length
  const fini = lot && termines === ids.length

  useEffect(() => {
    if (!lot || fini || ids.length === 0) return undefined
    const suivre = async () => {
      try {
        const recettes = await getTasksStatus(ids)
        setEtats(Object.fromEntries(recettes.map(r => [r.id, r])))
      } catch { /* réseau : on réessaie au prochain tour */ }
    }
    suivre()
    const interval = setInterval(suivre, 3000)
    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lot, fini])

  const envoyer = async (e) => {
    e.preventDefault()
    setEnvoi(true); setErreur(null)
    try {
      setLot(await submitBatchExtraction(texte))
    } catch (err) {
      setErreur(err.response?.data?.detail || t('importGroupe.sendError'))
    } finally {
      setEnvoi(false)
    }
  }

  if (lot) {
    const reussies = ids.filter(id => etats[id]?.status === 'done').length
    return (
      <div className="space-y-4">
        <p className="text-sm text-gray-600">
          {fini
            ? t(reussies > 1 ? 'importGroupe.finishedMany' : 'importGroupe.finishedOne', { n: reussies, total: ids.length })
            : t('importGroupe.progress', { done: termines, total: ids.length })}
        </p>
        {ids.length > 0 && (
          <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
            <div className="h-full bg-orange-500 transition-all" style={{ width: `${(termines / ids.length) * 100}%` }} />
          </div>
        )}
        <ul className="bg-white rounded-xl border border-gray-100 divide-y divide-gray-50 text-sm">
          {lot.items.map(({ recipe_id: id, input }) => {
            const r = etats[id]
            const etat = ETAT[r?.status] ?? ETAT.pending
            return (
              <li key={id} className="px-4 py-3 flex gap-3 items-start">
                <span title={t(etat.texte)}>{etat.icone}</span>
                <div className="min-w-0 flex-1">
                  {r?.status === 'done' ? (
                    <Link to={`/recettes/${id}`} className="font-medium text-gray-900 hover:text-orange-600">{r.title}</Link>
                  ) : (
                    <p className="text-gray-500">{r?.status === 'processing' ? (r.progress_message || t(etat.texte)) : t(etat.texte)}</p>
                  )}
                  <p className="text-xs text-gray-400 truncate">{input}</p>
                  {r?.status === 'failed' && <p className="text-xs text-red-600 mt-1">{r.error_msg}</p>}
                </div>
              </li>
            )
          })}
        </ul>
        {lot.already_saved.length > 0 && (
          <p className="text-xs text-gray-500">
            {t(lot.already_saved.length > 1 ? 'importGroupe.alreadySavedMany' : 'importGroupe.alreadySavedOne', { n: lot.already_saved.length })}
          </p>
        )}
        {lot.ignored > 0 && (
          <p className="text-xs text-orange-700">{t(lot.ignored > 1 ? 'importGroupe.ignoredMany' : 'importGroupe.ignoredOne', { n: lot.ignored })}</p>
        )}
        {fini && (
          <div className="flex gap-3">
            <Link to="/" className="px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg text-sm font-medium">{t('importGroupe.seeRecipes')}</Link>
            <button onClick={() => { setLot(null); setEtats({}); setTexte('') }}
              className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm">{t('importGroupe.importMore')}</button>
          </div>
        )}
      </div>
    )
  }

  const nb = countLinks(texte)
  return (
    <form onSubmit={envoyer} className="space-y-4">
      <textarea
        value={texte}
        onChange={(e) => setTexte(e.target.value)}
        placeholder={t('importGroupe.placeholder')}
        rows={8}
        className="w-full px-4 py-3 rounded-xl border border-gray-200 bg-white shadow-sm focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-transparent resize-none font-mono text-sm"
      />
      {erreur && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">{erreur}</div>}
      <button type="submit" disabled={envoi || nb === 0}
        className="w-full py-3 bg-orange-600 hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-colors">
        {envoi ? t('envoi.sending') : nb ? t(nb > 1 ? 'importGroupe.importMany' : 'importGroupe.importOne', { n: nb }) : t('importGroupe.importLinks')}
      </button>
      <p className="text-xs text-gray-400 text-center">
        {t('importGroupe.hint')}
      </p>
    </form>
  )
}
