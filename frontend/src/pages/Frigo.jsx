import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { whatToCook } from '../api'

const CLE = 'popote.frigo'

function lireFrigo() {
  try { return JSON.parse(localStorage.getItem(CLE)) || [] } catch { return [] }
}

// « Qu'est-ce que je cuisine ? » : ce qu'il y a dans le frigo → recettes
// classées par ce qu'il manque.
export default function Frigo() {
  const [items, setItems] = useState(lireFrigo)
  const [saisie, setSaisie] = useState('')
  const [compterBase, setCompterBase] = useState(false)
  const search = useMutation({ mutationFn: whatToCook })

  const enregistrer = (next) => {
    setItems(next)
    try { localStorage.setItem(CLE, JSON.stringify(next)) } catch { /* mode privé */ }
  }
  const ajouter = (e) => {
    e.preventDefault()
    // Plusieurs ingrédients d'un coup : « tomates, œufs, feta »
    const nouveaux = saisie.split(/[,;\n]/).map(s => s.trim()).filter(Boolean)
      .filter(s => !items.some(i => i.toLowerCase() === s.toLowerCase()))
    if (nouveaux.length) enregistrer([...items, ...nouveaux])
    setSaisie('')
  }
  const chercher = () => search.mutate({ ingredients: items, assume_staples: !compterBase })

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-1">🧊 Qu'est-ce que je cuisine ?</h1>
      <p className="text-gray-500 text-sm mb-6">Indiquez ce que vous avez sous la main : vos recettes sont classées selon ce qu'il manque.</p>

      <form onSubmit={ajouter} className="flex gap-2 mb-3">
        <input value={saisie} onChange={e => setSaisie(e.target.value)} autoFocus
          placeholder="tomates, œufs, feta…"
          className="flex-1 px-4 py-2.5 rounded-xl border border-gray-200 bg-white focus:outline-none focus:ring-2 focus:ring-orange-400" />
        <button className="px-4 py-2.5 bg-orange-100 text-orange-700 rounded-xl font-medium hover:bg-orange-200">Ajouter</button>
      </form>

      <div className="flex flex-wrap gap-2 mb-4">
        {items.map(item => (
          <span key={item} className="inline-flex items-center gap-1 pl-3 pr-2 py-1 bg-white border border-gray-200 rounded-full text-sm">
            {item}
            <button onClick={() => enregistrer(items.filter(i => i !== item))} className="text-gray-400 hover:text-red-500 px-1">×</button>
          </span>
        ))}
        {items.length > 0 && (
          <button onClick={() => enregistrer([])} className="text-xs text-red-500 hover:underline">Tout vider</button>
        )}
      </div>

      <label className="flex items-center gap-2 text-sm text-gray-500 mb-4">
        <input type="checkbox" checked={compterBase} onChange={e => setCompterBase(e.target.checked)} className="accent-orange-600" />
        Je n'ai pas forcément sel, poivre et huile
      </label>

      <button onClick={chercher} disabled={!items.length || search.isPending}
        className="w-full py-3 bg-orange-600 hover:bg-orange-700 disabled:opacity-50 text-white font-semibold rounded-xl mb-8">
        {search.isPending ? 'Recherche…' : 'Trouver des recettes'}
      </button>

      {search.isError && <p className="text-red-600 text-sm">Recherche impossible, réessayez.</p>}
      {search.data && (search.data.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <div className="text-5xl mb-3">🤷</div>
          <p>Aucune recette n'utilise ces ingrédients.</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {search.data.map(({ recipe, matched, missing, coverage }) => (
            <li key={recipe.id}>
              <Link to={`/recettes/${recipe.id}`}
                className="flex gap-4 p-3 bg-white rounded-2xl border border-gray-100 hover:border-orange-300 hover:shadow-sm">
                {recipe.thumbnail_url
                  ? <img src={recipe.thumbnail_url} alt="" className="w-20 h-20 rounded-xl object-cover flex-shrink-0" />
                  : <span className="w-20 h-20 rounded-xl bg-orange-50 flex items-center justify-center text-3xl flex-shrink-0">🍽️</span>}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-semibold text-gray-900 truncate">{recipe.title}</p>
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full flex-shrink-0 ${
                      missing.length === 0 ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'
                    }`}>
                      {missing.length === 0 ? 'Tout est là !' : `Il manque ${missing.length}`}
                    </span>
                  </div>
                  <div className="h-1.5 bg-gray-100 rounded-full mt-2 mb-2">
                    <div className="h-1.5 bg-green-500 rounded-full" style={{ width: `${Math.round(coverage * 100)}%` }} />
                  </div>
                  <p className="text-xs text-green-700 line-clamp-1">✓ {matched.join(', ')}</p>
                  {missing.length > 0 && <p className="text-xs text-gray-400 line-clamp-1">✗ {missing.join(', ')}</p>}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      ))}
    </div>
  )
}
