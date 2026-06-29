import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getRecipe, trackCookingMode } from '../api'
import StepTimer, { parseStepTime } from '../components/Timer'

export default function ModeCuisine() {
  const { id } = useParams()
  const [stepIdx, setStepIdx] = useState(0)

  const { data: recipe } = useQuery({ queryKey: ['recipe', id], queryFn: () => getRecipe(id) })

  // Wake Lock + achievement
  useEffect(() => {
    let lock = null
    if ('wakeLock' in navigator) {
      navigator.wakeLock.request('screen').then(l => { lock = l }).catch(() => {})
    }
    trackCookingMode()
    return () => { lock?.release() }
  }, [])

  if (!recipe) return <div className="flex items-center justify-center h-screen">Chargement…</div>

  const steps = recipe.steps || []
  const step = steps[stepIdx]
  const timerSec = step ? parseStepTime(step.text) : null

  return (
    <div className="fixed inset-0 bg-gray-950 text-white flex flex-col select-none">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
        <Link to={`/recettes/${id}`} className="text-gray-400 hover:text-white text-sm">← Sortir</Link>
        <span className="font-semibold text-lg line-clamp-1">{recipe.title}</span>
        <span className="text-gray-400 text-sm">{stepIdx + 1} / {steps.length}</span>
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-gray-800">
        <div
          className="h-1 bg-orange-500 transition-all duration-300"
          style={{ width: `${((stepIdx + 1) / steps.length) * 100}%` }}
        />
      </div>

      {/* Step */}
      <div className="flex-1 flex flex-col items-center justify-center px-8 gap-8">
        <div className="w-14 h-14 rounded-full bg-orange-600 flex items-center justify-center text-2xl font-bold">
          {stepIdx + 1}
        </div>
        <p className="text-2xl md:text-3xl text-center leading-relaxed max-w-3xl font-medium">
          {step?.text}
        </p>
        {timerSec && <StepTimer seconds={timerSec} label={`Étape ${stepIdx + 1}`} />}
      </div>

      {/* Ingrédients (mini) en bas à gauche */}
      {recipe.ingredients?.length > 0 && (
        <details className="mx-6 mb-4">
          <summary className="text-sm text-gray-400 cursor-pointer select-none">📋 Ingrédients</summary>
          <ul className="mt-2 grid grid-cols-2 gap-1 text-sm text-gray-300">
            {recipe.ingredients.map((ing, i) => (
              <li key={i}>{[ing.quantity, ing.unit, ing.name].filter(Boolean).join(' ')}</li>
            ))}
          </ul>
        </details>
      )}

      {/* Navigation */}
      <div className="flex items-center gap-4 px-6 pb-8 justify-between">
        <button
          onClick={() => setStepIdx(i => Math.max(0, i - 1))}
          disabled={stepIdx === 0}
          className="flex-1 py-4 rounded-2xl bg-gray-800 disabled:opacity-30 text-xl font-bold hover:bg-gray-700 transition-colors"
        >
          ←
        </button>
        {stepIdx === steps.length - 1 ? (
          <Link to={`/recettes/${id}`} className="flex-1 py-4 rounded-2xl bg-green-600 text-white text-center text-lg font-bold hover:bg-green-500">
            ✓ Terminé !
          </Link>
        ) : (
          <button
            onClick={() => setStepIdx(i => Math.min(steps.length - 1, i + 1))}
            className="flex-1 py-4 rounded-2xl bg-orange-600 text-xl font-bold hover:bg-orange-500 transition-colors"
          >
            →
          </button>
        )}
      </div>
    </div>
  )
}
