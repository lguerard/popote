import { useState } from 'react'
import { publicLink } from '../api'

// Lien public en lecture seule : créer, copier, révoquer.
export default function LienPartage({ token, path, onShare, onUnshare, busy, label = 'Partager par lien' }) {
  const [copie, setCopie] = useState(false)
  if (!token) {
    return (
      <button onClick={onShare} disabled={busy}
        className="px-3 py-2 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg disabled:opacity-50">
        🔗 {label}
      </button>
    )
  }
  const url = publicLink(path)
  const copier = async () => {
    try {
      if (navigator.share && /Android|iPhone|iPad/i.test(navigator.userAgent)) {
        await navigator.share({ url })
        return
      }
      await navigator.clipboard.writeText(url)
      setCopie(true)
      setTimeout(() => setCopie(false), 2000)
    } catch { /* partage annulé */ }
  }
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <input readOnly value={url} onFocus={e => e.target.select()}
        className="flex-1 min-w-0 px-3 py-2 rounded-lg border border-gray-200 bg-gray-50 text-gray-600" />
      <button onClick={copier} className="px-3 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700">
        {copie ? '✓ Copié' : 'Copier'}
      </button>
      <button onClick={onUnshare} disabled={busy} title="Le lien actuel cessera de fonctionner"
        className="px-3 py-2 text-red-600 bg-red-50 hover:bg-red-100 rounded-lg disabled:opacity-50">
        Révoquer
      </button>
    </div>
  )
}
