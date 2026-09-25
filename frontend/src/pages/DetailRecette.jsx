import { useState, useEffect } from 'react'
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

const SOURCE_ICONS = { video: '🎬', web: '🌐', text: '📝', manual: '✏️' }
const SOURCE_LABELS = { video: 'Vidéo', web: 'Site web', text: 'Texte', manual: 'Manuel' }

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
  const whole = Math.floor(num), frac = num - whole
  if (frac < 0.04) return whole > 0 ? String(whole) : null
  for (const [n, d] of [[1,4],[1,3],[1,2],[2,3],[3,4]]) {
    if (Math.abs(frac - n/d) < 0.06) return whole > 0 ? `${whole} ${n}/${d}` : `${n}/${d}`
  }
  const r = Math.round(num * 10) / 10
  return r % 1 === 0 ? String(Math.round(r)) : String(r)
}

function scaleQty(q, scale) {
  const n = parseFraction(q)
  return n === null ? q : (formatQty(n * scale) ?? q)
}

export default function DetailRecette() {
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [scale, setScale] = useState(1)
  const [customScale, setCustomScale] = useState('')
  const [notes, setNotes] = useState(null) // null = not editing
  const [savingNotes, setSavingNotes] = useState(false)
  const [panneau, setPanneau] = useState(null) // 'carnets' | 'partage' | null

  const { data: recipe, isLoading, error } = useQuery({
    queryKey: ['recipe', id],
    queryFn: () => getRecipe(id),
    // Réextraction en cours : on suit sa progression jusqu'à la fin.
    refetchInterval: (query) => (query.state.data?.reextracting ? 2000 : false),
  })

  useEffect(() => {
    if (notes === null && recipe?.notes) setNotes(recipe.notes)
  }, [recipe, notes])

  const deleteMut = useMutation({ mutationFn: () => deleteRecipe(id), onSuccess: () => { qc.invalidateQueries({ queryKey: ['recipes'] }); navigate('/') } })
  const favMut = useMutation({ mutationFn: () => toggleFavorite(id), onSuccess: (r) => qc.setQueryData(['recipe', id], r) })
  const setRecipe = (r) => { qc.setQueryData(['recipe', id], r); qc.invalidateQueries({ queryKey: ['recipes'] }) }
  const avisMut = useMutation({ mutationFn: (data) => patchRecipe(id, data), onSuccess: setRecipe })
  const reextractMut = useMutation({ mutationFn: () => reextractRecipe(id), onSuccess: setRecipe })
  const shareMut = useMutation({ mutationFn: () => shareRecipe(id), onSuccess: setRecipe })
  const unshareMut = useMutation({ mutationFn: () => unshareRecipe(id), onSuccess: setRecipe })
  const nutritionMut = useMutation({ mutationFn: () => analyzeNutrition(id), onSuccess: (n) => qc.setQueryData(['recipe', id], prev => ({ ...prev, nutrition: n })) })

  const saveNotes = async () => {
    setSavingNotes(true)
    await updateRecipe(id, { notes: notes || null })
    qc.setQueryData(['recipe', id], prev => ({ ...prev, notes: notes || null }))
    setSavingNotes(false)
  }

  if (isLoading) return <div className="animate-pulse text-gray-400 py-12 text-center">Chargement…</div>
  if (error) return <div className="text-red-500 py-12 text-center">Recette introuvable</div>

  const totalTime = (recipe.prep_time || 0) + (recipe.cook_time || 0)
  const scaledServings = recipe.servings ? Math.round(recipe.servings * scale) : null
  const currentNotes = notes ?? recipe.notes ?? ''

  return (
    <div className="max-w-3xl">
      {/* Doublon warning */}
      {recipe.similar_recipe_id && (
        <div className="mb-4 bg-amber-50 border border-amber-200 text-amber-800 px-4 py-3 rounded-xl text-sm flex items-center gap-2">
          ⚠️ Une recette similaire existe déjà.{' '}
          <Link to={`/recettes/${recipe.similar_recipe_id}`} className="underline font-medium">Voir la recette</Link>
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-4 flex-wrap">
        <div>
          <Link to="/" className="text-sm text-orange-600 hover:underline mb-2 inline-block">← Retour</Link>
          <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-2">
            {recipe.title}
            <button onClick={() => favMut.mutate()} title={recipe.is_favorite ? 'Retirer des favoris' : 'Ajouter aux favoris'}
              className="text-2xl transition-transform hover:scale-110 flex-shrink-0">
              {recipe.is_favorite ? '❤️' : '🤍'}
            </button>
          </h1>
          {recipe.description && <p className="text-gray-500 mt-2">{recipe.description}</p>}
          <div className="flex items-center gap-3 mt-3 flex-wrap">
            <Etoiles value={recipe.rating} onChange={(rating) => avisMut.mutate({ rating })} />
            <button onClick={() => avisMut.mutate({ cook_again: !recipe.cook_again })}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                recipe.cook_again ? 'bg-green-50 border-green-300 text-green-700' : 'bg-white border-gray-200 text-gray-500 hover:border-green-300'
              }`}>
              🔁 {recipe.cook_again ? 'À refaire !' : 'À refaire ?'}
            </button>
            <span className="text-xs text-gray-400">
              {recipe.cooked_count
                ? `Cuisinée ${recipe.cooked_count} fois · dernière le ${new Date(`${recipe.last_cooked_at}T00:00:00`).toLocaleDateString('fr-FR')}`
                : 'Jamais cuisinée'}
            </span>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Link to={`/recettes/${id}/cuisine`} className="px-3 py-2 text-sm bg-orange-600 text-white hover:bg-orange-700 rounded-lg transition-colors">
            👨‍🍳 Cuisiner
          </Link>
          <Link to={`/recettes/${id}/modifier`} className="px-3 py-2 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors">Modifier</Link>
          <button onClick={() => setPanneau(p => p === 'carnets' ? null : 'carnets')} title="Ajouter à un carnet"
            className={`px-3 py-2 text-sm rounded-lg transition-colors ${panneau === 'carnets' ? 'bg-orange-100 text-orange-700' : 'bg-gray-100 hover:bg-gray-200'}`}>📚</button>
          <button onClick={() => setPanneau(p => p === 'partage' ? null : 'partage')} title="Partager par lien"
            className={`px-3 py-2 text-sm rounded-lg transition-colors ${panneau === 'partage' ? 'bg-orange-100 text-orange-700' : 'bg-gray-100 hover:bg-gray-200'}`}>🔗</button>
          {confirmDelete ? (
            <div className="flex gap-2">
              <button onClick={() => deleteMut.mutate()} className="px-3 py-2 text-sm bg-red-600 text-white rounded-lg">Confirmer</button>
              <button onClick={() => setConfirmDelete(false)} className="px-3 py-2 text-sm bg-gray-100 rounded-lg">Annuler</button>
            </div>
          ) : (
            <button onClick={() => setConfirmDelete(true)} className="px-3 py-2 text-sm bg-red-50 text-red-600 hover:bg-red-100 rounded-lg transition-colors">Supprimer</button>
          )}
        </div>
      </div>

      {panneau === 'carnets' && <ChoixCarnets recipeId={id} />}
      {panneau === 'partage' && (
        <div className="mb-5 p-4 bg-white rounded-xl border border-gray-100">
          <p className="text-sm text-gray-600 mb-3">Toute personne ayant le lien peut lire la recette, sans compte. Vos notes, avis et historique restent privés.</p>
          <LienPartage token={recipe.share_token} path={`/partage/r/${recipe.share_token}`}
            onShare={() => shareMut.mutate()} onUnshare={() => unshareMut.mutate()}
            busy={shareMut.isPending || unshareMut.isPending} />
        </div>
      )}

      {recipe.reextracting && (
        <div className="mb-4 bg-blue-50 border border-blue-200 text-blue-800 px-4 py-3 rounded-xl text-sm flex items-center gap-3">
          <span className="w-4 h-4 border-2 border-blue-200 border-t-blue-600 rounded-full animate-spin flex-shrink-0" />
          {recipe.progress_message || 'Réextraction en cours…'}
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
            <p className="text-xs text-gray-400">{SOURCE_LABELS[recipe.source_type] || 'Source'}</p>
            <p className="text-sm text-orange-600 group-hover:underline truncate">{recipe.source_url}</p>
          </div>
          <span className="ml-auto text-gray-300 group-hover:text-orange-400 flex-shrink-0">↗</span>
        </a>
        <button
          onClick={() => { if (confirm('Relire la recette depuis sa source ? Titre, ingrédients et étapes seront remplacés ; vos notes, avis, historique et image importée sont conservés.')) reextractMut.mutate() }}
          disabled={recipe.reextracting || reextractMut.isPending}
          title="Relancer l'extraction depuis la source, avec l'extraction améliorée"
          className="px-3 py-2 text-sm bg-white border border-gray-200 rounded-xl hover:border-orange-300 disabled:opacity-50">
          🔄 Réextraire
        </button>
        </div>
      )}

      {/* Thumbnail */}
      {recipe.thumbnail_url && (
        <img src={recipe.thumbnail_url} alt={recipe.title} className="w-full aspect-video object-cover rounded-2xl mb-6" />
      )}

      {/* Meta */}
      <div className="flex flex-wrap gap-4 mb-6 p-4 bg-white rounded-xl border border-gray-100">
        {recipe.prep_time && <MetaBox label="Préparation" value={`${recipe.prep_time} min`} />}
        {recipe.cook_time && <MetaBox label="Cuisson" value={`${recipe.cook_time} min`} />}
        {totalTime > 0 && <MetaBox label="Total" value={`${totalTime} min`} />}
        {recipe.servings && <MetaBox label="Portions" value={String(scaledServings ?? recipe.servings)} />}
        {recipe.category && (
          <span className="self-center px-3 py-1 bg-orange-100 text-orange-700 text-xs font-semibold rounded-full capitalize">{recipe.category}</span>
        )}
        {recipe.tags?.map(tag => (
          <span key={tag} className="self-center bg-gray-100 text-gray-600 text-xs px-2 py-1 rounded-full">{tag}</span>
        ))}
      </div>

      {/* Nutrition */}
      <section className="mb-6 p-4 bg-white rounded-xl border border-gray-100">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-800">Valeurs nutritionnelles</h3>
          {/* Toujours proposé : les valeurs sont estimées à partir des
              ingrédients et des portions, elles deviennent donc fausses dès
              qu'on modifie la recette. Le recalcul écrase l'analyse
              précédente côté serveur. */}
          <button onClick={() => nutritionMut.mutate()} disabled={nutritionMut.isPending}
            className="text-sm text-orange-600 hover:underline disabled:opacity-50">
            {nutritionMut.isPending
              ? 'Analyse…'
              : recipe.nutrition ? '🔄 Recalculer' : '🔬 Analyser'}
          </button>
        </div>
        {recipe.nutrition ? (
          <div className="grid grid-cols-3 sm:grid-cols-5 gap-3 text-center">
            {[['🔥 Cal.', recipe.nutrition.calories, 'kcal'], ['🥩 Prot.', recipe.nutrition.proteins, 'g'],
              ['🌾 Glucides', recipe.nutrition.carbs, 'g'], ['🫒 Lipides', recipe.nutrition.fat, 'g'],
              ['🌿 Fibres', recipe.nutrition.fiber, 'g']].map(([label, val, unit]) => (
              <div key={label}>
                <p className="text-xs text-gray-400">{label}</p>
                <p className="font-bold text-gray-800">{val ? `${Math.round(val)} ${unit}` : '—'}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-400">Cliquez sur Analyser pour estimer les apports par portion.</p>
        )}
      </section>

      {/* Ingrédients + scaling */}
      {recipe.ingredients?.length > 0 && (
        <section className="mb-8">
          <div className="flex items-center justify-between mb-4 gap-4 flex-wrap">
            <h2 className="text-xl font-bold text-gray-900">Ingrédients</h2>
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
          {scale !== 1 && <p className="text-xs text-orange-600 mb-3 font-medium">Quantités × {scale} — {scaledServings ?? '?'} portion{scaledServings !== 1 ? 's' : ''}</p>}
          <ul className="bg-white rounded-xl border border-gray-100 divide-y divide-gray-50">
            {recipe.ingredients.map((ing, i) => {
              const sq = scaleQty(ing.quantity, scale)
              return (
                <li key={i} className="flex items-baseline gap-2 px-4 py-3">
                  <span className="font-semibold text-orange-600 w-24 text-right flex-shrink-0">
                    {sq && ing.unit ? `${sq} ${ing.unit}` : sq || ing.unit || ''}
                  </span>
                  <span className="text-gray-900">{ing.name}</span>
                  {ing.notes && <span className="text-gray-400 text-sm">({ing.notes})</span>}
                </li>
              )
            })}
          </ul>
        </section>
      )}

      {/* Étapes + timers */}
      {recipe.steps?.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xl font-bold text-gray-900 mb-4">Préparation</h2>
          <ol className="space-y-5">
            {recipe.steps.map((step, i) => {
              const timerSec = parseStepTime(step.text)
              return (
                <li key={i} className="flex gap-4">
                  <span className="flex-shrink-0 w-8 h-8 bg-orange-600 text-white rounded-full flex items-center justify-center font-bold text-sm">
                    {step.order || i + 1}
                  </span>
                  <div className="flex-1">
                    <p className="text-gray-700 mb-2">{step.text}</p>
                    {timerSec && <StepTimer seconds={timerSec} />}
                  </div>
                </li>
              )
            })}
          </ol>
        </section>
      )}

      <Historique recipeId={id} onChange={setRecipe} />

      {/* Notes personnelles */}
      <section className="mb-8 p-4 bg-white rounded-xl border border-gray-100">
        <h3 className="font-semibold text-gray-800 mb-3">📝 Notes personnelles</h3>
        <textarea
          value={currentNotes}
          onChange={e => setNotes(e.target.value)}
          placeholder="Mes astuces, modifications, avis… (sauvegardé automatiquement)"
          rows={3}
          className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-orange-400"
        />
        <button onClick={saveNotes} disabled={savingNotes || currentNotes === (recipe.notes ?? '')}
          className="mt-2 px-4 py-1.5 text-sm bg-orange-600 text-white rounded-lg disabled:opacity-40 hover:bg-orange-700 transition-colors">
          {savingNotes ? 'Enregistrement…' : 'Enregistrer'}
        </button>
      </section>

      {/* Export PDF */}
      <div className="flex gap-3 border-t border-gray-100 pt-4">
        <button onClick={() => window.print()} className="flex items-center gap-2 px-4 py-2 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors">
          🖨️ Imprimer / PDF
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
