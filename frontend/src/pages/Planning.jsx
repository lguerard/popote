import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMealPlans, createMealPlan, deleteMealPlan, getRecipes } from '../api'

const DAYS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
const MEAL_TYPES = [
  { value: 'petit-déjeuner', label: 'Matin', emoji: '☕' },
  { value: 'déjeuner', label: 'Midi', emoji: '🍽️' },
  { value: 'dîner', label: 'Soir', emoji: '🌙' },
  { value: 'snack', label: 'Snack', emoji: '🥨' },
]

function getWeekDates(offset = 0) {
  const now = new Date()
  const day = now.getDay() || 7
  const monday = new Date(now)
  monday.setDate(now.getDate() - day + 1 + offset * 7)
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(monday)
    d.setDate(monday.getDate() + i)
    return d
  })
}

function fmt(date) { return date.toISOString().split('T')[0] }

export default function Planning() {
  const [weekOffset, setWeekOffset] = useState(0)
  const [picker, setPicker] = useState(null) // {date, meal_type}
  const [search, setSearch] = useState('')
  const qc = useQueryClient()

  const days = getWeekDates(weekOffset)
  const dateFrom = fmt(days[0])
  const dateTo = fmt(days[6])

  const { data: plans = [] } = useQuery({
    queryKey: ['meal-plans', dateFrom, dateTo],
    queryFn: () => getMealPlans({ date_from: dateFrom, date_to: dateTo }),
  })

  const { data: recipes = [] } = useQuery({
    queryKey: ['recipes', { search, limit: 20 }],
    queryFn: () => getRecipes({ search: search || undefined, limit: 20 }),
    enabled: !!picker,
  })

  const addMutation = useMutation({
    mutationFn: createMealPlan,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['meal-plans'] }); setPicker(null); setSearch('') },
  })

  const removeMutation = useMutation({
    mutationFn: deleteMealPlan,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['meal-plans'] }),
  })

  const getPlansFor = (date, mealType) =>
    plans.filter(p => p.date === fmt(date) && p.meal_type === mealType)

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">📅 Planning des repas</h1>
        <div className="flex items-center gap-2">
          <button onClick={() => setWeekOffset(w => w - 1)} className="px-3 py-1.5 bg-white border border-gray-200 rounded-lg hover:border-orange-300">←</button>
          <button onClick={() => setWeekOffset(0)} className="px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-sm hover:border-orange-300">Aujourd'hui</button>
          <button onClick={() => setWeekOffset(w => w + 1)} className="px-3 py-1.5 bg-white border border-gray-200 rounded-lg hover:border-orange-300">→</button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse min-w-[700px]">
          <thead>
            <tr>
              <th className="w-20 p-2 text-left text-xs text-gray-400 font-medium">Repas</th>
              {days.map((d, i) => (
                <th key={i} className={`p-2 text-center text-sm font-semibold ${fmt(d) === fmt(new Date()) ? 'text-orange-600' : 'text-gray-700'}`}>
                  <div>{DAYS[i]}</div>
                  <div className={`text-xs font-normal ${fmt(d) === fmt(new Date()) ? 'text-orange-400' : 'text-gray-400'}`}>
                    {d.getDate()}/{d.getMonth() + 1}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {MEAL_TYPES.map(meal => (
              <tr key={meal.value} className="border-t border-gray-100">
                <td className="p-2 text-xs text-gray-500 font-medium whitespace-nowrap">
                  {meal.emoji} {meal.label}
                </td>
                {days.map((d, di) => {
                  const cell = getPlansFor(d, meal.value)
                  return (
                    <td key={di} className="p-1 align-top">
                      <div className="min-h-[60px] space-y-1">
                        {cell.map(plan => (
                          <div key={plan.id} className="group relative bg-orange-50 border border-orange-200 rounded-lg p-1.5 text-xs">
                            {plan.recipe_thumbnail && (
                              <img src={plan.recipe_thumbnail} alt="" className="w-full h-10 object-cover rounded mb-1" />
                            )}
                            <p className="font-medium text-gray-800 line-clamp-2">{plan.recipe_title}</p>
                            <button
                              onClick={() => removeMutation.mutate(plan.id)}
                              className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-600 text-xs"
                            >×</button>
                          </div>
                        ))}
                        <button
                          onClick={() => setPicker({ date: fmt(d), meal_type: meal.value })}
                          className="w-full text-center text-gray-300 hover:text-orange-400 hover:bg-orange-50 rounded-lg py-1 text-lg transition-colors"
                        >+</button>
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Recipe picker modal */}
      {picker && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-md shadow-xl">
            <div className="flex items-center justify-between p-4 border-b">
              <h3 className="font-semibold">Ajouter une recette</h3>
              <button onClick={() => { setPicker(null); setSearch('') }} className="text-gray-400 hover:text-gray-600 text-xl">×</button>
            </div>
            <div className="p-4">
              <input
                autoFocus
                type="search"
                placeholder="Rechercher…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-200 mb-3 focus:outline-none focus:ring-2 focus:ring-orange-400 text-sm"
              />
              <div className="space-y-1 max-h-72 overflow-y-auto">
                {recipes.map(r => (
                  <button
                    key={r.id}
                    onClick={() => addMutation.mutate({
                      date: picker.date,
                      meal_type: picker.meal_type,
                      recipe_id: r.id,
                      recipe_title: r.title,
                      recipe_thumbnail: r.thumbnail_url,
                    })}
                    className="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-orange-50 text-left"
                  >
                    {r.thumbnail_url
                      ? <img src={r.thumbnail_url} alt="" className="w-10 h-10 rounded-lg object-cover flex-shrink-0" />
                      : <span className="w-10 h-10 rounded-lg bg-orange-100 flex items-center justify-center text-xl">🍽️</span>
                    }
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{r.title}</p>
                      <p className="text-xs text-gray-400">{r.category || ''}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
