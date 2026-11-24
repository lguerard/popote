import { Fragment, useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getRecipe, deleteRecipe, toggleFavorite, updateRecipe, analyzeNutrition, patchRecipe,
  reextractRecipe, shareRecipe, unshareRecipe,
} from '../api'
import StepTimer, { parseStepTime } from '../components/Timer'
import Etoiles from '../components/Etoiles'
import LienPartage from '../components/LienPartage'
import Historique from '../components/Historique'
import ChoixCarnets from '../components/ChoixCarnets'
import EnvoiCompte from '../components/EnvoiCompte'
import ExportMfp from '../components/ExportMfp'
import { BoutonAssistant } from '../assistant/Assistant'
import { sectionStart, SectionTitle } from '../components/Sections'
import { useAuth } from '../auth'
import { libelleCategorie } from '../i18n'
import { contenuAffiche, DELAI_RELECTURE_TRADUCTION } from '../contenuRecette'

const SOURCE_ICONS = { video: '🎬', web: '🌐', text: '📝', manual: '✏️' }
const SOURCE_LABELS = { video: 'detail.source.video', web: 'detail.source.web', text: 'detail.source.text', manual: 'detail.source.manual' }

const SCALE_PRESETS = [{ label: '½×', value: 0.5 }, { label: '1×', value: 1 }, { label: '2×', value: 2 }, { label: '3×', value: 3 }]

function parseFraction(str) {
  if (!str) return null
  const frac = str.match(/^(\d+)\s*\/\s*(\d+)$/)
  if (frac) return +frac[1] / +frac[2]
  const mixed = str.match(/^(\d+)\s+(\d+)\s*\/\s*(\d+)$/)
  if (mixed) return +mixed[1] + +mixed[2] / +mixed[3]
  const n = parseFloat(str.replace(',', '.'))
  return isNaN(n) ? null : n
}

function formatQty(num) {
  if (num === null || isNaN(num)) return null
  // « 416 2/3 g » ne se pèse pas : arrondi à l'unité, ou au demi pour 10-50.
  if (num >= 50) return String(Math.round(num))
  if (num >= 10) return String(Math.round(num * 2) / 2)
  const whole = Math.floor(num), frac = num - whole
  if (frac < 0.04) return whole > 0 ? String(whole) : null
  for (const [n, d] of [[1,4],[1,3],[1,2],[2,3],[3,4]]) {
    if (Math.abs(frac - n/d) < 0.06) return whole > 0 ? `${whole} ${n}/${d}` : `${n}/${d}`
  }
  const r = Math.round(num * 10) / 10
  return r % 1 === 0 ? String(Math.round(r)) : String(r)
}

const formatScale = (s) => `×${String(Math.round(s * 100) / 100).replace('.', ',')}`

function scaleQty(q, scale) {
  const n = parseFraction(q)
  return n === null ? q : (formatQty(n * scale) ?? q)
}

