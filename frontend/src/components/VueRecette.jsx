// Recette en lecture seule, pour les pages publiques (pas de compte).
export default function VueRecette({ recipe }) {
  const total = (recipe.prep_time || 0) + (recipe.cook_time || 0)
  return (
    <article className="max-w-3xl">
      <h1 className="text-3xl font-bold text-gray-900">{recipe.title}</h1>
      {recipe.description && <p className="text-gray-500 mt-2">{recipe.description}</p>}
      {recipe.thumbnail_url && (
        <img src={recipe.thumbnail_url} alt={recipe.title} className="w-full aspect-video object-cover rounded-2xl my-6" />
      )}
      <div className="flex flex-wrap gap-4 my-6 p-4 bg-white rounded-xl border border-gray-100 text-sm">
        {recipe.prep_time > 0 && <span>🔪 Préparation {recipe.prep_time} min</span>}
        {recipe.cook_time > 0 && <span>🔥 Cuisson {recipe.cook_time} min</span>}
        {total > 0 && <span>⏱ Total {total} min</span>}
        {recipe.servings && <span>👥 {recipe.servings} pers.</span>}
        {recipe.category && <span className="capitalize">🏷️ {recipe.category}</span>}
      </div>
      {recipe.ingredients?.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xl font-bold text-gray-900 mb-4">Ingrédients</h2>
          <ul className="bg-white rounded-xl border border-gray-100 divide-y divide-gray-50">
            {recipe.ingredients.map((ing, i) => (
              <li key={i} className="flex items-baseline gap-2 px-4 py-3">
                <span className="font-semibold text-orange-600 w-24 text-right flex-shrink-0">
                  {[ing.quantity, ing.unit].filter(Boolean).join(' ')}
                </span>
                <span className="text-gray-900">{ing.name}</span>
                {ing.notes && <span className="text-gray-400 text-sm">({ing.notes})</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {recipe.steps?.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xl font-bold text-gray-900 mb-4">Préparation</h2>
          <ol className="space-y-5">
            {recipe.steps.map((step, i) => (
              <li key={i} className="flex gap-4">
                <span className="flex-shrink-0 w-8 h-8 bg-orange-600 text-white rounded-full flex items-center justify-center font-bold text-sm">
                  {step.order || i + 1}
                </span>
                <p className="text-gray-700 flex-1">{step.text}</p>
              </li>
            ))}
          </ol>
        </section>
      )}
      {recipe.source_url && (
        <p className="text-sm text-gray-400">
          Source : <a href={recipe.source_url} target="_blank" rel="noopener noreferrer" className="text-orange-600 hover:underline break-all">{recipe.source_url}</a>
        </p>
      )}
    </article>
  )
}
