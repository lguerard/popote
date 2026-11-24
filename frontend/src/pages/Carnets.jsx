import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createCollection, deleteCollection, getCollection, getCollections, removeFromCollection,
  shareCollection, unshareCollection, updateCollection,
} from '../api'
import CarteRecette from '../components/CarteRecette'
import LienPartage from '../components/LienPartage'
import { useAuth } from '../auth'

const EMOJIS = ['📒', '☀️', '🎄', '🥗', '⚡', '🍰', '🌶️', '🥘', '🎉', '👶', '💪', '🌱']

export function Carnets() {
  const { t } = useAuth()
  const qc = useQueryClient()
  const [nom, setNom] = useState('')
  const [emoji, setEmoji] = useState(EMOJIS[0])
  const { data: collections = [], isLoading } = useQuery({ queryKey: ['collections'], queryFn: () => getCollections() })
  const create = useMutation({
    mutationFn: () => createCollection({ name: nom.trim(), emoji }),
    onSuccess: () => { setNom(''); qc.invalidateQueries({ queryKey: ['collections'] }) },
  })

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-1">{t('carnets.title')}</h1>
      <p className="text-gray-400 text-sm mb-6">{t('carnets.subtitle')}</p>

      <form onSubmit={e => { e.preventDefault(); if (nom.trim()) create.mutate() }}
        className="flex flex-wrap gap-2 mb-8 p-4 bg-white rounded-2xl border border-gray-100">
        <select value={emoji} onChange={e => setEmoji(e.target.value)}
          className="px-2 py-2 rounded-lg border border-gray-200 bg-white text-lg">
          {EMOJIS.map(e => <option key={e}>{e}</option>)}
        </select>
        <input value={nom} onChange={e => setNom(e.target.value)} placeholder={t('carnets.newPlaceholder')}
          className="flex-1 min-w-[12rem] px-3 py-2 rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-orange-400" />
        <button disabled={!nom.trim() || create.isPending}
          className="px-4 py-2 bg-orange-600 text-white rounded-lg disabled:opacity-50">{t('carnets.create')}</button>
      </form>

      {isLoading ? (
        <div className="animate-pulse text-gray-400 py-12 text-center">{t('common.loading')}</div>
      ) : collections.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <div className="text-5xl mb-3">📚</div>
          <p className="font-medium text-gray-500">{t('carnets.empty')}</p>
          <p className="mt-1 text-sm">{t('carnets.emptyHint')}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {collections.map(c => (
            <Link key={c.id} to={`/carnets/${c.id}`}
              className="group bg-white rounded-2xl shadow-sm hover:shadow-md overflow-hidden">
              <div className="aspect-video bg-orange-50 grid grid-cols-2 grid-rows-2 gap-0.5 overflow-hidden">
                {c.covers.length ? c.covers.slice(0, 4).map((src, i) => (
                  <img key={i} src={src} alt="" className={`w-full h-full object-cover ${c.covers.length === 1 ? 'col-span-2 row-span-2' : ''}`} />
                )) : <span className="col-span-2 row-span-2 flex items-center justify-center text-5xl">{c.emoji || '📒'}</span>}
              </div>
              <div className="p-4">
                <p className="font-semibold text-gray-900 group-hover:text-orange-600">{c.emoji} {c.name}</p>
                <p className="text-xs text-gray-400 mt-1">
                  {t(c.recipe_count !== 1 ? 'accueil.countMany' : 'accueil.countOne', { n: c.recipe_count })}{c.share_token && t('carnets.shared')}
                </p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

export function Carnet() {
  const { t } = useAuth()
  const { id } = useParams()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [edition, setEdition] = useState(null)
  const key = ['collection', id]
  const { data: c, isLoading, isError } = useQuery({ queryKey: key, queryFn: () => getCollection(id) })
  const refresh = () => { qc.invalidateQueries({ queryKey: key }); qc.invalidateQueries({ queryKey: ['collections'] }) }

  const save = useMutation({ mutationFn: (data) => updateCollection(id, data), onSuccess: () => { setEdition(null); refresh() } })
  const remove = useMutation({
    mutationFn: () => deleteCollection(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['collections'] }); navigate('/carnets') },
  })
  const removeRecipe = useMutation({ mutationFn: (recipeId) => removeFromCollection(id, recipeId), onSuccess: refresh })
  const share = useMutation({ mutationFn: () => shareCollection(id), onSuccess: refresh })
  const unshare = useMutation({ mutationFn: () => unshareCollection(id), onSuccess: refresh })

  if (isLoading) return <div className="animate-pulse text-gray-400 py-12 text-center">{t('common.loading')}</div>
  if (isError) return <div className="text-red-500 py-12 text-center">{t('carnets.notFound')}</div>

  return (
    <div>
      <Link to="/carnets" className="text-sm text-orange-600 hover:underline mb-2 inline-block">{t('carnets.back')}</Link>
      {edition ? (
        <form onSubmit={e => { e.preventDefault(); save.mutate(edition) }} className="space-y-2 mb-6 max-w-xl">
          <div className="flex gap-2">
            <select value={edition.emoji || ''} onChange={e => setEdition({ ...edition, emoji: e.target.value })}
              className="px-2 py-2 rounded-lg border border-gray-200 bg-white text-lg">
              {EMOJIS.map(e => <option key={e}>{e}</option>)}
            </select>
            <input value={edition.name} onChange={e => setEdition({ ...edition, name: e.target.value })}
              className="flex-1 px-3 py-2 rounded-lg border border-gray-200 text-lg font-semibold" />
          </div>
          <textarea value={edition.description || ''} onChange={e => setEdition({ ...edition, description: e.target.value })}
            placeholder={t('carnets.descriptionPlaceholder')} rows={2}
            className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm" />
          <div className="flex gap-2">
            <button disabled={!edition.name.trim()} className="px-4 py-2 bg-orange-600 text-white rounded-lg text-sm disabled:opacity-50">{t('common.save')}</button>
            <button type="button" onClick={() => setEdition(null)} className="px-4 py-2 bg-gray-100 rounded-lg text-sm">{t('common.cancel')}</button>
          </div>
        </form>
      ) : (
        <div className="flex items-start justify-between gap-4 mb-6 flex-wrap">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">{c.emoji} {c.name}</h1>
            {c.description && <p className="text-gray-500 mt-1">{c.description}</p>}
          </div>
          <div className="flex gap-2">
            <button onClick={() => setEdition({ name: c.name, emoji: c.emoji, description: c.description })}
              className="px-3 py-2 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg">{t('common.edit')}</button>
            <button onClick={() => { if (confirm(t('carnets.confirmDelete'))) remove.mutate() }}
              className="px-3 py-2 text-sm bg-red-50 text-red-600 hover:bg-red-100 rounded-lg">{t('common.delete')}</button>
          </div>
        </div>
      )}

      <div className="mb-8 max-w-xl">
        <LienPartage token={c.share_token} path={`/partage/c/${c.share_token}`}
          onShare={() => share.mutate()} onUnshare={() => unshare.mutate()}
          busy={share.isPending || unshare.isPending} label={t('carnets.shareLabel')} />
      </div>

      {c.recipes.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <div className="text-5xl mb-3">📭</div>
          <p>{t('carnets.emptyCollection')}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {c.recipes.map(r => (
            <div key={r.id} className="relative group">
              <CarteRecette recipe={r} />
              <button onClick={() => removeRecipe.mutate(r.id)} title={t('carnets.removeFrom')}
                className="absolute top-2 left-2 bg-white/90 rounded-full w-8 h-8 shadow text-gray-500 hover:text-red-600 sm:opacity-0 group-hover:opacity-100">×</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
