import { useState, useEffect, useRef } from 'react'

export function parseStepTime(text) {
  const RE = /(\d+)\s*(heure?s?|h\b|min(?:ute)?s?|sec(?:onde)?s?)/gi
  let match; let totalSec = 0; let found = false
  while ((match = RE.exec(text)) !== null) {
    found = true
    const n = parseInt(match[1])
    const unit = match[2].toLowerCase()
    if (unit.startsWith('h')) totalSec += n * 3600
    else if (unit.startsWith('min')) totalSec += n * 60
    else totalSec += n
  }
  return found ? totalSec : null
}

export function formatTime(sec) {
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  if (h > 0) return `${h}h${String(m).padStart(2, '0')}m${String(s).padStart(2, '0')}s`
  if (m > 0) return `${m}m${String(s).padStart(2, '0')}s`
  return `${s}s`
}

export default function StepTimer({ seconds, label }) {
  const [remaining, setRemaining] = useState(seconds)
  const [running, setRunning] = useState(false)
  const [done, setDone] = useState(false)
  const intervalRef = useRef(null)

  useEffect(() => {
    if (running && remaining > 0) {
      intervalRef.current = setInterval(() => {
        setRemaining(r => {
          if (r <= 1) {
            clearInterval(intervalRef.current)
            setRunning(false)
            setDone(true)
            return 0
          }
          return r - 1
        })
      }, 1000)
    }
    return () => clearInterval(intervalRef.current)
  }, [running])

  const reset = () => { setRemaining(seconds); setRunning(false); setDone(false) }

  return (
    <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-mono font-medium border ${
      done ? 'bg-green-50 border-green-300 text-green-700'
           : running ? 'bg-orange-50 border-orange-300 text-orange-700'
           : 'bg-gray-50 border-gray-200 text-gray-600'
    }`}>
      {done ? (
        <>
          <span>✓</span>
          <span>Terminé !</span>
          <button onClick={reset} className="text-xs underline opacity-70 hover:opacity-100">↺</button>
        </>
      ) : (
        <>
          <span>⏱</span>
          <span>{formatTime(remaining)}</span>
          <button
            onClick={() => setRunning(r => !r)}
            className="text-xs underline opacity-70 hover:opacity-100"
          >
            {running ? 'Pause' : remaining === seconds ? 'Démarrer' : 'Reprendre'}
          </button>
          {remaining < seconds && <button onClick={reset} className="text-xs underline opacity-70 hover:opacity-100">↺</button>}
        </>
      )}
    </div>
  )
}
