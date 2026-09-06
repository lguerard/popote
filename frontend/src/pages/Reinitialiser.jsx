import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { checkResetToken, messageErreur, resetPassword } from '../api'

/** Page ouverte via le lien à usage unique généré par un administrateur.
 *  Accessible sans être connecté. */
export default function Reinitialiser() {
  const { token } = useParams()
  const [cible, setCible] = useState(null) // { valid, email }
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [erreur, setErreur] = useState(null)
  const [fait, setFait] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let annule = false
    checkResetToken(token)
      .then((r) => { if (!annule) setCible(r) })
      .catch(() => { if (!annule) setCible({ valid: false }) })
    return () => { annule = true }
  }, [token])

  const envoyer = async (e) => {
    e.preventDefault()
    setErreur(null)
    if (password.length < 8) return setErreur('Mot de passe : 8 caractères minimum.')
    if (password !== confirmation) return setErreur('Les deux mots de passe ne correspondent pas.')
    setBusy(true)
    try {
      await resetPassword(token, password)
      setFait(true)
    } catch (err) {
      setErreur(messageErreur(err, 'Réinitialisation impossible'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-orange-50 px-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-sm border border-orange-100 p-6">
        <div className="text-center mb-5">
          <div className="text-4xl mb-1">🍳</div>
          <h1 className="text-xl font-bold text-orange-600">Nouveau mot de passe</h1>
        </div>

        {cible === null && <p className="text-sm text-gray-500 text-center">Vérification du lien…</p>}

        {cible && !cible.valid && (
          <>
            <p className="text-sm text-red-600">Ce lien est invalide, expiré ou déjà utilisé.</p>
            <p className="text-sm text-gray-500 mt-2">Demande un nouveau lien à un administrateur.</p>
            <Link to="/" className="block text-center mt-4 text-orange-600 hover:underline">
              ← Retour à la connexion
            </Link>
          </>
        )}

        {cible?.valid && fait && (
          <>
            <p className="text-sm text-green-700">Mot de passe enregistré. Tu peux te connecter.</p>
            <Link to="/" className="block text-center mt-4 py-2 rounded-lg bg-orange-600 text-white font-medium hover:bg-orange-700">
              Se connecter
            </Link>
          </>
        )}

        {cible?.valid && !fait && (
          <form onSubmit={envoyer} className="space-y-3">
            <p className="text-sm text-gray-500">Choisis un nouveau mot de passe pour {cible.email}.</p>
            <div>
              <label className="block text-sm text-gray-600 mb-1" htmlFor="mdp">Mot de passe (8 caractères minimum)</label>
              <input id="mdp" type="password" autoComplete="new-password" required
                     className="w-full px-3 py-2 rounded-lg border border-gray-200 focus:border-orange-400 focus:ring-1 focus:ring-orange-400 outline-none"
                     value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1" htmlFor="conf">Confirme le mot de passe</label>
              <input id="conf" type="password" autoComplete="new-password" required
                     className="w-full px-3 py-2 rounded-lg border border-gray-200 focus:border-orange-400 focus:ring-1 focus:ring-orange-400 outline-none"
                     value={confirmation} onChange={(e) => setConfirmation(e.target.value)} />
            </div>
            {erreur && <p className="text-sm text-red-600">{erreur}</p>}
            <button type="submit" disabled={busy}
                    className="w-full py-2 rounded-lg bg-orange-600 text-white font-medium hover:bg-orange-700 disabled:opacity-50">
              {busy ? 'Enregistrement…' : 'Enregistrer le mot de passe'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
