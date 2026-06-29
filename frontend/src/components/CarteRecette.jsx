import { Link } from 'react-router-dom'

const ICONS = { video: '🎬', web: '🌐', text: '📝', manual: '✏️' }

export default function CarteRecette({ recipe }) {
  const totalTime = (recipe.prep_time || 0) + (recipe.cook_time || 0)

  return (
    <Link
      to={`/recettes/${recipe.id}`}
      className="group bg-white rounded-2xl shadow-sm hover:shadow-md transition-shadow overflow-hidden flex flex-col"
    >
      <div className="aspect-video bg-orange-50 relative overflow-hidden">
        {recipe.thumbnail_url ? (
          <img
            src={recipe.thumbnail_url}
            alt={recipe.title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-5xl">🍽️</div>
        )}
        <span className="absolute top-2 right-2 text-lg" title={recipe.source_type}>
          {ICONS[recipe.source_type] || '📄'}
        </span>
      </div>
      <div className="p-4 flex flex-col flex-1">
        <h3 className="font-semibold text-gray-900 line-clamp-2 mb-2 group-hover:text-orange-600 transition-colors">
          {recipe.title}
        </h3>
        {recipe.description && (
          <p className="text-sm text-gray-500 line-clamp-2 mb-3">{recipe.description}</p>
        )}
        <div className="mt-auto flex items-center gap-3 text-xs text-gray-400">
          {totalTime > 0 && <span>⏱ {totalTime} min</span>}
          {recipe.servings && <span>👥 {recipe.servings} pers.</span>}
          {recipe.tags?.slice(0, 2).map(tag => (
            <span key={tag} className="bg-orange-50 text-orange-600 px-2 py-0.5 rounded-full">
              {tag}
            </span>
          ))}
        </div>
      </div>
    </Link>
  )
}
