import { useState, useRef } from 'react'
import { submitExtraction, submitImageExtraction } from '../api'
import StatutExtraction from '../components/StatutExtraction'

const TABS = [
  { id: 'url', label: 'URL / Texte', emoji: '🔗' },
  { id: 'photo', label: 'Photo', emoji: '📷' },
]

export default function AjouterRecette() {
  const [tab, setTab] = useState('url')
  const [input, setInput] = useState('')
  const [imageFile, setImageFile] = useState(null)
  const [imagePreview, setImagePreview] = useState(null)
  const [loading, setLoading] = useState(false)
  const [recipeId, setRecipeId] = useState(null)
  const [error, setError] = useState(null)
  const fileRef = useRef(null)

  const handleSubmitUrl = async (e) => {
    e.preventDefault()
    if (!input.trim()) return
    setLoading(true); setError(null)
    try {
      const res = await submitExtraction(input.trim())
      setRecipeId(res.recipe_id)
    } catch (err) {
      setError(err.response?.data?.detail || 'Erreur lors de la soumission')
      setLoading(false)
    }
  }

  const handleImageChange = (e) => {
    const file = e.target.files[0]
    if (!file) return
    setImageFile(file)
    setImagePreview(URL.createObjectURL(file))
  }

  const handleSubmitImage = async (e) => {
    e.preventDefault()
    if (!imageFile) return
    setLoading(true); setError(null)
    try {
      const res = await submitImageExtraction(imageFile)
      setRecipeId(res.recipe_id)
    } catch (err) {
      setError(err.response?.data?.detail || 'Erreur lors de l\'OCR')
      setLoading(false)
    }
  }

  if (recipeId) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-8">Extraction en cours</h1>
        <StatutExtraction recipeId={recipeId} onError={(msg) => { setRecipeId(null); setError(msg); setLoading(false) }} />
      </div>
    )
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-3xl font-bold text-gray-900 mb-6">Ajouter une recette</h1>

      {/* Tabs */}
      <div className="flex gap-2 mb-6 bg-gray-100 p-1 rounded-xl w-fit">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => { setTab(t.id); setError(null) }}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === t.id ? 'bg-white shadow-sm text-orange-700' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.emoji} {t.label}
          </button>
        ))}
      </div>

      {tab === 'url' && (
        <form onSubmit={handleSubmitUrl} className="space-y-4">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={'URL YouTube, TikTok, Instagram, Marmiton…\nou texte brut de recette (toute langue)'}
            rows={6}
            className="w-full px-4 py-3 rounded-xl border border-gray-200 bg-white shadow-sm focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-transparent resize-none font-mono text-sm"
          />
          {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">{error}</div>}
          <button type="submit" disabled={loading || !input.trim()} className="w-full py-3 bg-orange-600 hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-colors">
            {loading ? 'Envoi…' : 'Extraire la recette'}
          </button>
          <div className="p-4 bg-white rounded-xl border border-gray-100 grid grid-cols-2 gap-2 text-sm text-gray-500">
            <span>🎬 YouTube, TikTok, Instagram</span>
            <span>🌐 Marmiton, 750g, AllRecipes…</span>
            <span>📱 Facebook, Twitter/X, Vimeo</span>
            <span>📝 Texte libre (toute langue)</span>
          </div>
        </form>
      )}

      {tab === 'photo' && (
        <form onSubmit={handleSubmitImage} className="space-y-4">
          <input ref={fileRef} type="file" accept="image/*" capture="environment" onChange={handleImageChange} className="hidden" />
          {imagePreview ? (
            <div className="relative">
              <img src={imagePreview} alt="Aperçu" className="w-full rounded-xl max-h-80 object-contain bg-gray-50 border border-gray-200" />
              <button type="button" onClick={() => { setImageFile(null); setImagePreview(null) }}
                className="absolute top-2 right-2 bg-white rounded-full w-8 h-8 flex items-center justify-center shadow text-gray-600 hover:text-red-500">×</button>
            </div>
          ) : (
            <button type="button" onClick={() => fileRef.current?.click()}
              className="w-full h-48 border-2 border-dashed border-gray-200 rounded-xl flex flex-col items-center justify-center gap-3 text-gray-400 hover:border-orange-300 hover:text-orange-500 transition-colors bg-white">
              <span className="text-5xl">📷</span>
              <span className="font-medium">Prendre une photo ou importer</span>
              <span className="text-sm">Recette manuscrite, livre, magazine…</span>
            </button>
          )}
          {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">{error}</div>}
          <button type="submit" disabled={loading || !imageFile} className="w-full py-3 bg-orange-600 hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-colors">
            {loading ? 'OCR en cours…' : 'Extraire depuis la photo'}
          </button>
          <p className="text-xs text-gray-400 text-center">
            Utilise Claude Vision ou Tesseract pour lire le texte.
            Fonctionne avec recettes manuscrites, livres, écrans.
          </p>
        </form>
      )}
    </div>
  )
}
