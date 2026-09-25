import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getRecipe, trackCookingMode, markCooked } from '../api'
import { parseStepTime, formatTime } from '../components/Timer'
import Etoiles from '../components/Etoiles'

const SpeechRecognition = typeof window !== 'undefined'
  && (window.SpeechRecognition || window.webkitSpeechRecognition)

function fold(text) {
  return text.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
}

// Mots reconnus à la voix → action. Testés dans l'ordre : « étape
// précédente » ne doit pas déclencher « étape ».
const COMMANDES = [
  [/\b(precedent|precedente|retour|reviens|avant)\b/, 'prev'],
  [/\b(suivant|suivante|apres|next|ensuite|continue)\b/, 'next'],
  [/\b(repete|relis|lis|redis|quoi)\b/, 'read'],
  [/\b(minuteur|chrono|timer|minute)\b/, 'timer'],
  [/\b(ingredient|ingredients)\b/, 'ingredients'],
  [/\b(termine|fini|finis)\b/, 'finish'],
]

function parler(texte) {
  if (!('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  const u = new SpeechSynthesisUtterance(texte)
  u.lang = 'fr-FR'
  window.speechSynthesis.speak(u)
}

function sonnerie() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    ;[0, 0.35, 0.7].forEach(t => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.frequency.value = 880
      gain.gain.setValueAtTime(0.3, ctx.currentTime + t)
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + t + 0.3)
      osc.connect(gain).connect(ctx.destination)
      osc.start(ctx.currentTime + t)
      osc.stop(ctx.currentTime + t + 0.3)
    })
  } catch { /* pas d'audio */ }
  navigator.vibrate?.([300, 150, 300, 150, 300])
}

// Écran allumé tant que la page est visible. Le navigateur relâche le
// verrou dès qu'on change d'onglet ou qu'on verrouille le téléphone : il
// faut le redemander au retour, sinon l'écran s'éteint dès la 2e étape.
function useWakeLock() {
  const [actif, setActif] = useState(false)
  useEffect(() => {
    if (!('wakeLock' in navigator)) return
    let lock = null
    let annule = false
    const demander = async () => {
      if (document.visibilityState !== 'visible' || annule) return
      try {
        lock = await navigator.wakeLock.request('screen')
        setActif(true)
        lock.addEventListener('release', () => setActif(false))
      } catch { setActif(false) }
    }
    demander()
    document.addEventListener('visibilitychange', demander)
    return () => {
      annule = true
      document.removeEventListener('visibilitychange', demander)
      lock?.release().catch(() => {})
    }
  }, [])
  return actif
}

// Plusieurs minuteurs en parallèle. Calculés depuis leur heure de fin, pas
// décrémentés seconde par seconde : un onglet en arrière-plan (où les
// intervalles sont ralentis) reste juste.
function useMinuteurs() {
  const [timers, setTimers] = useState([])
  const [, setTick] = useState(0)

  const timersRef = useRef(timers)
  timersRef.current = timers

  useEffect(() => {
    if (!timers.some(t => t.endsAt)) return
    const id = setInterval(() => {
      const now = Date.now()
      const finis = timersRef.current.filter(t => t.endsAt && t.endsAt <= now).map(t => t.id)
      if (finis.length) {
        sonnerie()
        parler(timersRef.current.filter(t => finis.includes(t.id)).map(t => `${t.label} : c'est prêt !`).join(' '))
        setTimers(ts => ts.map(t => (finis.includes(t.id) ? { ...t, endsAt: null, remaining: 0, done: true } : t)))
      }
      setTick(n => n + 1)
    }, 500)
    return () => clearInterval(id)
  }, [timers])

  const restant = (t) => (t.endsAt ? Math.max(0, Math.ceil((t.endsAt - Date.now()) / 1000)) : t.remaining)
  const ajouter = useCallback((label, seconds) => {
    setTimers(ts => [...ts, {
      id: `${Date.now()}-${Math.random()}`, label, total: seconds,
      remaining: seconds, endsAt: Date.now() + seconds * 1000, done: false,
    }])
  }, [])
  const basculer = (id) => setTimers(ts => ts.map(t => {
    if (t.id !== id || t.done) return t
    return t.endsAt
      ? { ...t, remaining: restant(t), endsAt: null }
      : { ...t, endsAt: Date.now() + t.remaining * 1000 }
  }))
  const retirer = (id) => setTimers(ts => ts.filter(t => t.id !== id))
  return { timers, ajouter, basculer, retirer, restant }
}

