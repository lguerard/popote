import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getAutomaticShares, stopReceiving, stopSending } from '../api'
import EnvoiCompte from '../components/EnvoiCompte'

export default function PartageComptes() {
  const qc = useQueryClient()
  const { data: auto } = useQuery({ queryKey: ['partage-auto'], queryFn: getAutomaticShares })
  const arreter = useMutation({
    mutationFn: ({ sens, id }) => (sens === 'envoi' ? stopSending(id) : stopReceiving(id)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['partage-auto'] }),
  })

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">👥 Partager avec un autre compte</h1>
        <p className="text-gray-500 mt-1 text-sm">
          Chaque recette partagée est copiée dans le compte de la personne, avec un badge « Partagée par … ».
          Elle peut ensuite la noter, la planifier ou la modifier sans toucher à la vôtre.
          Pour une seule recette, utilisez le bouton 👥 sur sa fiche.
        </p>
      </div>

      <section className="p-4 bg-white rounded-xl border border-gray-100">
        <h2 className="font-semibold text-gray-800 mb-3">Partager toutes mes recettes</h2>
        <EnvoiCompte tout />
      </section>

      <section className="p-4 bg-white rounded-xl border border-gray-100 space-y-4 text-sm">
        <h2 className="font-semibold text-gray-800">Partage automatique</h2>
        <Liste titre="Mes nouvelles recettes sont envoyées à" comptes={auto?.outgoing}
          vide="Personne pour l'instant." action="Arrêter"
          onStop={(id) => arreter.mutate({ sens: 'envoi', id })} />
        <Liste titre="Je reçois automatiquement les recettes de" comptes={auto?.incoming}
          vide="Personne pour l'instant." action="Ne plus recevoir"
          onStop={(id) => arreter.mutate({ sens: 'reception', id })} />
        <p className="text-xs text-gray-400">
          Arrêter ne supprime aucune recette déjà partagée.
        </p>
      </section>
    </div>
  )
}

function Liste({ titre, comptes, vide, action, onStop }) {
  return (
    <div>
      <p className="text-gray-600 mb-2">{titre} :</p>
      {comptes?.length ? (
        <ul className="space-y-2">
          {comptes.map(c => (
            <li key={c.id} className="flex items-center justify-between gap-2">
              <span>👤 {c.display_name}</span>
              <button onClick={() => onStop(c.id)}
                className="px-3 py-1 text-red-600 bg-red-50 hover:bg-red-100 rounded-lg">{action}</button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-gray-400">{vide}</p>
      )}
    </div>
  )
}
