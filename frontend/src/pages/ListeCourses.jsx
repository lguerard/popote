import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getRecipes, getShoppingItems, generateShoppingItems, addShoppingItem, updateShoppingItem,
  deleteShoppingItem, clearShoppingItems, shareShoppingList, unshareShoppingList,
} from '../api'
import LienPartage from '../components/LienPartage'

const AISLE_EMOJI = {
  'Fruits et légumes': '🥕',
  'Boucherie et poissonnerie': '🥩',
  'Crèmerie et œufs': '🧀',
  'Boulangerie': '🥖',
  'Épicerie salée': '🥫',
  'Épicerie sucrée': '🍫',
  'Épices et condiments': '🧂',
  'Surgelés': '❄️',
  'Boissons': '🥤',
  'Autres': '🛍️',
}

const KEY = ['shopping-items']

// Liste groupée par rayon, articles cochés en bas de chaque rayon.
// Partagée avec la page publique /partage/courses/<jeton>.
export function ListeParRayon({ items, aisles, onToggle, onDelete }) {
  const groups = aisles
    .map(aisle => ({ aisle, items: items.filter(i => i.aisle === aisle) }))
    .filter(g => g.items.length)
  const inconnus = items.filter(i => !aisles.includes(i.aisle))
  if (inconnus.length) groups.push({ aisle: 'Autres', items: inconnus })

  if (!items.length) {
    return (
      <div className="text-center py-16 text-gray-400">
        <div className="text-5xl mb-3">🛒</div>
        <p className="font-medium text-gray-500">La liste est vide</p>
      </div>
    )
  }
  return (
    <div className="space-y-5">
      {groups.map(({ aisle, items: rows }) => {
        const restants = rows.filter(i => !i.checked).length
        return (
          <section key={aisle}>
            <h2 className={`text-sm font-semibold mb-2 flex items-center gap-2 ${restants ? 'text-gray-700' : 'text-gray-300'}`}>
              <span>{AISLE_EMOJI[aisle] || '🛍️'}</span>{aisle}
              <span className="text-xs font-normal text-gray-400">{restants ? `${restants}/${rows.length}` : '✓'}</span>
            </h2>
            <ul className="space-y-1">
              {[...rows.filter(i => !i.checked), ...rows.filter(i => i.checked)].map(item => (
                <li key={item.id}
                  className={`group flex items-center gap-3 p-3 bg-white rounded-xl border border-gray-100 select-none ${item.checked ? 'opacity-50' : 'hover:border-orange-200'}`}>
                  <button onClick={() => onToggle(item)} className="print-keep flex items-center gap-3 flex-1 min-w-0 text-left">
                    <span className={`w-5 h-5 border-2 rounded flex-shrink-0 flex items-center justify-center text-xs ${
                      item.checked ? 'border-green-400 bg-green-100 text-green-600' : 'border-gray-300'
                    }`}>{item.checked && '✓'}</span>
                    <span className={`flex-1 min-w-0 ${item.checked ? 'line-through' : ''}`}>
                      <span className="font-medium">{item.name}</span>
                      {(item.quantity || item.unit) && (
                        <span className="text-orange-600 ml-2 font-semibold">{[item.quantity, item.unit].filter(Boolean).join(' ')}</span>
                      )}
                    </span>
                    {item.recipes?.length > 0 && (
                      <span className="text-xs text-gray-400 hidden sm:block truncate max-w-[40%]">{item.recipes.slice(0, 2).join(', ')}</span>
                    )}
                  </button>
                  {onDelete && (
                    <button onClick={() => onDelete(item)} title="Retirer"
                      className="text-gray-300 hover:text-red-500 px-1 sm:opacity-0 group-hover:opacity-100">×</button>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}

export default function ListeCourses() {
  const qc = useQueryClient()
  // null : choisi automatiquement (sélection de recettes si la liste est vide)
  const [choix, setChoix] = useState(null)
  const [nouveau, setNouveau] = useState('')
  const [partage, setPartage] = useState(false)

  // Rafraîchie toutes les 5 s : ce qui est coché sur un autre appareil (ou
  // via le lien partagé) apparaît sans recharger.
  const { data, isLoading } = useQuery({ queryKey: KEY, queryFn: getShoppingItems, refetchInterval: 5000 })
  const items = data?.items ?? []
  const aisles = data?.aisles ?? []

  const setList = (list) => qc.setQueryData(KEY, list)
  const refresh = () => qc.invalidateQueries({ queryKey: KEY })

  const toggle = async (item) => {
    qc.setQueryData(KEY, prev => ({
      ...prev, items: prev.items.map(i => i.id === item.id ? { ...i, checked: !i.checked } : i),
    }))
    try { await updateShoppingItem(item.id, { checked: !item.checked }) } finally { refresh() }
  }
  const remove = async (item) => {
    qc.setQueryData(KEY, prev => ({ ...prev, items: prev.items.filter(i => i.id !== item.id) }))
    try { await deleteShoppingItem(item.id) } finally { refresh() }
  }
  const add = useMutation({
    mutationFn: () => addShoppingItem({ name: nouveau.trim() }),
    onSuccess: () => { setNouveau(''); refresh() },
  })
  const clear = useMutation({ mutationFn: clearShoppingItems, onSuccess: refresh })
  const share = useMutation({ mutationFn: shareShoppingList, onSuccess: setList })
  const unshare = useMutation({ mutationFn: unshareShoppingList, onSuccess: setList })

  if (choix || (choix === null && !isLoading && items.length === 0)) {
    return <ChoixRecettes hasItems={items.length > 0}
      onDone={(list) => { setList(list); setChoix(false) }} onCancel={() => setChoix(false)} />
  }

  const restants = items.filter(i => !i.checked).length
  const coches = items.length - restants

  return (
    <div className="max-w-2xl">
      <div className="flex items-center justify-between gap-2 mb-2 flex-wrap print:hidden">
        <h1 className="text-2xl font-bold text-gray-900">🛒 Liste de courses</h1>
        <div className="flex gap-2 flex-wrap">
          <button onClick={() => setPartage(p => !p)} className="px-3 py-2 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg">👨‍👩‍👧 Foyer</button>
          <button onClick={() => window.print()} className="px-3 py-2 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg">🖨️</button>
          <button onClick={() => setChoix(true)} className="px-3 py-2 text-sm bg-orange-100 text-orange-700 hover:bg-orange-200 rounded-lg">+ Recettes</button>
        </div>
      </div>
      <p className="text-sm text-gray-500 mb-4 print:hidden">
        {restants} article{restants !== 1 ? 's' : ''} restant{restants !== 1 ? 's' : ''}
        {coches > 0 && (
          <> · <button onClick={() => clear.mutate(true)} className="text-orange-600 hover:underline">retirer les {coches} cochés</button></>
        )}
        {' · '}<button onClick={() => { if (confirm('Vider toute la liste ?')) clear.mutate(false) }} className="text-red-500 hover:underline">tout vider</button>
      </p>

      {partage && (
        <div className="mb-5 p-4 bg-white rounded-xl border border-gray-100 print:hidden">
          <p className="text-sm text-gray-600 mb-3">
            Envoyez ce lien au reste du foyer : chacun peut cocher les articles en magasin, sans compte.
            Les cases se synchronisent toutes seules.
          </p>
          <LienPartage token={data?.share_token} path={`/partage/courses/${data?.share_token}`}
            onShare={() => share.mutate()} onUnshare={() => unshare.mutate()}
            busy={share.isPending || unshare.isPending} label="Créer le lien du foyer" />
        </div>
      )}

      <form onSubmit={e => { e.preventDefault(); if (nouveau.trim()) add.mutate() }} className="flex gap-2 mb-6 print:hidden">
        <input value={nouveau} onChange={e => setNouveau(e.target.value)} placeholder="Ajouter un article (lessive, pain…)"
          className="flex-1 px-4 py-2 rounded-xl border border-gray-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
        <button disabled={!nouveau.trim() || add.isPending} className="px-4 py-2 bg-orange-600 text-white rounded-xl text-sm disabled:opacity-50">Ajouter</button>
      </form>

      {isLoading
        ? <div className="animate-pulse text-gray-400 py-12 text-center">Chargement…</div>
        : <ListeParRayon items={items} aisles={aisles} onToggle={toggle} onDelete={remove} />}
    </div>
  )
}

function ChoixRecettes({ hasItems, onDone, onCancel }) {
  const [selectedIds, setSelectedIds] = useState([])
  const [remplacer, setRemplacer] = useState(false)
  const { data: recipes = [] } = useQuery({ queryKey: ['recipes', { limit: 1000 }], queryFn: () => getRecipes({ limit: 1000 }) })
  const gen = useMutation({
    mutationFn: () => generateShoppingItems({ recipe_ids: selectedIds, replace: !hasItems || remplacer }),
    onSuccess: onDone,
  })
  const toggle = (id) => setSelectedIds(ids => ids.includes(id) ? ids.filter(i => i !== id) : [...ids, id])

  return (
    <div className="max-w-2xl">
      <div className="flex items-center justify-between mb-2">
        <h1 className="text-2xl font-bold text-gray-900">🛒 Liste de courses</h1>
        <button onClick={onCancel} className="px-3 py-2 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg">
          {hasItems ? '← Ma liste' : 'Ajouter à la main'}
        </button>
      </div>
      <p className="text-gray-500 text-sm mb-6">
        Sélectionnez les recettes à cuisiner, ou générez la liste de la semaine depuis le <Link to="/planning" className="text-orange-600 hover:underline">planning</Link>.
        Les ingrédients sont additionnés et rangés par rayon.
      </p>

      {recipes.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <div className="text-5xl mb-3">🍽️</div>
          <p className="font-medium text-gray-500">Aucune recette pour l'instant</p>
        </div>
      ) : (
        <div className="space-y-2 mb-6">
          {recipes.map(r => (
            <label key={r.id} className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
              selectedIds.includes(r.id) ? 'border-orange-400 bg-orange-50' : 'border-gray-200 bg-white hover:border-orange-200'
            }`}>
              <input type="checkbox" checked={selectedIds.includes(r.id)} onChange={() => toggle(r.id)} className="accent-orange-600 w-4 h-4" />
              {r.thumbnail_url && <img src={r.thumbnail_url} alt="" className="w-10 h-10 rounded-lg object-cover flex-shrink-0" />}
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{r.title}</p>
                <p className="text-xs text-gray-400">{r.servings ? `${r.servings} pers.` : ''} {r.category || ''}</p>
              </div>
            </label>
          ))}
        </div>
      )}

      {hasItems && (
        <label className="flex items-center gap-2 text-sm text-gray-600 mb-3">
          <input type="checkbox" checked={remplacer} onChange={e => setRemplacer(e.target.checked)} className="accent-orange-600" />
          Remplacer la liste actuelle (sinon, ajouter à la suite)
        </label>
      )}
      {gen.isError && <p className="text-sm text-red-600 mb-3">{gen.error?.response?.data?.detail || 'Génération impossible'}</p>}
      <button onClick={() => gen.mutate()} disabled={selectedIds.length === 0 || gen.isPending}
        className="w-full py-3 bg-orange-600 hover:bg-orange-700 disabled:opacity-50 text-white font-semibold rounded-xl">
        {gen.isPending ? 'Génération…' : `Générer la liste (${selectedIds.length} recette${selectedIds.length > 1 ? 's' : ''})`}
      </button>
    </div>
  )
}