export default function DetailRecette() {
  const { t, lang } = useAuth()
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [scale, setScale] = useState(1)
  const [customScale, setCustomScale] = useState('')
  const [ajuste, setAjuste] = useState(null) // index de l'ingrédient dont on saisit la quantité
  // 200 g de chocolat au lieu de 120 → toute la recette × 1,67.
  const ajusterIngredient = (ing, valeur) => {
    const base = parseFraction(ing.quantity), voulu = parseFraction(String(valeur).trim())
    if (base > 0 && voulu > 0) {
      const s = voulu / base
      setScale(s)
      setCustomScale(String(Math.round(s * 100) / 100))
    }
    setAjuste(null)
  }
  const [notes, setNotes] = useState(null) // null = not editing
  const [savingNotes, setSavingNotes] = useState(false)
  const [panneau, setPanneau] = useState(null) // 'carnets' | 'partage' | 'compte' | 'mfp' | null

  const { data: recipe, isLoading, error } = useQuery({
    queryKey: ['recipe', id],
    queryFn: () => getRecipe(id),
    // Réextraction en cours : on suit sa progression jusqu'à la fin. Même
    // chose pour une traduction lancée en arrière-plan par le serveur.
    refetchInterval: (query) => (
      query.state.data?.reextracting ? 2000
        : query.state.data?.translation_pending ? DELAI_RELECTURE_TRADUCTION : false
    ),
  })

  useEffect(() => {
    if (notes === null && recipe?.notes) setNotes(recipe.notes)
  }, [recipe, notes])

  const deleteMut = useMutation({ mutationFn: () => deleteRecipe(id), onSuccess: () => { qc.invalidateQueries({ queryKey: ['recipes'] }); navigate('/') } })
  const favMut = useMutation({ mutationFn: () => toggleFavorite(id), onSuccess: (r) => qc.setQueryData(['recipe', id], r) })
  const setRecipe = (r) => { qc.setQueryData(['recipe', id], r); qc.invalidateQueries({ queryKey: ['recipes'] }) }
  const avisMut = useMutation({ mutationFn: (data) => patchRecipe(id, data), onSuccess: setRecipe })
  const [reextraction, setReextraction] = useState(null) // null = panneau fermé, sinon { remplacerImage }
  const reextractMut = useMutation({
    mutationFn: (remplacerImage) => reextractRecipe(id, remplacerImage),
    onSuccess: (r) => { setRecipe(r); setReextraction(null) },
  })
  const shareMut = useMutation({ mutationFn: () => shareRecipe(id), onSuccess: setRecipe })
  const unshareMut = useMutation({ mutationFn: () => unshareRecipe(id), onSuccess: setRecipe })
  const nutritionMut = useMutation({ mutationFn: () => analyzeNutrition(id), onSuccess: (n) => qc.setQueryData(['recipe', id], prev => ({ ...prev, nutrition: n })) })

  const saveNotes = async () => {
    setSavingNotes(true)
    await updateRecipe(id, { notes: notes || null })
    qc.setQueryData(['recipe', id], prev => ({ ...prev, notes: notes || null }))
    setSavingNotes(false)
  }

  if (isLoading) return <div className="animate-pulse text-gray-400 py-12 text-center">{t('common.loading')}</div>
  if (error) return <div className="text-red-500 py-12 text-center">{t('detail.notFound')}</div>

  // Affichage seulement (traduction du compte) : les enregistrements
  // ci-dessus n'envoient que des champs précis (notes, avis), jamais `vue`.
  const vue = contenuAffiche(recipe)
  const totalTime = (recipe.prep_time || 0) + (recipe.cook_time || 0)
  const scaledServings = recipe.servings ? Math.round(recipe.servings * scale) : null
  const currentNotes = notes ?? recipe.notes ?? ''

  return (
    <div className="max-w-3xl">
      {/* Doublon warning */}
      {recipe.similar_recipe_id && (
        <div className="mb-4 bg-amber-50 border border-amber-200 text-amber-800 px-4 py-3 rounded-xl text-sm flex items-center gap-2">
          {t('detail.similarExists')}{' '}
          <Link to={`/recettes/${recipe.similar_recipe_id}`} className="underline font-medium">{t('tableau.seeRecipe')}</Link>
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-4 flex-wrap">
        <div>
          <Link to="/" className="text-sm text-orange-600 hover:underline mb-2 inline-block">{t('detail.back')}</Link>
          <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-2">
            {vue.title}
            <button onClick={() => favMut.mutate()} title={recipe.is_favorite ? t('detail.removeFavorite') : t('detail.addFavorite')}
              className="text-2xl transition-transform hover:scale-110 flex-shrink-0">
              {recipe.is_favorite ? '❤️' : '🤍'}
            </button>
          </h1>
          {recipe.shared_by_name && (
            <p className="mt-2 inline-flex items-center gap-1.5 px-3 py-1 bg-sky-50 text-sky-700 border border-sky-200 rounded-full text-xs font-medium">
              {t('detail.sharedBy', { name: recipe.shared_by_name })}
            </p>
          )}
          {vue.description && <p className="text-gray-500 mt-2">{vue.description}</p>}
          <div className="flex items-center gap-3 mt-3 flex-wrap">
            <Etoiles value={recipe.rating} onChange={(rating) => avisMut.mutate({ rating })} />
            <button onClick={() => avisMut.mutate({ cook_again: !recipe.cook_again })}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                recipe.cook_again ? 'bg-green-50 border-green-300 text-green-700' : 'bg-white border-gray-200 text-gray-500 hover:border-green-300'
              }`}>
              🔁 {recipe.cook_again ? t('detail.cookAgainYes') : t('detail.cookAgainAsk')}
            </button>
            <span className="text-xs text-gray-400">
              {recipe.cooked_count
                ? t('detail.cookedCount', { n: recipe.cooked_count, date: new Date(`${recipe.last_cooked_at}T00:00:00`).toLocaleDateString(t('common.locale')) })
                : t('detail.neverCooked')}
            </span>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Link to={`/recettes/${id}/cuisine`} className="px-3 py-2 text-sm bg-orange-600 text-white hover:bg-orange-700 rounded-lg transition-colors">
            {t('detail.cook')}
          </Link>
          <BoutonAssistant recipe={vue} />
          <Link to={`/recettes/${id}/modifier`} className="px-3 py-2 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors">{t('common.edit')}</Link>
          <button onClick={() => setPanneau(p => p === 'carnets' ? null : 'carnets')} title={t('detail.addToCollection')}
            className={`px-3 py-2 text-sm rounded-lg transition-colors ${panneau === 'carnets' ? 'bg-orange-100 text-orange-700' : 'bg-gray-100 hover:bg-gray-200'}`}>📚</button>
          <button onClick={() => setPanneau(p => p === 'partage' ? null : 'partage')} title={t('lienPartage.shareByLink')}
            className={`px-3 py-2 text-sm rounded-lg transition-colors ${panneau === 'partage' ? 'bg-orange-100 text-orange-700' : 'bg-gray-100 hover:bg-gray-200'}`}>🔗</button>
          <button onClick={() => setPanneau(p => p === 'compte' ? null : 'compte')} title={t('detail.sendToAccount')}
            className={`px-3 py-2 text-sm rounded-lg transition-colors ${panneau === 'compte' ? 'bg-orange-100 text-orange-700' : 'bg-gray-100 hover:bg-gray-200'}`}>👥</button>
          <button onClick={() => setPanneau(p => p === 'mfp' ? null : 'mfp')} title={t('detail.exportMfp')}
            className={`px-3 py-2 text-sm rounded-lg transition-colors ${panneau === 'mfp' ? 'bg-orange-100 text-orange-700' : 'bg-gray-100 hover:bg-gray-200'}`}>🥗 MFP</button>
          {confirmDelete ? (
            <div className="flex gap-2">
              <button onClick={() => deleteMut.mutate()} className="px-3 py-2 text-sm bg-red-600 text-white rounded-lg">{t('detail.confirm')}</button>
              <button onClick={() => setConfirmDelete(false)} className="px-3 py-2 text-sm bg-gray-100 rounded-lg">{t('common.cancel')}</button>
            </div>
          ) : (
            <button onClick={() => setConfirmDelete(true)} className="px-3 py-2 text-sm bg-red-50 text-red-600 hover:bg-red-100 rounded-lg transition-colors">{t('common.delete')}</button>
          )}
        </div>
      </div>

      {panneau === 'carnets' && <ChoixCarnets recipeId={id} />}
      {panneau === 'partage' && (
        <div className="mb-5 p-4 bg-white rounded-xl border border-gray-100">
          <p className="text-sm text-gray-600 mb-3">{t('detail.linkInfo')}</p>
          <LienPartage token={recipe.share_token} path={`/partage/r/${recipe.share_token}`}
            onShare={() => shareMut.mutate()} onUnshare={() => unshareMut.mutate()}
            busy={shareMut.isPending || unshareMut.isPending} />
        </div>
      )}

      {panneau === 'compte' && (
        <div className="mb-5 p-4 bg-white rounded-xl border border-gray-100">
          <p className="text-sm text-gray-600 mb-3">
            {t('detail.accountInfo')}
          </p>
          <EnvoiCompte recipeIds={[id]} />
        </div>
      )}
      {panneau === 'mfp' && (
        <div className="mb-5 p-4 bg-white rounded-xl border border-gray-100">
          <h3 className="font-semibold text-gray-800 mb-3">{t('detail.exportMfp')}</h3>
          <ExportMfp recipe={vue} scale={scale} scaleQty={scaleQty} portions={scaledServings}
            onShare={() => shareMut.mutate()} busy={shareMut.isPending} />
        </div>
      )}

      {recipe.reextracting && (
        <div className="mb-4 bg-blue-50 border border-blue-200 text-blue-800 px-4 py-3 rounded-xl text-sm flex items-center gap-3">
          <span className="w-4 h-4 border-2 border-blue-200 border-t-blue-600 rounded-full animate-spin flex-shrink-0" />
          {recipe.progress_message || t('detail.reextracting')}
        </div>
      )}
      {!recipe.reextracting && recipe.error_msg && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">{recipe.error_msg}</div>
      )}

      {/* Source — mis en avant */}
      {recipe.source_url && (
        <div className="mb-5 flex items-center gap-2 flex-wrap">
        <a href={recipe.source_url} target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-200 rounded-xl hover:border-orange-300 hover:bg-orange-50 transition-colors group w-fit max-w-full">
          <span className="text-lg flex-shrink-0">{SOURCE_ICONS[recipe.source_type] || '🔗'}</span>
          <div className="min-w-0">
            <p className="text-xs text-gray-400">{SOURCE_LABELS[recipe.source_type] ? t(SOURCE_LABELS[recipe.source_type]) : t('detail.source.default')}</p>
            <p className="text-sm text-orange-600 group-hover:underline truncate">{recipe.source_url}</p>
          </div>
          <span className="ml-auto text-gray-300 group-hover:text-orange-400 flex-shrink-0">↗</span>
        </a>
        <button
          onClick={() => setReextraction(r => (r ? null : { remplacerImage: false }))}
          disabled={recipe.reextracting || reextractMut.isPending}
          title={t('detail.reextractTitle')}
          className={`px-3 py-2 text-sm border rounded-xl disabled:opacity-50 ${
            reextraction ? 'bg-orange-50 border-orange-300' : 'bg-white border-gray-200 hover:border-orange-300'
          }`}>
          {t('detail.reextractButton')}
        </button>
        </div>
      )}
      {reextraction && !recipe.reextracting && (
        <div className="mb-5 p-4 bg-white rounded-xl border border-orange-200 text-sm space-y-3">
          <p className="text-gray-600">
            {t('detail.reextractInfo')}
          </p>
          <label className="flex items-start gap-2 cursor-pointer">
            <input type="checkbox" checked={reextraction.remplacerImage}
              onChange={e => setReextraction({ remplacerImage: e.target.checked })}
              className="accent-orange-600 w-4 h-4 mt-0.5" />
            <span>
              {t('detail.replaceImage')}
              {recipe.thumbnail_url?.startsWith('/media/') && (
                <span className="block text-xs text-gray-400">{t('detail.keepImage')}</span>
              )}
            </span>
          </label>
          <div className="flex gap-2">
            <button onClick={() => reextractMut.mutate(reextraction.remplacerImage)} disabled={reextractMut.isPending}
              className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:opacity-50">
              {reextractMut.isPending ? t('detail.launching') : t('detail.reextract')}
            </button>
            <button onClick={() => setReextraction(null)} className="px-4 py-2 bg-gray-100 rounded-lg hover:bg-gray-200">{t('common.cancel')}</button>
          </div>
        </div>
      )}

      {/* Thumbnail */}
      {recipe.thumbnail_url && (
        <img src={recipe.thumbnail_url} alt={vue.title} className="w-full aspect-video object-cover rounded-2xl mb-6" />
      )}

      {/* Meta */}
      <div className="flex flex-wrap gap-4 mb-6 p-4 bg-white rounded-xl border border-gray-100">
        {recipe.prep_time && <MetaBox label={t('detail.prep')} value={`${recipe.prep_time} min`} />}
        {recipe.cook_time && <MetaBox label={t('detail.cookTime')} value={`${recipe.cook_time} min`} />}
        {totalTime > 0 && <MetaBox label={t('detail.total')} value={`${totalTime} min`} />}
        {recipe.servings && <MetaBox label={t('detail.servings')} value={String(scaledServings ?? recipe.servings)} />}
        {recipe.category && (
          <span className="self-center px-3 py-1 bg-orange-100 text-orange-700 text-xs font-semibold rounded-full capitalize">{libelleCategorie(lang, recipe.category)}</span>
        )}
        {vue.tags?.map(tag => (
          <span key={tag} className="self-center bg-gray-100 text-gray-600 text-xs px-2 py-1 rounded-full">{tag}</span>
        ))}
      </div>

      {/* Nutrition */}
      <section className="mb-6 p-4 bg-white rounded-xl border border-gray-100">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-800">{t('detail.nutrition')}</h3>
          {/* Toujours proposé : les valeurs sont estimées à partir des
              ingrédients et des portions, elles deviennent donc fausses dès
              qu'on modifie la recette. Le recalcul écrase l'analyse
              précédente côté serveur. */}
          <button onClick={() => nutritionMut.mutate()} disabled={nutritionMut.isPending}
            className="text-sm text-orange-600 hover:underline disabled:opacity-50">
            {nutritionMut.isPending
              ? t('detail.analyzing')
              : recipe.nutrition ? t('detail.recalculate') : t('detail.analyze')}
          </button>
        </div>
        {recipe.nutrition ? (
          <div className="grid grid-cols-3 sm:grid-cols-5 gap-3 text-center">
            {[['detail.nutri.calories', recipe.nutrition.calories, 'kcal'], ['detail.nutri.proteins', recipe.nutrition.proteins, 'g'],
              ['detail.nutri.carbs', recipe.nutrition.carbs, 'g'], ['detail.nutri.fat', recipe.nutrition.fat, 'g'],
              ['detail.nutri.fiber', recipe.nutrition.fiber, 'g']].map(([label, val, unit]) => (
              <div key={label}>
                <p className="text-xs text-gray-400">{t(label)}</p>
                <p className="font-bold text-gray-800">{val ? `${Math.round(val)} ${unit}` : '—'}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-400">{t('detail.nutritionHint')}</p>
        )}
      </section>

      {/* Ingrédients + scaling */}
      {vue.ingredients?.length > 0 && (
        <section className="mb-8">
          <div className="flex items-center justify-between mb-4 gap-4 flex-wrap">
            <h2 className="text-xl font-bold text-gray-900">{t('detail.ingredients')}</h2>
            <div className="flex items-center gap-1.5 flex-wrap">
              {SCALE_PRESETS.map(({ label, value }) => (
                <button key={value} onClick={() => { setScale(value); setCustomScale('') }}
                  className={`px-3 py-1 rounded-lg text-sm font-medium transition-colors ${scale === value && !customScale ? 'bg-orange-600 text-white' : 'bg-white border border-gray-200 text-gray-600 hover:border-orange-300'}`}>
                  {label}
                </button>
              ))}
              <input type="number" min="0.1" step="0.1" placeholder="×?" value={customScale}
                onChange={e => { setCustomScale(e.target.value); const n = parseFloat(e.target.value); if (!isNaN(n) && n > 0) setScale(n) }}
                className="w-16 px-2 py-1 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-400 text-center" />
            </div>
          </div>
          {recipe.servings > 0 && (
            <label className="flex items-center gap-2 text-sm text-gray-600 mb-2">
              {t('detail.servingsLabel')}
              <input type="number" min="1" value={scaledServings ?? ''}
                onChange={e => { const n = parseFloat(e.target.value); if (n > 0) { setScale(n / recipe.servings); setCustomScale(String(Math.round(n / recipe.servings * 100) / 100)) } }}
                className="w-16 px-2 py-1 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-400 text-center" />
            </label>
          )}
          <p className="text-xs text-gray-400 mb-2">{t('detail.adjustHint')}</p>
          {scale !== 1 && <p className="text-xs text-orange-600 mb-3 font-medium">{t(scaledServings !== 1 ? 'detail.scaledMany' : 'detail.scaledOne', { scale: formatScale(scale), n: scaledServings ?? '?' })}</p>}
          <ul className="bg-white rounded-xl border border-gray-100 divide-y divide-gray-50">
            {vue.ingredients.map((ing, i) => {
              const sq = scaleQty(ing.quantity, scale)
              const ajustable = parseFraction(ing.quantity) > 0
              const section = sectionStart(vue.ingredients, i)
              return (
                <Fragment key={i}>
                {section && <SectionTitle className="px-4 pt-4 pb-1 bg-orange-50/60">{section}</SectionTitle>}
                <li className="flex items-baseline gap-2 px-4 py-3">
                  {ajuste === i ? (
                    <span className="w-24 flex-shrink-0 flex items-baseline justify-end gap-1">
                      <input autoFocus inputMode="decimal" defaultValue={sq}
                        onBlur={e => ajusterIngredient(ing, e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur(); if (e.key === 'Escape') setAjuste(null) }}
                        className="w-16 px-1 py-0.5 text-right font-semibold text-orange-600 border border-orange-300 rounded focus:outline-none focus:ring-2 focus:ring-orange-400" />
                      <span className="text-orange-600 text-sm">{ing.unit}</span>
                    </span>
                  ) : (
                    <button type="button" disabled={!ajustable} onClick={() => setAjuste(i)}
                      title={ajustable ? t('detail.adjustTitle') : undefined}
                      className={`font-semibold text-orange-600 w-24 text-right flex-shrink-0 ${ajustable ? 'hover:underline decoration-dotted cursor-pointer' : 'cursor-default'}`}>
                      {sq && ing.unit ? `${sq} ${ing.unit}` : sq || ing.unit || ''}
                    </button>
                  )}
                  <span className="text-gray-900">{ing.name}</span>
                  {ing.notes && <span className="text-gray-400 text-sm">({ing.notes})</span>}
                </li>
                </Fragment>
              )
            })}
          </ul>
        </section>
      )}

      {/* Étapes + timers */}
      {vue.steps?.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xl font-bold text-gray-900 mb-4">{t('detail.steps')}</h2>
          <ol className="space-y-5">
            {vue.steps.map((step, i) => {
              const timerSec = parseStepTime(step.text)
              const section = sectionStart(vue.steps, i)
              return (
                <Fragment key={i}>
                {section && <SectionTitle className="pt-2">{section}</SectionTitle>}
                <li className="flex gap-4">
                  <span className="flex-shrink-0 w-8 h-8 bg-orange-600 text-white rounded-full flex items-center justify-center font-bold text-sm">
                    {step.order || i + 1}
                  </span>
                  <div className="flex-1">
                    <p className="text-gray-700 mb-2">{step.text}</p>
                    {timerSec && <StepTimer seconds={timerSec} />}
                  </div>
                </li>
                </Fragment>
              )
            })}
          </ol>
        </section>
      )}

      <Historique recipeId={id} onChange={setRecipe} />

      {/* Notes personnelles */}
      <section className="mb-8 p-4 bg-white rounded-xl border border-gray-100">
        <h3 className="font-semibold text-gray-800 mb-3">{t('detail.personalNotes')}</h3>
        <textarea
          value={currentNotes}
          onChange={e => setNotes(e.target.value)}
          placeholder={t('detail.notesPlaceholder')}
          rows={3}
          className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-orange-400"
        />
        <button onClick={saveNotes} disabled={savingNotes || currentNotes === (recipe.notes ?? '')}
          className="mt-2 px-4 py-1.5 text-sm bg-orange-600 text-white rounded-lg disabled:opacity-40 hover:bg-orange-700 transition-colors">
          {savingNotes ? t('detail.saving') : t('common.save')}
        </button>
      </section>

      {/* Export PDF */}
      <div className="flex gap-3 border-t border-gray-100 pt-4">
        <button onClick={() => window.print()} className="flex items-center gap-2 px-4 py-2 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors">
          {t('detail.print')}
        </button>
      </div>
    </div>
  )
}

function MetaBox({ label, value }) {
  return (
    <div className="text-center">
      <p className="text-xs text-gray-400 uppercase tracking-wide">{label}</p>
      <p className="font-semibold">{value}</p>
    </div>
  )
}
