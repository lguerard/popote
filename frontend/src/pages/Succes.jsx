import { useQuery } from '@tanstack/react-query'
import { getAchievements } from '../api'

const CATEGORY_LABELS = {
  collection: '📚 Collection',
  cuisine: '🍳 Cuisine',
  organisation: '📅 Organisation',
  decouverte: '🌍 Découverte',
  perfectionniste: '✨ Perfectionniste',
}

export default function Succes() {
  const { data: achievements = [], isLoading } = useQuery({
    queryKey: ['achievements'],
    queryFn: getAchievements,
  })

  const grouped = achievements.reduce((acc, a) => {
    if (!acc[a.category]) acc[a.category] = []
    acc[a.category].push(a)
    return acc
  }, {})

  const total = achievements.length
  const unlocked = achievements.filter(a => a.unlocked_at).length

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">🏆 Succès</h1>
        <div className="flex items-center gap-3">
          <div className="flex-1 bg-gray-200 rounded-full h-3">
            <div
              className="bg-orange-500 h-3 rounded-full transition-all"
              style={{ width: `${total ? (unlocked / total) * 100 : 0}%` }}
            />
          </div>
          <span className="text-sm font-semibold text-gray-600">{unlocked}/{total}</span>
        </div>
      </div>

      {isLoading && <p className="text-gray-500">Chargement…</p>}

      {Object.entries(CATEGORY_LABELS).map(([cat, label]) => {
        const items = grouped[cat] || []
        if (!items.length) return null
        return (
          <div key={cat} className="mb-8">
            <h2 className="text-lg font-bold mb-3 text-gray-700">{label}</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {items.map(a => (
                <AchievementCard key={a.id} achievement={a} />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function AchievementCard({ achievement: a }) {
  const done = !!a.unlocked_at
  const progress = Math.min(a.progress / a.goal, 1)

  return (
    <div className={`rounded-xl border p-4 flex gap-4 items-start transition-all ${
      done ? 'border-orange-400 bg-orange-50' : 'border-gray-200 bg-white opacity-60'
    }`}>
      <span className={`text-3xl ${done ? '' : 'grayscale'}`}>{a.icon}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <p className="font-bold text-sm truncate">{a.name}</p>
          {done && (
            <span className="text-xs text-orange-600 font-medium whitespace-nowrap">
              {new Date(a.unlocked_at).toLocaleDateString('fr-FR')}
            </span>
          )}
        </div>
        <p className="text-xs text-gray-500 mb-2">{a.description}</p>
        {a.goal > 1 && (
          <div className="flex items-center gap-2">
            <div className="flex-1 bg-gray-200 rounded-full h-1.5">
              <div
                className="bg-orange-400 h-1.5 rounded-full"
                style={{ width: `${progress * 100}%` }}
              />
            </div>
            <span className="text-xs text-gray-400">{Math.min(a.progress, a.goal)}/{a.goal}</span>
          </div>
        )}
      </div>
    </div>
  )
}
