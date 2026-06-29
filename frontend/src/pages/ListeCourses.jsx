import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getRecipes, getShoppingList } from '../api'

export default function ListeCourses() {
  const [selectedIds, setSelectedIds] = useState([])
  const [shoppingList, setShoppingList] = useState(null)
  const [loading, setLoading] = useState(false)
  const [checked, setChecked] = useState({})

  const { data: recipes = [] } = useQuery({ queryKey: ['recipes', {}], queryFn: () => getRecipes({ limit: 100 }) })

  const toggle = (id) => setSelectedIds(ids => ids.includes(id) ? ids.filter(i => i !== id) : [...ids, id])

  const generate = async () => {
    setLoading(true)
    try {
      const list = await getShoppingList(selectedIds)
      setShoppingList(list)
      setChecked({})
    } finally {
      setLoading(false)
    }
  }

  const toggleCheck = (name) => setChecked(c => ({ ...c, [name]: !c[name] }))

  const printList = () => window.print()

  if (shoppingList) {
    const unchecked = shoppingList.filter(i => !checked[i.name])
    const done = shoppingList.filter(i => checked[i.name])
    return (
      <div className="max-w-2xl">
        <div className="flex items-center justify-between mb-6 print:hidden">
          <h1 className="text-2xl font-bold text-gray-900">🛒 Liste de courses</h1>
          <div className="flex gap-2">
            <button onClick={printList} className="px-3 py-2 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg">🖨️ Imprimer</button>
            <button onClick={() => setShoppingList(null)} className="px-3 py-2 text-sm bg-orange-100 text-orange-700 hover:bg-orange-200 rounded-lg">← Modifier</button>
          </div>
        </div>
        <p className="text-sm text-gray-500 mb-4 print:hidden">{unchecked.length} article{unchecked.length !== 1 ? 's' : ''} restant{unchecked.length !== 1 ? 's' : ''}</p>

        <ul className="space-y-1">
          {unchecked.map(item => (
            <li key={item.name} onClick={() => toggleCheck(item.name)}
              className="flex items-center gap-3 p-3 bg-white rounded-xl border border-gray-100 cursor-pointer hover:border-orange-200 select-none">
              <span className="w-5 h-5 border-2 border-gray-300 rounded flex-shrink-0" />
              <div className="flex-1">
                <span className="font-medium">{item.name}</span>
                {(item.quantity || item.unit) && (
                  <span className="text-orange-600 ml-2 font-semibold">{[item.quantity, item.unit].filter(Boolean).join(' ')}</span>
                )}
              </div>
              {item.recipes.length > 0 && (
                <span className="text-xs text-gray-400 hidden sm:block">{item.recipes.slice(0, 2).join(', ')}</span>
              )}
            </li>
          ))}
        </ul>

        {done.length > 0 && (
          <>
            <p className="text-xs text-gray-400 mt-6 mb-2">Déjà dans le panier</p>
            <ul className="space-y-1 opacity-50">
              {done.map(item => (
                <li key={item.name} onClick={() => toggleCheck(item.name)}
                  className="flex items-center gap-3 p-3 bg-white rounded-xl border border-gray-100 cursor-pointer line-through select-none">
                  <span className="w-5 h-5 border-2 border-green-400 bg-green-100 rounded flex-shrink-0 flex items-center justify-center text-green-600 text-xs">✓</span>
                  <span>{item.name}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    )
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">🛒 Liste de courses</h1>
      <p className="text-gray-500 text-sm mb-6">Sélectionnez les recettes à cuisiner — la liste d'ingrédients sera générée automatiquement.</p>

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

      <button
        onClick={generate}
        disabled={selectedIds.length === 0 || loading}
        className="w-full py-3 bg-orange-600 hover:bg-orange-700 disabled:opacity-50 text-white font-semibold rounded-xl"
      >
        {loading ? 'Génération…' : `Générer la liste (${selectedIds.length} recette${selectedIds.length > 1 ? 's' : ''})`}
      </button>
    </div>
  )
}
