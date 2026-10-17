import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { submitBatchExtraction, getTasksStatus } from '../api'

// Liens d'un texte collé : même détection approximative que le serveur,
// seulement pour annoncer « 12 liens détectés » avant l'envoi.
export const countLinks = (text) =>
  new Set((text || '').match(/(?:https?:\/\/|www\.)[^\s<>"']+|^[a-z0-9-]+(?:\.[a-z0-9-]+)+\/\S*/gim) || []).size

const ETAT = {
  pending: { icone: '⏳', texte: 'En attente' },
  processing: { icone: '🔄', texte: 'Extraction…' },
  done: { icone: '✅', texte: 'Ajoutée' },
  failed: { icone: '⚠️', texte: 'Échec' },
}

/** Import de plusieurs liens (reels enregistrés, favoris…) avec leur suivi. */
export default function ImportGroupe({ initialText = '' }) {
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
      setErreur(err.response?.data?.detail || 'Erreur lors de l\'envoi')
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
            ? `Terminé : ${reussies} recette${reussies > 1 ? 's' : ''} ajoutée${reussies > 1 ? 's' : ''} sur ${ids.length}.`
            : `${termines} / ${ids.length} — les liens sont extraits l'un après l'autre. Vous pouvez quitter cette page : l'import continue.`}
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
                <span title={etat.texte}>{etat.icone}</span>
                <div className="min-w-0 flex-1">
                  {r?.status === 'done' ? (
                    <Link to={`/recettes/${id}`} className="font-medium text-gray-900 hover:text-orange-600">{r.title}</Link>
                  ) : (
                    <p className="text-gray-500">{r?.status === 'processing' ? (r.progress_message || etat.texte) : etat.texte}</p>
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
            Déjà dans Popote, non réimporté{lot.already_saved.length > 1 ? 's' : ''} : {lot.already_saved.length} lien{lot.already_saved.length > 1 ? 's' : ''}.
          </p>
        )}
        {lot.ignored > 0 && (
          <p className="text-xs text-orange-700">{lot.ignored} lien{lot.ignored > 1 ? 's' : ''} au-delà de 50 non envoyé{lot.ignored > 1 ? 's' : ''} : relancez-les ensuite.</p>
        )}
        {fini && (
          <div className="flex gap-3">
            <Link to="/" className="px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg text-sm font-medium">Voir mes recettes</Link>
            <button onClick={() => { setLot(null); setEtats({}); setTexte('') }}
              className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm">Importer d'autres liens</button>
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
        placeholder={'Collez plusieurs liens, un par ligne (ou en vrac) :\nhttps://www.instagram.com/reel/…\nhttps://www.tiktok.com/@…/video/…\nhttps://www.marmiton.org/…'}
        rows={8}
        className="w-full px-4 py-3 rounded-xl border border-gray-200 bg-white shadow-sm focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-transparent resize-none font-mono text-sm"
      />
      {erreur && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">{erreur}</div>}
      <button type="submit" disabled={envoi || nb === 0}
        className="w-full py-3 bg-orange-600 hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-colors">
        {envoi ? 'Envoi…' : nb ? `Importer ${nb} lien${nb > 1 ? 's' : ''}` : 'Importer les liens'}
      </button>
      <p className="text-xs text-gray-400 text-center">
        Jusqu'à 50 liens à la fois, extraits l'un après l'autre. Les liens déjà importés sont ignorés.
      </p>
    </form>
  )
}