export default function ModeCuisine() {
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [stepIdx, setStepIdx] = useState(0)
  const [showIngredients, setShowIngredients] = useState(false)
  const [voix, setVoix] = useState(false)
  const [entendu, setEntendu] = useState('')
  const [fin, setFin] = useState(false)
  const [note, setNote] = useState(null)
  const [enregistrement, setEnregistrement] = useState(false)
  const ecranAllume = useWakeLock()
  const { timers, ajouter, basculer, retirer, restant } = useMinuteurs()

  const { data: recipe, isError } = useQuery({ queryKey: ['recipe', id], queryFn: () => getRecipe(id) })
  const steps = recipe?.steps || []
  const step = steps[stepIdx]
  const timerSec = step ? parseStepTime(step.text) : null

  useEffect(() => { trackCookingMode() }, [])

  // Les commandes vocales et le clavier passent par une ref : la
  // reconnaissance vocale est créée une fois, elle doit toujours agir sur
  // l'étape courante et non sur celle du moment où elle a démarré.
  const actions = useRef({})
  actions.current = {
    next: () => {
      if (stepIdx >= steps.length - 1) { setFin(true); return }
      setStepIdx(i => i + 1)
    },
    prev: () => setStepIdx(i => Math.max(0, i - 1)),
    read: () => step && parler(`Étape ${stepIdx + 1}. ${step.text}`),
    timer: () => {
      if (timerSec) { ajouter(`Étape ${stepIdx + 1}`, timerSec); parler('Minuteur lancé') }
      else parler("Pas de durée dans cette étape")
    },
    ingredients: () => {
      setShowIngredients(true)
      parler((recipe?.ingredients || []).map(i => [i.quantity, i.unit, i.name].filter(Boolean).join(' ')).join(', '))
    },
    finish: () => setFin(true),
  }

  // En mode mains libres, chaque nouvelle étape est lue à voix haute.
  useEffect(() => {
    if (voix && step) parler(`Étape ${stepIdx + 1}. ${step.text}`)
  }, [voix, stepIdx])

  useEffect(() => {
    if (!voix || !SpeechRecognition) return
    const rec = new SpeechRecognition()
    rec.lang = 'fr-FR'
    rec.continuous = true
    rec.interimResults = false
    let actif = true
    rec.onresult = (event) => {
      // Ignore ce que l'appli dit elle-même (lecture de l'étape).
      if (window.speechSynthesis?.speaking) return
      const texte = fold(event.results[event.results.length - 1][0].transcript)
      setEntendu(texte)
      const commande = COMMANDES.find(([re]) => re.test(texte))
      if (commande) actions.current[commande[1]]()
    }
    // Chrome coupe la reconnaissance après un silence : on la relance tant
    // que le mode mains libres est actif.
    rec.onend = () => { if (actif) { try { rec.start() } catch { /* déjà relancée */ } } }
    rec.onerror = (e) => {
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') { actif = false; setVoix(false) }
    }
    try { rec.start() } catch { /* ignore */ }
    return () => { actif = false; rec.onend = null; rec.stop() }
  }, [voix])

  useEffect(() => () => window.speechSynthesis?.cancel(), [])

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === 'INPUT') return
      if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); actions.current.next() }
      if (e.key === 'ArrowLeft') actions.current.prev()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const ajouterManuel = () => {
    const min = parseFloat((window.prompt('Durée du minuteur (minutes) ?', '5') || '').replace(',', '.'))
    if (min > 0) ajouter(`Minuteur ${timers.length + 1}`, Math.round(min * 60))
  }

  const terminer = async () => {
    setEnregistrement(true)
    try {
      const r = await markCooked(id, { rating: note })
      qc.setQueryData(['recipe', id], r)
      qc.invalidateQueries({ queryKey: ['recipes'] })
      qc.invalidateQueries({ queryKey: ['cook-history', id] })
    } finally {
      navigate(`/recettes/${id}`)
    }
  }

  if (isError) return (
    <div className="fixed inset-0 bg-gray-950 text-white flex flex-col items-center justify-center gap-4">
      <p>Impossible de charger la recette.</p>
      <Link to={`/recettes/${id}`} className="text-orange-400 hover:underline">← Retour</Link>
    </div>
  )
  if (!recipe) return <div className="fixed inset-0 bg-gray-950 text-white flex items-center justify-center">Chargement…</div>

  return (
    <div className="fixed inset-0 bg-gray-950 text-white flex flex-col select-none z-50">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 px-4 sm:px-6 py-3 border-b border-gray-800">
        <Link to={`/recettes/${id}`} className="text-gray-400 hover:text-white text-sm flex-shrink-0">← Sortir</Link>
        <span className="font-semibold text-lg line-clamp-1 text-center">{recipe.title}</span>
        <span className="text-gray-400 text-sm flex-shrink-0">{steps.length ? `${stepIdx + 1} / ${steps.length}` : ''}</span>
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-gray-800">
        <div className="h-1 bg-orange-500 transition-all duration-300"
          style={{ width: `${steps.length ? ((stepIdx + 1) / steps.length) * 100 : 0}%` }} />
      </div>

      {/* Barre d'outils : écran, voix, minuteurs */}
      <div className="flex items-center gap-2 px-4 sm:px-6 py-2 text-xs flex-wrap border-b border-gray-900">
        <span className={ecranAllume ? 'text-green-400' : 'text-gray-500'} title="L'écran ne se mettra pas en veille">
          {ecranAllume ? '🔆 Écran allumé' : '🔅 Veille possible'}
        </span>
        {SpeechRecognition ? (
          <button onClick={() => setVoix(v => !v)}
            className={`px-3 py-1 rounded-full font-medium ${voix ? 'bg-red-600 text-white animate-pulse' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'}`}>
            🎤 {voix ? 'Mains libres activé' : 'Mains libres'}
          </button>
        ) : (
          <span className="text-gray-600">🎤 Commande vocale non prise en charge par ce navigateur</span>
        )}
        <button onClick={ajouterManuel} className="px-3 py-1 rounded-full bg-gray-800 text-gray-300 hover:bg-gray-700">+ Minuteur</button>
        {voix && (
          <span className="text-gray-500 truncate">
            Dites « suivant », « précédent », « répète », « minuteur », « ingrédients »{entendu && ` · entendu : « ${entendu} »`}
          </span>
        )}
      </div>

      {timers.length > 0 && (
        <div className="flex gap-2 px-4 sm:px-6 py-2 overflow-x-auto border-b border-gray-900">
          {timers.map(t => {
            const r = restant(t)
            return (
              <div key={t.id} className={`flex-shrink-0 flex items-center gap-2 pl-3 pr-1 py-1 rounded-full font-mono text-sm ${
                t.done ? 'bg-green-600 text-white animate-pulse' : t.endsAt ? 'bg-orange-600/20 text-orange-300 border border-orange-600' : 'bg-gray-800 text-gray-400'
              }`}>
                <span className="font-sans text-xs opacity-80">{t.label}</span>
                <span>{t.done ? 'Prêt !' : formatTime(r)}</span>
                {!t.done && (
                  <button onClick={() => basculer(t.id)} className="px-1 hover:text-white" title={t.endsAt ? 'Pause' : 'Reprendre'}>
                    {t.endsAt ? '⏸' : '▶'}
                  </button>
                )}
                <button onClick={() => retirer(t.id)} className="px-1 hover:text-white" title="Retirer">×</button>
              </div>
            )
          })}
        </div>
      )}

      {/* Step */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 sm:px-8 gap-8 overflow-y-auto">
        {steps.length === 0 ? (
          <p className="text-gray-400">Cette recette n'a pas d'étapes.</p>
        ) : (
          <>
            <div className="w-14 h-14 rounded-full bg-orange-600 flex items-center justify-center text-2xl font-bold">
              {stepIdx + 1}
            </div>
            <p className="text-2xl md:text-3xl text-center leading-relaxed max-w-3xl font-medium">{step?.text}</p>
            {timerSec && (
              <button onClick={() => actions.current.timer()}
                className="px-5 py-2 rounded-full bg-gray-800 hover:bg-gray-700 text-orange-300 font-mono">
                ⏱ Lancer {formatTime(timerSec)}
              </button>
            )}
          </>
        )}
      </div>

      {recipe.ingredients?.length > 0 && (
        <details open={showIngredients} onToggle={e => setShowIngredients(e.currentTarget.open)} className="mx-6 mb-4">
          <summary className="text-sm text-gray-400 cursor-pointer select-none">📋 Ingrédients</summary>
          <ul className="mt-2 grid grid-cols-2 gap-1 text-sm text-gray-300 max-h-40 overflow-y-auto">
            {recipe.ingredients.map((ing, i) => (
              <li key={i}>{[ing.quantity, ing.unit, ing.name].filter(Boolean).join(' ')}</li>
            ))}
          </ul>
        </details>
      )}

      {/* Navigation */}
      <div className="flex items-center gap-4 px-6 pb-8 justify-between">
        <button onClick={() => actions.current.prev()} disabled={stepIdx === 0}
          className="flex-1 py-4 rounded-2xl bg-gray-800 disabled:opacity-30 text-xl font-bold hover:bg-gray-700 transition-colors">
          ←
        </button>
        {stepIdx >= steps.length - 1 ? (
          <button onClick={() => setFin(true)}
            className="flex-1 py-4 rounded-2xl bg-green-600 text-white text-center text-lg font-bold hover:bg-green-500">
            ✓ Terminé !
          </button>
        ) : (
          <button onClick={() => actions.current.next()}
            className="flex-1 py-4 rounded-2xl bg-orange-600 text-xl font-bold hover:bg-orange-500 transition-colors">
            →
          </button>
        )}
      </div>

      {fin && (
        <div className="absolute inset-0 bg-black/70 flex items-center justify-center p-4">
          <div className="bg-white text-gray-900 rounded-2xl p-6 w-full max-w-sm text-center space-y-4">
            <div className="text-5xl">🍽️</div>
            <p className="text-xl font-bold">Bon appétit !</p>
            <p className="text-sm text-gray-500">Comment c'était ?</p>
            <Etoiles value={note} onChange={setNote} size="text-3xl" />
            <button onClick={terminer} disabled={enregistrement}
              className="w-full py-3 bg-green-600 text-white rounded-xl font-semibold hover:bg-green-700 disabled:opacity-50">
              ✓ Marquer comme cuisinée
            </button>
            <div className="flex justify-between text-sm">
              <button onClick={() => setFin(false)} className="text-gray-500 hover:underline">← Revenir aux étapes</button>
              <Link to={`/recettes/${id}`} className="text-gray-500 hover:underline">Sortir sans noter</Link>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
