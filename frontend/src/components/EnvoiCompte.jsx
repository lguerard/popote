import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getShareableUsers, sendRecipes } from '../api'
import { useAuth } from '../auth'

// Envoie une recette (recipeIds) ou toute la bibliothèque (tout) à un autre
// compte. Le destinataire en reçoit une copie, marquée « de <vous> ».
export default function EnvoiCompte({ recipeIds = [], tout = false }) {
  const { t } = useAuth()
  const qc = useQueryClient()
  const [destinataire, setDestinataire] = useState('')
  const [automatique, setAutomatique] = useState(true)
  const { data: comptes, isLoading } = useQuery({ queryKey: ['comptes-partage'], queryFn: getShareableUsers })
  const envoi = useMutation({
    mutationFn: () => sendRecipes({
      user_id: destinataire, recipe_ids: recipeIds, all: tout, automatic: tout && automatique,
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['partage-auto'] }),
  })

  if (isLoading) return <p className="text-sm text-gray-400">{t('envoi.loadingAccounts')}</p>
  if (!comptes?.length) {
    return <p className="text-sm text-gray-500">{t('envoi.noAccounts')}</p>
  }

  const resultat = envoi.data
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap gap-2">
        {comptes.map(c => (
          <button key={c.id} onClick={() => { setDestinataire(c.id); envoi.reset() }}
            className={`px-3 py-1.5 rounded-full border ${
              destinataire === c.id ? 'bg-orange-600 border-orange-600 text-white' : 'bg-white border-gray-200 hover:border-orange-300'
            }`}>
            👤 {c.display_name}
          </button>
        ))}
      </div>
      {tout && (
        <label className="flex items-start gap-2 cursor-pointer">
          <input type="checkbox" checked={automatique} onChange={e => setAutomatique(e.target.checked)}
            className="accent-orange-600 w-4 h-4 mt-0.5" />
          <span>{t('envoi.autoSend')}</span>
        </label>
      )}
      <button onClick={() => envoi.mutate()} disabled={!destinataire || envoi.isPending}
        className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:opacity-50">
        {envoi.isPending ? t('envoi.sending') : tout ? t('envoi.shareAll') : t('envoi.sendRecipe')}
      </button>
      {resultat && (
        <p className="text-green-700">
          {resultat.copied
            ? t(resultat.copied > 1 ? 'envoi.sentMany' : 'envoi.sentOne', { n: resultat.copied })
            : t('envoi.alreadyHas')}
          {resultat.copied > 0 && resultat.skipped > 0 && t(resultat.skipped > 1 ? 'envoi.skippedMany' : 'envoi.skippedOne', { n: resultat.skipped })}
          {resultat.automatic && t('envoi.automatic')}
        </p>
      )}
      {envoi.isError && <p className="text-red-600">{t('envoi.error', { error: envoi.error?.response?.data?.detail || envoi.error.message })}</p>}
    </div>
  )
}
