import { Link } from 'react-router-dom'


const SOURCES = { video: 'Vidéo', web: 'Site', text: 'Texte', manual: 'Maison' }

/** Carte d'une recette : grande photo arrondie avec sa source et le favori, puis titre et durée. */
export default function CarteRecette({ recipe }) {
  const totalTime = (recipe.prep_time || 0) + (recipe.cook_time || 0)
  const source = SOURCES[recipe.source_type]
  const meta = [totalTime > 0 && `${totalTime} min`, recipe.category && recipe.category[0].toUpperCase() + recipe.category.slice(1)]
    .filter(Boolean).join(' · ')

  return (
    <Link to={`/recettes/${recipe.id}`} className="group flex flex-col gap-2.5 rounded-3xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500">
      <div className="aspect-[1.1] rounded-[22px] bg-orange-100 relative overflow-hidden">
        {recipe.thumbnail_url ? (
          <img
            src={recipe.thumbnail_url}
            alt=""
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-5xl" aria-hidden="true">🍽️</div>
        )}
        {recipe.shared_by_name && (
          <span className="absolute top-2.5 left-2.5 px-2.5 py-1 bg-gray-900 text-white text-xs font-extrabold rounded-full max-w-[70%] truncate"
            title={`Partagée par ${recipe.shared_by_name}`}>
            De {recipe.shared_by_name}
          </span>
        )}
        {recipe.is_favorite && (
          <span className="absolute top-2.5 right-2.5 w-8 h-8 rounded-full bg-white text-orange-700 flex items-center justify-center" title="Favori">
            <span aria-hidden="true">♥</span><span className="sr-only">Favori</span>
          </span>
        )}
        {source && (
          <span className="absolute bottom-2.5 left-2.5 px-2.5 py-1 bg-white/90 text-gray-900 text-xs font-extrabold rounded-full">
            {source}
          </span>
        )}
      </div>
      <div className="px-1">
        <h3 className="font-extrabold text-gray-900 leading-snug line-clamp-2 group-hover:text-orange-700 transition-colors">
          {recipe.title}
        </h3>
        <p className="mt-0.5 flex items-center gap-2 text-sm font-semibold text-gray-500">
          {meta && <span>{totalTime > 0 && '⏱ '}{meta}</span>}
          {recipe.rating > 0 && <span className="text-orange-700" title={`${recipe.rating}/5`}>★ {recipe.rating}</span>}
          {recipe.cook_again && <span title="À refaire">🔁</span>}
        </p>
      </div>
    </Link>
  )
}
