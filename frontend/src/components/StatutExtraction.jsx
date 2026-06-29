import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getTaskStatus } from '../api'

const MESSAGES = {
  pending: 'En attente…',
  processing: 'Extraction en cours…',
  done: 'Recette extraite !',
  failed: 'Échec de l\'extraction',
}

export default function StatutExtraction({ recipeId, onError }) {
  const [status, setStatus] = useState('pending')
  const [errorMsg, setErrorMsg] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (!recipeId) return
    const interval = setInterval(async () => {
      try {
        const data = await getTaskStatus(recipeId)
        setStatus(data.status)
        if (data.status === 'done') {
          clearInterval(interval)
          navigate(`/recettes/${recipeId}`)
        } else if (data.status === 'failed') {
          clearInterval(interval)
          setErrorMsg(data.error_msg || 'Erreur inconnue')
          onError?.(data.error_msg)
        }
      } catch (e) {
        clearInterval(interval)
      }
    }, 2000)
    return () => clearInterval(interval)
  }, [recipeId, navigate, onError])

  return (
    <div className="flex flex-col items-center gap-4 py-12">
      {status !== 'failed' ? (
        <div className="w-16 h-16 border-4 border-orange-200 border-t-orange-600 rounded-full animate-spin" />
      ) : (
        <div className="text-5xl">❌</div>
      )}
      <p className="text-lg font-medium text-gray-700">{MESSAGES[status]}</p>
      {errorMsg && <p className="text-sm text-red-500 max-w-md text-center">{errorMsg}</p>}
    </div>
  )
}
