import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { downloadBackup, importBackup } from '../api'
import { useAuth } from '../auth'

// Nom proposé par le serveur (« popote-sauvegarde-2026-10-17.zip »).
const nomFichier = (disposition) =>
  /filename="?([^";]+)"?/.exec(disposition || '')?.[1] || 'popote-sauvegarde.zip'

export default function Sauvegarde() {
  const { t } = useAuth()
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
      setExport({ enCours: false, erreur: t('sauvegarde.exportError') })
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
        ? t('sauvegarde.tooLarge')
        : err.response?.data?.detail || t('sauvegarde.restoreError')
      setImport({ progression: null, rapport: null, erreur: message })
    }
  }

  const r = import_.rapport
  const plur = (n, cle) => t(`sauvegarde.${cle}${n > 1 ? 'Many' : 'One'}`, { n })
  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{t('sauvegarde.title')}</h1>
        <p className="text-gray-500 mt-1 text-sm">
          {t('sauvegarde.intro')}
        </p>
      </div>

      <section className="p-4 bg-white rounded-xl border border-gray-100 space-y-3">
        <h2 className="font-semibold text-gray-800">{t('sauvegarde.download')}</h2>
        <button onClick={telecharger} disabled={export_.enCours}
          className="px-4 py-2 bg-orange-600 hover:bg-orange-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium">
          {export_.enCours ? t('sauvegarde.preparing') : t('sauvegarde.downloadButton')}
        </button>
        {export_.erreur && <p className="text-sm text-red-600">{export_.erreur}</p>}
        <p className="text-xs text-gray-400">{t('sauvegarde.notIncluded')}</p>
      </section>

      <section className="p-4 bg-white rounded-xl border border-gray-100 space-y-3">
        <h2 className="font-semibold text-gray-800">{t('sauvegarde.restore')}</h2>
        <p className="text-sm text-gray-500">
          {t('sauvegarde.restoreInfo')}
        </p>
        <input ref={fichier} type="file" accept=".zip,application/zip" onChange={restaurer} className="hidden" />
        <button onClick={() => fichier.current?.click()} disabled={import_.progression !== null}
          className="px-4 py-2 bg-gray-100 hover:bg-gray-200 disabled:opacity-50 rounded-lg text-sm font-medium">
          {import_.progression === null
            ? t('sauvegarde.chooseFile')
            : import_.progression < 1 ? t('sauvegarde.uploading', { n: Math.round(import_.progression * 100) }) : t('sauvegarde.restoring')}
        </button>
        {import_.erreur && <p className="text-sm text-red-600">{import_.erreur}</p>}
        {r && (
          <div className="text-sm bg-green-50 text-green-800 rounded-lg p-3 space-y-1">
            <p>{plur(r.recipes_added, 'added')}
              {r.images > 0 && plur(r.images, 'images')}
              {r.collections_added > 0 && plur(r.collections_added, 'collections')}.</p>
            {r.recipes_skipped > 0 && <p>{plur(r.recipes_skipped, 'skipped')}</p>}
            {r.invalid > 0 && <p className="text-orange-700">{plur(r.invalid, 'invalid')}</p>}
          </div>
        )}
      </section>
    </div>
  )
}
