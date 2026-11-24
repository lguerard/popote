import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteCookLog, getCookHistory, markCooked } from '../api'
import { useAuth } from '../auth'
import Etoiles from './Etoiles'

function aujourdhui() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// « Cuisinée le… » : journal des fois où la recette a été faite.
export default function Historique({ recipeId, onChange }) {
  const { t } = useAuth()
  const qc = useQueryClient()
  const key = ['cook-history', recipeId]
  const [ouvert, setOuvert] = useState(false)
  const [date, setDate] = useState(aujourdhui)
  const [note, setNote] = useState(null)
  const [commentaire, setCommentaire] = useState('')
  const { data: logs = [] } = useQuery({ queryKey: key, queryFn: () => getCookHistory(recipeId) })

  const done = (recipe) => { onChange(recipe); qc.invalidateQueries({ queryKey: key }) }
  const add = useMutation({
    mutationFn: () => markCooked(recipeId, { cooked_on: date, rating: note, comment: commentaire || null }),
    onSuccess: (r) => { done(r); setOuvert(false); setNote(null); setCommentaire(''); setDate(aujourdhui()) },
  })
  const remove = useMutation({ mutationFn: (logId) => deleteCookLog(recipeId, logId), onSuccess: done })

  return (
    <section className="mb-8 p-4 bg-white rounded-xl border border-gray-100">
      <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
        <h3 className="font-semibold text-gray-800">{t('historique.title')}</h3>
        {!ouvert && (
          <button onClick={() => setOuvert(true)} className="px-3 py-1.5 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700">
            {t('historique.cookedIt')}
          </button>
        )}
      </div>
      {ouvert && (
        <form onSubmit={e => { e.preventDefault(); add.mutate() }} className="mb-4 p-3 bg-green-50 rounded-lg space-y-2">
          <div className="flex items-center gap-3 flex-wrap text-sm">
            <label className="flex items-center gap-2">{t('historique.on')}
              <input type="date" value={date} max={aujourdhui()} onChange={e => setDate(e.target.value)}
                className="px-2 py-1 rounded border border-gray-200" />
            </label>
            <Etoiles value={note} onChange={setNote} />
          </div>
          <input value={commentaire} onChange={e => setCommentaire(e.target.value)} placeholder={t('historique.commentPlaceholder')}
            className="w-full px-3 py-1.5 rounded border border-gray-200 text-sm" />
          <div className="flex gap-2">
            <button disabled={add.isPending || !date} className="px-3 py-1.5 text-sm bg-green-600 text-white rounded-lg disabled:opacity-50">{t('common.save')}</button>
            <button type="button" onClick={() => setOuvert(false)} className="px-3 py-1.5 text-sm bg-white rounded-lg">{t('common.cancel')}</button>
          </div>
        </form>
      )}
      {logs.length === 0 ? (
        <p className="text-sm text-gray-400">{t('historique.never')}</p>
      ) : (
        <ul className="divide-y divide-gray-50 text-sm">
          {logs.map(log => (
            <li key={log.id} className="flex items-center gap-3 py-2 group">
              <span className="text-gray-700 w-28 flex-shrink-0">{new Date(`${log.cooked_on}T00:00:00`).toLocaleDateString(t('common.locale'))}</span>
              {log.rating && <Etoiles value={log.rating} size="text-sm" />}
              <span className="text-gray-500 flex-1 min-w-0 truncate">{log.comment}</span>
              <button onClick={() => remove.mutate(log.id)} title={t('common.delete')}
                className="text-gray-300 hover:text-red-500 sm:opacity-0 group-hover:opacity-100">×</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
