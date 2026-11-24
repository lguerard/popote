import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getAutomaticShares, stopReceiving, stopSending } from '../api'
import EnvoiCompte from '../components/EnvoiCompte'
import { useAuth } from '../auth'

export default function PartageComptes() {
  const { t } = useAuth()
  const qc = useQueryClient()
  const { data: auto } = useQuery({ queryKey: ['partage-auto'], queryFn: getAutomaticShares })
  const arreter = useMutation({
    mutationFn: ({ sens, id }) => (sens === 'envoi' ? stopSending(id) : stopReceiving(id)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['partage-auto'] }),
  })

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{t('partageComptes.title')}</h1>
        <p className="text-gray-500 mt-1 text-sm">
          {t('partageComptes.intro')}
        </p>
      </div>

      <section className="p-4 bg-white rounded-xl border border-gray-100">
        <h2 className="font-semibold text-gray-800 mb-3">{t('partageComptes.shareAll')}</h2>
        <EnvoiCompte tout />
      </section>

      <section className="p-4 bg-white rounded-xl border border-gray-100 space-y-4 text-sm">
        <h2 className="font-semibold text-gray-800">{t('partageComptes.automatic')}</h2>
        <Liste titre={t('partageComptes.outgoing')} comptes={auto?.outgoing}
          vide={t('partageComptes.nobody')} action={t('partageComptes.stop')}
          onStop={(id) => arreter.mutate({ sens: 'envoi', id })} />
        <Liste titre={t('partageComptes.incoming')} comptes={auto?.incoming}
          vide={t('partageComptes.nobody')} action={t('partageComptes.stopReceiving')}
          onStop={(id) => arreter.mutate({ sens: 'reception', id })} />
        <p className="text-xs text-gray-400">
          {t('partageComptes.stopHint')}
        </p>
      </section>
    </div>
  )
}

function Liste({ titre, comptes, vide, action, onStop }) {
  return (
    <div>
      <p className="text-gray-600 mb-2">{titre}</p>
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
