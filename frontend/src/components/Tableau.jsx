import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getMealPlans, getRecipe, getShoppingItems } from '../api'
import { useAssistant } from '../assistant/Assistant'

// Dates locales au format AAAA-MM-JJ (celles du planning).
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const JOURS = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam']

/**
 * Haut de l'accueil, en tuiles : le repas prévu aujourd'hui, les dîners des
 * 7 prochains jours, les courses et une idée à demander à l'assistant.
 */
export default function Tableau() {
  const { ouvrir, setDraft } = useAssistant()
  const today = new Date()
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(today)
    d.setDate(today.getDate() + i)
    return d
  })
  const from = iso(days[0])
  const to = iso(days[6])

  const { data: plans = [] } = useQuery({
    queryKey: ['meal-plans', { from, to }],
    queryFn: () => getMealPlans({ date_from: from, date_to: to }),
  })
  const { data: shopping } = useQuery({ queryKey: ['shopping-items'], queryFn: getShoppingItems })

  // Avant 14 h, le déjeuner d'abord ; ensuite le dîner.
  const todays = plans.filter(p => p.date === from)
  const order = today.getHours() < 14 ? ['déjeuner', 'dîner'] : ['dîner']
  const plan = order.map(m => todays.find(p => p.meal_type === m)).find(Boolean)
  const { data: recipe } = useQuery({
    queryKey: ['recipe', plan?.recipe_id],
    queryFn: () => getRecipe(plan.recipe_id),
    enabled: !!plan,
  })

  const items = shopping?.items || []
  const left = items.filter(i => !i.checked).length
  const done = items.length - left
  const firstFree = days.find(d => !plans.some(p => p.date === iso(d) && p.meal_type === 'dîner'))

  const demander = (question) => {
    setDraft(question)
    ouvrir()
  }

  const total = (recipe?.prep_time || 0) + (recipe?.cook_time || 0)

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 mb-10">
      {/* Ce soir */}
      <section aria-label="Repas prévu" className="lg:col-span-7 lg:row-span-2 relative overflow-hidden rounded-[32px] bg-[#2B1608] text-white p-7 flex flex-col gap-4 min-h-[340px]">
        <div aria-hidden="true" className="absolute -right-10 -top-10 w-36 h-36 sm:-right-12 sm:-top-12 sm:w-64 sm:h-64 rounded-full bg-[#3D2213] p-3 sm:p-5">
          {(recipe?.thumbnail_url || plan?.recipe_thumbnail) ? (
            <img src={recipe?.thumbnail_url || plan?.recipe_thumbnail} alt="" className="w-full h-full rounded-full object-cover" />
          ) : (
            <div className="w-full h-full rounded-full bg-[#E8762B]" />
          )}
        </div>
        <span className="self-start text-xs font-extrabold tracking-wider uppercase bg-orange-300 text-[#431407] px-3 py-1.5 rounded-full relative">
          {plan ? (plan.meal_type === 'déjeuner' ? 'Ce midi · déjeuner' : 'Ce soir · dîner') : 'Ce soir'}
        </span>
        {plan ? (
          <>
            <div className="relative max-w-md pr-20 sm:pr-0">
              <h2 className="font-display text-4xl sm:text-5xl font-extrabold leading-none tracking-tight">
                {recipe?.title || plan.recipe_title}
              </h2>
              <p className="mt-2 text-orange-100/90">
                {[total > 0 && `${total} min`, recipe?.servings && `${recipe.servings} portions`, recipe?.category]
                  .filter(Boolean).join(' · ')}
              </p>
            </div>
            {recipe?.ingredients?.length > 0 && (
              <ul className="relative flex flex-wrap gap-2">
                {recipe.ingredients.slice(0, 3).map((ing, i) => (
                  <li key={i} className="h-9 flex items-center rounded-full bg-[#3D2213] px-4 text-sm font-bold">
                    {[ing.quantity, ing.unit, ing.name].filter(Boolean).join(' ')}
                  </li>
                ))}
                {recipe.ingredients.length > 3 && (
                  <li className="h-9 flex items-center rounded-full bg-[#3D2213] px-4 text-sm font-bold">
                    + {recipe.ingredients.length - 3} autre{recipe.ingredients.length - 3 > 1 ? 's' : ''}
                  </li>
                )}
              </ul>
            )}
            <div className="relative mt-auto flex flex-wrap gap-3">
              <Link to={`/recettes/${plan.recipe_id}/cuisine`}
                className="h-14 inline-flex items-center rounded-full bg-orange-300 text-[#431407] px-7 text-lg font-black hover:bg-orange-200 transition-colors">
                Lancer le mode cuisine
              </Link>
              <Link to={`/recettes/${plan.recipe_id}`}
                className="h-14 inline-flex items-center rounded-full border-2 border-white/30 px-6 font-bold hover:border-white/60 transition-colors">
                Voir la recette
              </Link>
            </div>
          </>
        ) : (
          <>
            <div className="relative max-w-md pr-20 sm:pr-0">
              <h2 className="font-display text-4xl font-extrabold leading-none tracking-tight">Rien de prévu pour l'instant</h2>
              <p className="mt-3 text-orange-100/90">Choisis une recette dans le planning, ou demande une idée avec ce qu'il te reste.</p>
            </div>
            <div className="relative mt-auto flex flex-wrap gap-3">
              <button onClick={() => demander('Une idée pour ce soir, avec mes recettes ?')}
                className="h-14 inline-flex items-center rounded-full bg-orange-300 text-[#431407] px-7 text-lg font-black hover:bg-orange-200 transition-colors">
                Une idée ?
              </button>
              <Link to="/planning"
                className="h-14 inline-flex items-center rounded-full border-2 border-white/30 px-6 font-bold hover:border-white/60 transition-colors">
                Planifier
              </Link>
            </div>
          </>
        )}
      </section>

      {/* Dîners de la semaine */}
      <section aria-label="Dîners de la semaine" className="lg:col-span-5 lg:row-span-2 rounded-[32px] bg-sky-100 text-[#13223F] p-6 flex flex-col gap-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="font-extrabold">Dîners de la semaine</h2>
          <Link to="/planning" className="text-sm font-bold text-[#1F3A6B] hover:underline">Planning</Link>
        </div>
        <ul className="flex flex-col gap-1.5">
          {days.map(d => {
            const dinner = plans.find(p => p.date === iso(d) && p.meal_type === 'dîner')
            return (
              <li key={iso(d)} className="flex items-center gap-3 min-h-11">
                <span className="w-10 text-sm font-extrabold uppercase">{JOURS[d.getDay()]}</span>
                {dinner ? (
                  <Link to={`/recettes/${dinner.recipe_id}`}
                    className="flex-1 min-h-10 flex items-center rounded-xl bg-white px-3.5 text-[15px] font-bold hover:bg-sky-50 truncate">
                    {dinner.recipe_title || 'Recette'}
                  </Link>
                ) : (
                  <button onClick={() => demander(`Une idée de dîner pour ${d.toLocaleDateString('fr-FR', { weekday: 'long' })} ?`)}
                    className="flex-1 min-h-10 flex items-center rounded-xl border-2 border-dashed border-sky-400/70 px-3.5 text-[15px] font-bold text-[#1F3A6B] hover:bg-white/60 text-left">
                    Libre : proposer une idée
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      </section>

      {/* Courses */}
      <Link to="/courses" aria-label="Liste de courses" className="lg:col-span-4 rounded-[32px] bg-amber-100 text-[#3D2E00] p-6 flex flex-col gap-3 hover:bg-amber-200/70 transition-colors">
        <h2 className="font-extrabold">Courses</h2>
        <span className="font-display text-4xl font-extrabold leading-none tracking-tight">
          {items.length === 0 ? 'Liste vide' : left === 0 ? 'Tout est pris' : `${left} à prendre`}
        </span>
        {items.length > 0 && (
          <div className="h-2.5 rounded-full bg-amber-200 overflow-hidden" aria-hidden="true">
            <div className="h-full rounded-full bg-[#3D2E00]" style={{ width: `${Math.round(done / items.length * 100)}%` }} />
          </div>
        )}
        <p className="text-sm font-semibold">
          {items.length > 0 ? `${done} sur ${items.length} dans le panier` : 'Ajoute les recettes de la semaine depuis le planning.'}
        </p>
      </Link>

      {/* Frigo */}
      <Link to="/frigo" className="lg:col-span-4 rounded-[32px] bg-white border border-orange-100 p-6 flex flex-col gap-3 hover:border-orange-300 transition-colors">
        <h2 className="font-extrabold">Frigo</h2>
        <p className="font-display text-2xl font-extrabold leading-tight">Que faire avec ce qu'il me reste ?</p>
        <span className="mt-auto text-sm font-bold text-orange-700">Choisir mes ingrédients →</span>
      </Link>

      {/* Idée de l'assistant */}
      <section aria-label="Idée de l'assistant" className="lg:col-span-4 rounded-[32px] bg-green-100 text-[#17301A] p-6 flex flex-col gap-3">
        <span className="text-sm font-extrabold uppercase tracking-wider">✦ Idée</span>
        <p className="text-lg font-bold leading-snug">
          {firstFree
            ? `${iso(firstFree) === from ? 'Ce soir' : firstFree.toLocaleDateString('fr-FR', { weekday: 'long' }).replace(/^./, c => c.toUpperCase())} est libre : on te propose quelque chose ?`
            : 'La semaine est complète. Une liste de courses pour tout ça ?'}
        </p>
        <button
          onClick={() => demander(firstFree
            ? `Propose-moi un dîner pour ${firstFree.toLocaleDateString('fr-FR', { weekday: 'long' })}, et ajoute-le au planning.`
            : 'Ajoute aux courses les ingrédients des dîners de la semaine.')}
          className="mt-auto self-start h-11 inline-flex items-center rounded-full bg-[#17301A] text-white px-5 font-bold hover:bg-[#24482a] transition-colors">
          Demander à l'assistant
        </button>
      </section>
    </div>
  )
}
