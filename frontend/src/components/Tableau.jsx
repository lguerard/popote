import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getMealPlans, getRecipe, getShoppingItems } from '../api'
import { useAssistant } from '../assistant/Assistant'
import { useAuth } from '../auth'
import { libelleCategorie } from '../i18n'
import { contenuAffiche, DELAI_RELECTURE_TRADUCTION } from '../contenuRecette'

// Dates locales au format AAAA-MM-JJ (celles du planning).
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/**
 * Haut de l'accueil, en tuiles : le repas prévu aujourd'hui, les dîners des
 * 7 prochains jours, les courses et une idée à demander à l'assistant.
 */
export default function Tableau() {
  const { ouvrir, setDraft } = useAssistant()
  const { t, lang } = useAuth()
  const weekday = (d) => d.toLocaleDateString(t('common.locale'), { weekday: 'long' })
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
  const { data: brute } = useQuery({
    queryKey: ['recipe', plan?.recipe_id],
    queryFn: () => getRecipe(plan.recipe_id),
    enabled: !!plan,
    refetchInterval: (query) => (query.state.data?.translation_pending ? DELAI_RELECTURE_TRADUCTION : false),
  })
  // Affichage seulement : dans la langue du compte quand elle est traduite.
  const recipe = brute && contenuAffiche(brute)

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
      <section aria-label={t('tableau.plannedMeal')} className="lg:col-span-7 lg:row-span-2 relative overflow-hidden rounded-[32px] bg-[#2B1608] text-white p-7 flex flex-col gap-4 min-h-[340px]">
        <div aria-hidden="true" className="absolute -right-10 -top-10 w-36 h-36 sm:-right-12 sm:-top-12 sm:w-64 sm:h-64 rounded-full bg-[#3D2213] p-3 sm:p-5">
          {(recipe?.thumbnail_url || plan?.recipe_thumbnail) ? (
            <img src={recipe?.thumbnail_url || plan?.recipe_thumbnail} alt="" className="w-full h-full rounded-full object-cover" />
          ) : (
            <div className="w-full h-full rounded-full bg-[#E8762B]" />
          )}
        </div>
        <span className="self-start text-xs font-extrabold tracking-wider uppercase bg-orange-300 text-[#431407] px-3 py-1.5 rounded-full relative">
          {plan ? (plan.meal_type === 'déjeuner' ? t('tableau.lunchBadge') : t('tableau.dinnerBadge')) : t('tableau.tonight')}
        </span>
        {plan ? (
          <>
            <div className="relative max-w-md pr-20 sm:pr-0">
              <h2 className="font-display text-4xl sm:text-5xl font-extrabold leading-none tracking-tight">
                {recipe?.title || plan.recipe_title}
              </h2>
              <p className="mt-2 text-orange-100/90">
                {[total > 0 && `${total} min`, recipe?.servings && t('tableau.servings', { n: recipe.servings }), recipe?.category && libelleCategorie(lang, recipe.category)]
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
                    {t(recipe.ingredients.length - 3 > 1 ? 'tableau.moreMany' : 'tableau.moreOne', { n: recipe.ingredients.length - 3 })}
                  </li>
                )}
              </ul>
            )}
            <div className="relative mt-auto flex flex-wrap gap-3">
              <Link to={`/recettes/${plan.recipe_id}/cuisine`}
                className="h-14 inline-flex items-center rounded-full bg-orange-300 text-[#431407] px-7 text-lg font-black hover:bg-orange-200 transition-colors">
                {t('tableau.startCooking')}
              </Link>
              <Link to={`/recettes/${plan.recipe_id}`}
                className="h-14 inline-flex items-center rounded-full border-2 border-white/30 px-6 font-bold hover:border-white/60 transition-colors">
                {t('tableau.seeRecipe')}
              </Link>
            </div>
          </>
        ) : (
          <>
            <div className="relative max-w-md pr-20 sm:pr-0">
              <h2 className="font-display text-4xl font-extrabold leading-none tracking-tight">{t('tableau.nothingPlanned')}</h2>
              <p className="mt-3 text-orange-100/90">{t('tableau.nothingPlannedHint')}</p>
            </div>
            <div className="relative mt-auto flex flex-wrap gap-3">
              <button onClick={() => demander(t('tableau.askTonight'))}
                className="h-14 inline-flex items-center rounded-full bg-orange-300 text-[#431407] px-7 text-lg font-black hover:bg-orange-200 transition-colors">
                {t('tableau.anIdea')}
              </button>
              <Link to="/planning"
                className="h-14 inline-flex items-center rounded-full border-2 border-white/30 px-6 font-bold hover:border-white/60 transition-colors">
                {t('tableau.plan')}
              </Link>
            </div>
          </>
        )}
      </section>

      {/* Dîners de la semaine */}
      <section aria-label={t('tableau.weekDinners')} className="lg:col-span-5 lg:row-span-2 rounded-[32px] bg-sky-100 text-[#13223F] p-6 flex flex-col gap-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="font-extrabold">{t('tableau.weekDinners')}</h2>
          <Link to="/planning" className="text-sm font-bold text-[#1F3A6B] hover:underline">{t('nav.planning')}</Link>
        </div>
        <ul className="flex flex-col gap-1.5">
          {days.map(d => {
            const dinner = plans.find(p => p.date === iso(d) && p.meal_type === 'dîner')
            return (
              <li key={iso(d)} className="flex items-center gap-3 min-h-11">
                <span className="w-10 text-sm font-extrabold uppercase">{t(`tableau.day${d.getDay()}`)}</span>
                {dinner ? (
                  <Link to={`/recettes/${dinner.recipe_id}`}
                    className="flex-1 min-h-10 flex items-center rounded-xl bg-white px-3.5 text-[15px] font-bold hover:bg-sky-50 truncate">
                    {dinner.recipe_title || t('tableau.recipe')}
                  </Link>
                ) : (
                  <button onClick={() => demander(t('tableau.askDinnerFor', { day: weekday(d) }))}
                    className="flex-1 min-h-10 flex items-center rounded-xl border-2 border-dashed border-sky-400/70 px-3.5 text-[15px] font-bold text-[#1F3A6B] hover:bg-white/60 text-left">
                    {t('tableau.freeSuggest')}
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      </section>

      {/* Courses */}
      <Link to="/courses" aria-label={t('tableau.shoppingList')} className="lg:col-span-4 rounded-[32px] bg-amber-100 text-[#3D2E00] p-6 flex flex-col gap-3 hover:bg-amber-200/70 transition-colors">
        <h2 className="font-extrabold">{t('nav.shopping')}</h2>
        <span className="font-display text-4xl font-extrabold leading-none tracking-tight">
          {items.length === 0 ? t('tableau.emptyList') : left === 0 ? t('tableau.allPicked') : t('tableau.toPick', { n: left })}
        </span>
        {items.length > 0 && (
          <div className="h-2.5 rounded-full bg-amber-200 overflow-hidden" aria-hidden="true">
            <div className="h-full rounded-full bg-[#3D2E00]" style={{ width: `${Math.round(done / items.length * 100)}%` }} />
          </div>
        )}
        <p className="text-sm font-semibold">
          {items.length > 0 ? t('tableau.inCart', { done, total: items.length }) : t('tableau.addFromPlanning')}
        </p>
      </Link>

      {/* Frigo */}
      <Link to="/frigo" className="lg:col-span-4 rounded-[32px] bg-white border border-orange-100 p-6 flex flex-col gap-3 hover:border-orange-300 transition-colors">
        <h2 className="font-extrabold">{t('nav.fridge')}</h2>
        <p className="font-display text-2xl font-extrabold leading-tight">{t('tableau.fridgeQuestion')}</p>
        <span className="mt-auto text-sm font-bold text-orange-700">{t('tableau.pickIngredients')}</span>
      </Link>

      {/* Idée de l'assistant */}
      <section aria-label={t('tableau.assistantIdea')} className="lg:col-span-4 rounded-[32px] bg-green-100 text-[#17301A] p-6 flex flex-col gap-3">
        <span className="text-sm font-extrabold uppercase tracking-wider">{t('tableau.idea')}</span>
        <p className="text-lg font-bold leading-snug">
          {firstFree
            ? t('tableau.dayIsFree', { day: iso(firstFree) === from ? t('tableau.tonight') : weekday(firstFree).replace(/^./, c => c.toUpperCase()) })
            : t('tableau.weekFull')}
        </p>
        <button
          onClick={() => demander(firstFree
            ? t('tableau.askDinnerAndPlan', { day: weekday(firstFree) })
            : t('tableau.askWeekShopping'))}
          className="mt-auto self-start h-11 inline-flex items-center rounded-full bg-[#17301A] text-white px-5 font-bold hover:bg-[#24482a] transition-colors">
          {t('tableau.askAssistant')}
        </button>
      </section>
    </div>
  )
}
