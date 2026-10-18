import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { downloadBackup, importBackup } from '../api'

// Nom proposé par le serveur (« popote-sauvegarde-2026-10-17.zip »).
const nomFichier = (disposition) =>
  /filename="?([^";]+)"?/.exec(disposition || '')?.[1] || 'popote-sauvegarde.zip'

export default function Sauvegarde() {
  const qc = useQueryClient()
  const fichier = useRef(null)
  const [export_, setExport] = useState({ enCours: false, erreur: null })
  const [import_, setImport] = useState({ progression: null, rapport: null, erreur: null })

  const telecharger = async () => {
    setExport({ enCours: true, erreur: null })
    try {
      const res = await downloadBackup()
      const url = URL.createObjectURL(res.data)
      const lien = document.createElement('a')
      lien.href = url
      lien.download = nomFichier(res.headers['content-disposition'])
      lien.click()
      setTimeout(() => URL.revokeObjectURL(url), 10000)
      setExport({ enCours: false, erreur: null })
    } catch {
      setExport({ enCours: false, erreur: 'La sauvegarde a échoué. Réessayez.' })
    }
  }

  const restaurer = async (e) => {
    const choisi = e.target.files?.[0]
    e.target.value = ''
    if (!choisi) return
    setImport({ progression: 0, rapport: null, erreur: null })
    try {
      const rapport = await importBackup(choisi, (p) => setImport((s) => ({ ...s, progression: p })))
      setImport({ progression: null, rapport, erreur: null })
      qc.invalidateQueries()
    } catch (err) {
      const message = err.response?.status === 413
        ? 'Fichier trop volumineux pour le serveur.'
        : err.response?.data?.detail || 'La restauration a échoué.'
      setImport({ progression: null, rapport: null, erreur: message })
    }
  }

  const r = import_.rapport
  const pluriel = (n, mot) => `${n} ${mot}${n > 1 ? 's' : ''}`
  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">💾 Sauvegarde</h1>
        <p className="text-gray-500 mt-1 text-sm">
          Toutes vos recettes dans un seul fichier : contenu, images, notes, favoris, avis, historique et carnets.
          À garder au chaud, ou à restaurer sur ce serveur ou un autre.
        </p>
      </div>

      <section className="p-4 bg-white rounded-xl border border-gray-100 space-y-3">
        <h2 className="font-semibold text-gray-800">Télécharger une sauvegarde</h2>
        <button onClick={telecharger} disabled={export_.enCours}
          className="px-4 py-2 bg-orange-600 hover:bg-orange-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium">
          {export_.enCours ? 'Préparation du fichier…' : '⬇️ Télécharger mes recettes (.zip)'}
        </button>
        {export_.erreur && <p className="text-sm text-red-600">{export_.erreur}</p>}
        <p className="text-xs text-gray-400">Le planning et la liste de courses ne sont pas inclus.</p>
      </section>

      <section className="p-4 bg-white rounded-xl border border-gray-100 space-y-3">
        <h2 className="font-semibold text-gray-800">Restaurer une sauvegarde</h2>
        <p className="text-sm text-gray-500">
          Les recettes de la sauvegarde sont ajoutées à votre compte. Celles que vous avez déjà
          (même lien d'origine, ou même nom) ne sont pas dupliquées, et les carnets du même nom sont complétés.
        </p>
        <input ref={fichier} type="file" accept=".zip,application/zip" onChange={restaurer} className="hidden" />
        <button onClick={() => fichier.current?.click()} disabled={import_.progression !== null}
          className="px-4 py-2 bg-gray-100 hover:bg-gray-200 disabled:opacity-50 rounded-lg text-sm font-medium">
          {import_.progression === null
            ? '⬆️ Choisir un fichier .zip'
            : import_.progression < 1 ? `Envoi… ${Math.round(import_.progression * 100)} %` : 'Restauration…'}
        </button>
        {import_.erreur && <p className="text-sm text-red-600">{import_.erreur}</p>}
        {r && (
          <div className="text-sm bg-green-50 text-green-800 rounded-lg p-3 space-y-1">
            <p>✅ {pluriel(r.recipes_added, 'recette')} ajoutée{r.recipes_added > 1 ? 's' : ''}
              {r.images > 0 && ` (${pluriel(r.images, 'image')})`}
              {r.collections_added > 0 && `, ${pluriel(r.collections_added, 'carnet')} créé${r.collections_added > 1 ? 's' : ''}`}.</p>
            {r.recipes_skipped > 0 && <p>{pluriel(r.recipes_skipped, 'recette')} déjà présente{r.recipes_skipped > 1 ? 's' : ''}, gardée{r.recipes_skipped > 1 ? 's' : ''} telle{r.recipes_skipped > 1 ? 's' : ''} quelle{r.recipes_skipped > 1 ? 's' : ''}.</p>}
            {r.invalid > 0 && <p className="text-orange-700">{pluriel(r.invalid, 'élément')} illisible{r.invalid > 1 ? 's' : ''} ignoré{r.invalid > 1 ? 's' : ''}.</p>}
          </div>
        )}
      </section>
    </div>
  )
}
