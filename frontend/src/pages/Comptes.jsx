import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { approveUser, listUsers, rejectUser } from '../api'
import { useAuth } from '../auth'

const ETIQUETTES = {
  pending:  { texte: 'comptes.status.pending',  classe: 'bg-amber-100 text-amber-700' },
  approved: { texte: 'comptes.status.approved', classe: 'bg-emerald-100 text-emerald-700' },
  rejected: { texte: 'comptes.status.rejected', classe: 'bg-gray-200 text-gray-500' },
}

export default function Comptes() {
  const { user, t } = useAuth()
  const qc = useQueryClient()
  // Les refus de plus d'une semaine sont masqués par défaut : la page
  // sert à traiter les demandes du moment, pas à tenir un historique.
  const [archives, setArchives] = useState(false)
  const { data: comptes, isLoading, error } = useQuery({
    queryKey: ['comptes', archives], queryFn: () => listUsers(archives),
  })
  const decider = useMutation({
    mutationFn: ({ id, action }) => (action === 'approve' ? approveUser(id) : rejectUser(id)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['comptes'] }),
  })

  if (isLoading) return <p className="text-gray-400">{t('common.loading')}</p>
  if (error) return <p className="text-red-600">{t('comptes.loadError')}</p>

  const attente = comptes.filter(c => c.status === 'pending')

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-800 mb-1">{t('comptes.title')}</h1>
      <p className="text-sm text-gray-500 mb-6">
        {attente.length === 0
          ? t('comptes.noPending')
          : t(attente.length > 1 ? 'comptes.pendingMany' : 'comptes.pendingOne', { n: attente.length })}
      </p>

      <div className="space-y-2">
        {comptes.map(c => {
          const et = ETIQUETTES[c.status] || ETIQUETTES.pending
          const soi = c.id === user?.id
          return (
            <div key={c.id}
                 className="flex items-center gap-3 bg-white p-4 rounded-xl border border-gray-100">
              <div className="flex-1 min-w-0">
                <p className="font-medium text-gray-800 truncate">
                  {c.display_name}
                  {c.is_admin && <span className="ml-2 text-xs text-orange-600">{t('comptes.admin')}</span>}
                  {soi && <span className="ml-2 text-xs text-gray-400">{t('comptes.you')}</span>}
                </p>
                <p className="text-sm text-gray-400 truncate">{c.email}</p>
              </div>
              <span className={`text-xs px-2 py-1 rounded-full ${et.classe}`}>{t(et.texte)}</span>

              {/* Un administrateur ne peut pas se juger lui-même : le
                  serveur le refuse aussi, on évite juste le clic inutile. */}
              {!soi && (
                <div className="flex gap-2 flex-shrink-0">
                  {c.status !== 'approved' && (
                    <button
                      onClick={() => decider.mutate({ id: c.id, action: 'approve' })}
                      disabled={decider.isPending}
                      className="text-sm px-3 py-1.5 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
                    >
                      {t('comptes.approve')}
                    </button>
                  )}
                  {c.status !== 'rejected' && (
                    <button
                      onClick={() => decider.mutate({ id: c.id, action: 'reject' })}
                      disabled={decider.isPending}
                      className="text-sm px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                    >
                      {c.status === 'approved' ? t('comptes.revoke') : t('comptes.reject')}
                    </button>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <button
        onClick={() => setArchives(!archives)}
        className="mt-6 text-sm text-orange-600 hover:underline"
      >
        {archives ? t('comptes.hideArchived') : t('comptes.showArchived')}
      </button>

      <p className="text-xs text-gray-400 mt-4">
        {t('comptes.footnote')}
      </p>
    </div>
  )
}
