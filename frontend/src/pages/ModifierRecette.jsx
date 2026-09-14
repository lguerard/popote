import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getRecipe, updateRecipe, uploadThumbnail, generateThumbnail } from '../api'

export default function ModifierRecette() {
  const { id } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: recipe, isLoading } = useQuery({
    queryKey: ['recipe', id],
    queryFn: () => getRecipe(id),
  })

  const [form, setForm] = useState(null)

  useEffect(() => {
    if (recipe) setForm(recipe)
  }, [recipe])

  const updateMutation = useMutation({
    mutationFn: (data) => updateRecipe(id, data),
    onSuccess: (updated) => {
      queryClient.setQueryData(['recipe', id], updated)
      queryClient.invalidateQueries({ queryKey: ['recipes'] })
      navigate(`/recettes/${id}`)
    },
  })

  // L'image se sauvegarde a part, immediatement : c'est un upload
  // multipart, pas un champ du formulaire JSON envoye par "Enregistrer".
  const onThumbnailSaved = (updated) => {
    setForm((f) => ({ ...f, thumbnail_url: updated.thumbnail_url }))
    queryClient.setQueryData(['recipe', id], updated)
    queryClient.invalidateQueries({ queryKey: ['recipes'] })
  }
  const uploadMutation = useMutation({
    mutationFn: (file) => uploadThumbnail(id, file),
    onSuccess: onThumbnailSaved,
  })

  // La génération tourne en arrière-plan côté serveur (le premier appel
  // doit télécharger un modèle de plusieurs Go avant de générer quoi que
  // ce soit — trop long pour une réponse HTTP classique) : on lance la
  // tâche puis on interroge la recette jusqu'à ce qu'elle ait fini,
  // même principe que le suivi d'extraction.
  const [isGenerating, setIsGenerating] = useState(false)
  const [generateError, setGenerateError] = useState(null)
  const startMutation = useMutation({
    mutationFn: () => generateThumbnail(id),
    onSuccess: () => { setGenerateError(null); setIsGenerating(true) },
  })

  useEffect(() => {
    if (recipe?.thumbnail_generating) setIsGenerating(true)
  }, [recipe])

  useEffect(() => {
    if (!isGenerating) return undefined
    const interval = setInterval(async () => {
      try {
        const updated = await getRecipe(id)
        if (!updated.thumbnail_generating) {
          clearInterval(interval)
          setIsGenerating(false)
          if (updated.thumbnail_error) setGenerateError(updated.thumbnail_error)
          else onThumbnailSaved(updated)
        }
      } catch {
        clearInterval(interval)
        setIsGenerating(false)
      }
    }, 2000)
    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isGenerating, id])

  const fileRef = useRef(null)
  const handlePickImage = (e) => {
    const file = e.target.files[0]
    e.target.value = '' // permet de reselectionner le meme fichier ensuite
    if (file) uploadMutation.mutate(file)
  }

  if (isLoading || !form) return <div className="text-gray-400 py-12 text-center">Chargement…</div>

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))

  const setIngredient = (i, field) => (e) => {
    const ings = [...form.ingredients]
    ings[i] = { ...ings[i], [field]: e.target.value }
    setForm((f) => ({ ...f, ingredients: ings }))
  }

  const addIngredient = () =>
    setForm((f) => ({ ...f, ingredients: [...f.ingredients, { quantity: '', unit: '', name: '', notes: '' }] }))

  const removeIngredient = (i) =>
    setForm((f) => ({ ...f, ingredients: f.ingredients.filter((_, idx) => idx !== i) }))

  const setStep = (i) => (e) => {
    const steps = [...form.steps]
    steps[i] = { ...steps[i], text: e.target.value }
    setForm((f) => ({ ...f, steps }))
  }

  const addStep = () =>
    setForm((f) => ({ ...f, steps: [...f.steps, { order: f.steps.length + 1, text: '' }] }))

  const removeStep = (i) =>
    setForm((f) => ({ ...f, steps: f.steps.filter((_, idx) => idx !== i).map((s, idx) => ({ ...s, order: idx + 1 })) }))

  const handleSubmit = (e) => {
    e.preventDefault()
    updateMutation.mutate({
      title: form.title,
      description: form.description,
      servings: form.servings ? Number(form.servings) : null,
      prep_time: form.prep_time ? Number(form.prep_time) : null,
      cook_time: form.cook_time ? Number(form.cook_time) : null,
      ingredients: form.ingredients,
      steps: form.steps,
      tags: typeof form.tags === 'string' ? form.tags.split(',').map(t => t.trim()).filter(Boolean) : form.tags,
      thumbnail_url: form.thumbnail_url,
    })
  }

  const labelCls = 'block text-sm font-medium text-gray-700 mb-1'
  const inputCls = 'w-full px-3 py-2 rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-orange-400 text-sm'

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl space-y-6">
      <div className="flex items-center gap-4">
        <Link to={`/recettes/${id}`} className="text-sm text-orange-600 hover:underline">← Annuler</Link>
        <h1 className="text-2xl font-bold text-gray-900">Modifier la recette</h1>
      </div>

      <div>
        <label className={labelCls}>Image</label>
        <div className="flex items-start gap-4">
          <div className="w-40 aspect-video rounded-xl overflow-hidden bg-gray-100 border border-gray-200 flex-shrink-0">
            {form.thumbnail_url ? (
              <img src={form.thumbnail_url} alt="" className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-3xl text-gray-300">🍽️</div>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <input ref={fileRef} type="file" accept="image/*" onChange={handlePickImage} className="hidden" />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={uploadMutation.isPending || isGenerating}
              className="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-50"
            >
              {uploadMutation.isPending ? 'Envoi…' : '📷 Changer l’image'}
            </button>
            <button
              type="button"
              onClick={() => startMutation.mutate()}
              disabled={uploadMutation.isPending || isGenerating || startMutation.isPending}
              className="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-50"
            >
              {isGenerating || startMutation.isPending ? 'Génération…' : '🪄 Générer avec l’IA'}
            </button>
            {isGenerating && (
              <p className="text-xs text-gray-400 max-w-xs">
                Peut prendre plusieurs minutes la première fois (téléchargement du modèle).
              </p>
            )}
            {(uploadMutation.isError || startMutation.isError || generateError) && (
              <p className="text-xs text-red-500 max-w-xs">
                {uploadMutation.error?.response?.data?.detail
                  || startMutation.error?.response?.data?.detail
                  || generateError
                  || 'Erreur lors de la mise à jour de l’image.'}
              </p>
            )}
          </div>
        </div>
      </div>

      <div>
        <label className={labelCls}>Titre</label>
        <input value={form.title} onChange={set('title')} required className={inputCls} />
      </div>

      <div>
        <label className={labelCls}>Description</label>
        <textarea value={form.description || ''} onChange={set('description')} rows={3} className={inputCls} />
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className={labelCls}>Portions</label>
          <input type="number" min="1" value={form.servings || ''} onChange={set('servings')} className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>Prép. (min)</label>
          <input type="number" min="0" value={form.prep_time || ''} onChange={set('prep_time')} className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>Cuisson (min)</label>
          <input type="number" min="0" value={form.cook_time || ''} onChange={set('cook_time')} className={inputCls} />
        </div>
      </div>

      <div>
        <label className={labelCls}>Tags (séparés par des virgules)</label>
        <input
          value={Array.isArray(form.tags) ? form.tags.join(', ') : form.tags || ''}
          onChange={set('tags')}
          placeholder="facile, végétarien, rapide"
          className={inputCls}
        />
      </div>

      {/* Ingrédients */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className={labelCls + ' mb-0'}>Ingrédients</label>
          <button type="button" onClick={addIngredient} className="text-sm text-orange-600 hover:underline">+ Ajouter</button>
        </div>
        <div className="space-y-2">
          {form.ingredients.map((ing, i) => (
            <div key={i} className="flex gap-2 items-center">
              <input placeholder="Qté" value={ing.quantity || ''} onChange={setIngredient(i, 'quantity')} className={inputCls + ' w-16'} />
              <input placeholder="Unité" value={ing.unit || ''} onChange={setIngredient(i, 'unit')} className={inputCls + ' w-20'} />
              <input placeholder="Ingrédient" value={ing.name || ''} onChange={setIngredient(i, 'name')} className={inputCls + ' flex-1'} required />
              <input placeholder="Notes" value={ing.notes || ''} onChange={setIngredient(i, 'notes')} className={inputCls + ' w-28'} />
              <button type="button" onClick={() => removeIngredient(i)} className="text-red-400 hover:text-red-600 text-lg">×</button>
            </div>
          ))}
        </div>
      </div>

      {/* Étapes */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className={labelCls + ' mb-0'}>Étapes</label>
          <button type="button" onClick={addStep} className="text-sm text-orange-600 hover:underline">+ Ajouter</button>
        </div>
        <div className="space-y-2">
          {form.steps.map((step, i) => (
            <div key={i} className="flex gap-2 items-start">
              <span className="w-7 h-7 bg-orange-100 text-orange-700 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0 mt-1.5">
                {i + 1}
              </span>
              <textarea
                value={step.text}
                onChange={setStep(i)}
                rows={2}
                className={inputCls + ' flex-1 resize-none'}
                required
              />
              <button type="button" onClick={() => removeStep(i)} className="text-red-400 hover:text-red-600 text-lg mt-1">×</button>
            </div>
          ))}
        </div>
      </div>

      <button
        type="submit"
        disabled={updateMutation.isPending}
        className="w-full py-3 bg-orange-600 hover:bg-orange-700 disabled:opacity-50 text-white font-semibold rounded-xl transition-colors"
      >
        {updateMutation.isPending ? 'Enregistrement…' : 'Enregistrer les modifications'}
      </button>
    </form>
  )
}
