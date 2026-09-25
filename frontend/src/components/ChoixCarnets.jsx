import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { addToCollection, createCollection, getCollections, removeFromCollection } from '../api'

// Cases à cocher des carnets contenant la recette, + création rapide.
export default function ChoixCarnets({ recipeId }) {
  const qc = useQueryClient()
  const key = ['collections', 'for', recipeId]
  const [nom, setNom] = useState('')
  const { data: collections = [], isLoading } = useQuery({ queryKey: key, queryFn: () => getCollections(recipeId) })
  const refresh = () => qc.invalidateQueries({ queryKey: ['collections'] })

  const toggle = useMutation({
    mutationFn: (c) => (c.contains_recipe ? removeFromCollection(c.id, recipeId) : addToCollection(c.id, recipeId)),
    onMutate: (c) => qc.setQueryData(key, prev => prev.map(x => x.id === c.id ? { ...x, contains_recipe: !c.contains_recipe } : x)),
    onSettled: refresh,
  })
  const create = useMutation({
    mutationFn: async () => {
      const c = await createCollection({ name: nom.trim(), emoji: '📒' })
      await addToCollection(c.id, recipeId)
    },
    onSuccess: () => { setNom(''); refresh() },
  })

  return (
    <div className="mb-5 p-4 bg-white rounded-xl border border-gray-100">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-semibold text-gray-700">📚 Carnets</p>
        <Link to="/carnets" className="text-xs text-orange-600 hover:underline">Gérer les carnets</Link>
      </div>
      {isLoading ? <p className="text-sm text-gray-400">Chargement…</p> : (
        <div className="flex flex-wrap gap-2 mb-3">
          {collections.map(c => (
            <button key={c.id} onClick={() => toggle.mutate(c)}
              className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                c.contains_recipe ? 'bg-orange-600 border-orange-600 text-white' : 'bg-white border-gray-200 text-gray-600 hover:border-orange-300'
              }`}>
              {c.contains_recipe ? '✓ ' : ''}{c.emoji} {c.name}
            </button>
          ))}
          {collections.length === 0 && <p className="text-sm text-gray-400">Aucun carnet : créez le premier.</p>}
        </div>
      )}
      <form onSubmit={e => { e.preventDefault(); if (nom.trim()) create.mutate() }} className="flex gap-2">
        <input value={nom} onChange={e => setNom(e.target.value)} placeholder="Nouveau carnet…"
          className="flex-1 px-3 py-1.5 rounded-lg border border-gray-200 text-sm" />
        <button disabled={!nom.trim() || create.isPending} className="px-3 py-1.5 text-sm bg-orange-100 text-orange-700 rounded-lg disabled:opacity-50">Créer et ajouter</button>
      </form>
    </div>
  )
}
