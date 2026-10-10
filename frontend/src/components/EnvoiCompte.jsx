import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getShareableUsers, sendRecipes } from '../api'

// Envoie une recette (recipeIds) ou toute la bibliothèque (tout) à un autre
// compte. Le destinataire en reçoit une copie, marquée « de <vous> ».
export default function EnvoiCompte({ recipeIds = [], tout = false }) {
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

  if (isLoading) return <p className="text-sm text-gray-400">Chargement des comptes…</p>
  if (!comptes?.length) {
    return <p className="text-sm text-gray-500">Aucun autre compte sur ce serveur pour l'instant.</p>
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
          <span>Envoyer aussi automatiquement mes prochaines recettes</span>
        </label>
      )}
      <button onClick={() => envoi.mutate()} disabled={!destinataire || envoi.isPending}
        className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:opacity-50">
        {envoi.isPending ? 'Envoi…' : tout ? 'Partager toutes mes recettes' : 'Envoyer la recette'}
      </button>
      {resultat && (
        <p className="text-green-700">
          {resultat.copied
            ? `✓ ${resultat.copied} recette${resultat.copied > 1 ? 's' : ''} envoyée${resultat.copied > 1 ? 's' : ''}.`
            : '✓ Ce compte a déjà cette recette.'}
          {resultat.copied > 0 && resultat.skipped > 0 && ` ${resultat.skipped} déjà présente${resultat.skipped > 1 ? 's' : ''}.`}
          {resultat.automatic && ' Les prochaines suivront automatiquement.'}
        </p>
      )}
      {envoi.isError && <p className="text-red-600">Envoi impossible : {envoi.error?.response?.data?.detail || envoi.error.message}</p>}
    </div>
  )
}
