import { useState, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getRecipes } from '../api'
import CarteRecette from '../components/CarteRecette'

const CATEGORIES = [
  { value: 'favoris', label: 'Favoris', emoji: '❤️' },
  { value: null, label: 'Tout', emoji: '🍽️' },
  { value: 'petit-déjeuner', label: 'Petit-déj', emoji: '☕' },
  { value: 'entrée', label: 'Entrée', emoji: '🥗' },
  { value: 'plat', label: 'Plat', emoji: '🍲' },
  { value: 'dessert', label: 'Dessert', emoji: '🍰' },
  { value: 'snack', label: 'Snack', emoji: '🥨' },
  { value: 'soupe', label: 'Soupe', emoji: '🍜' },
  { value: 'apéritif', label: 'Apéritif', emoji: '🥂' },
  { value: 'boisson', label: 'Boisson', emoji: '🥤' },
  { value: 'sauce', label: 'Sauce', emoji: '🫙' },
]

const TIME_FILTERS = [
  { value: null, label: 'Tout' },
  { value: 30, label: '≤ 30 min' },
  { value: 60, label: '≤ 1h' },
]

const SOURCE_FILTERS = [
  { value: null, label: 'Tout', emoji: '🌐' },
  { value: 'video', label: 'Vidéo', emoji: '🎬' },
  { value: 'web', label: 'Site', emoji: '🌐' },
  { value: 'text', label: 'Texte', emoji: '📝' },
  { value: 'manual', label: 'Manuel', emoji: '✏️' },
]

export default function Accueil() {
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [category, setCategory] = useState(null)
  const [maxTime, setMaxTime] = useState(null)
  const [sourceType, setSourceType] = useState(null)
  const timerRef = useRef(null)

  const filters = {
    ...(debouncedSearch && { search: debouncedSearch }),
    ...(category === 'favoris' ? { favorites_only: true } : category ? { category } : {}),
    ...(maxTime && { max_time: maxTime }),
    ...(sourceType && { source_type: sourceType }),
    limit: 100,
  }

  const { data: recipes = [], isLoading } = useQuery({
    queryKey: ['recipes', filters],
    queryFn: () => getRecipes(filters),
  })

  const handleSearch = (val) => {
    setSearch(val)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setDebouncedSearch(val), 400)
  }

  const activeFilters = [category, maxTime, sourceType].filter(Boolean).length

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900 mb-1">Mes Recettes</h1>
        <p className="text-gray-400 text-sm">{recipes.length} recette{recipes.length !== 1 ? 's' : ''}</p>
      </div>

      {/* Recherche */}
      <div className="mb-4">
        <input
          type="search"
          placeholder="Rechercher une recette…"
          value={search}
          onChange={(e) => handleSearch(e.target.value)}
          className="w-full max-w-lg px-4 py-2.5 rounded-xl border border-gray-200 bg-white shadow-sm focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-transparent"
        />
      </div>

      {/* Filtres catégories */}
      <div className="mb-3 flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.value ?? 'all'}
            onClick={() => setCategory(cat.value)}
            className={`flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
              category === cat.value
                ? 'bg-orange-600 text-white shadow-sm'
                : 'bg-white text-gray-600 border border-gray-200 hover:border-orange-300 hover:text-orange-600'
            }`}
          >
            <span>{cat.emoji}</span>
            <span>{cat.label}</span>
          </button>
        ))}
      </div>

      {/* Filtres secondaires */}
      <div className="mb-6 flex flex-wrap gap-3 items-center">
        <div className="flex gap-1.5">
          {TIME_FILTERS.map((t) => (
            <button
              key={t.value ?? 'all'}
              onClick={() => setMaxTime(t.value)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                maxTime === t.value
                  ? 'bg-amber-100 text-amber-800 border border-amber-300'
                  : 'bg-white text-gray-500 border border-gray-200 hover:border-amber-200'
              }`}
            >
              ⏱ {t.label}
            </button>
          ))}
        </div>
        <div className="flex gap-1.5">
          {SOURCE_FILTERS.map((s) => (
            <button
              key={s.value ?? 'all'}
              onClick={() => setSourceType(s.value)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                sourceType === s.value
                  ? 'bg-blue-50 text-blue-700 border border-blue-200'
                  : 'bg-white text-gray-500 border border-gray-200 hover:border-blue-200'
              }`}
            >
              {s.emoji} {s.label}
            </button>
          ))}
        </div>
        {activeFilters > 0 && (
          <button
            onClick={() => { setCategory(null); setMaxTime(null); setSourceType(null) }}
            className="text-xs text-red-500 hover:text-red-700 underline"
          >
            Réinitialiser ({activeFilters})
          </button>
        )}
      </div>

      {/* Grille */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="bg-white rounded-2xl shadow-sm overflow-hidden animate-pulse">
              <div className="aspect-video bg-gray-100" />
              <div className="p-4 space-y-2">
                <div className="h-4 bg-gray-100 rounded w-3/4" />
                <div className="h-3 bg-gray-100 rounded w-1/2" />
              </div>
            </div>
          ))}
        </div>
      ) : recipes.length === 0 ? (
        <div className="text-center py-24 text-gray-400">
          <div className="text-6xl mb-4">🔍</div>
          <p className="text-xl font-medium text-gray-500">Aucune recette trouvée</p>
          <p className="mt-2 text-sm">Essayez d'autres filtres ou ajoutez une nouvelle recette.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {recipes.map((r) => (
            <CarteRecette key={r.id} recipe={r} />
          ))}
        </div>
      )}
    </div>
  )
}
