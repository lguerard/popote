import { useState } from 'react'
import { login, register } from '../api'
import { useAuth } from '../auth'

export default function Connexion() {
  const { memoriser } = useAuth()
  const [inscription, setInscription] = useState(false)
  const [nom, setNom] = useState('')
  const [email, setEmail] = useState('')
  const [motDePasse, setMotDePasse] = useState('')
  const [erreur, setErreur] = useState(null)
  const [envoi, setEnvoi] = useState(false)

  async function soumettre(e) {
    e.preventDefault()
    setErreur(null)
    setEnvoi(true)
    try {
      const reponse = inscription
        ? await register({ email, password: motDePasse, display_name: nom })
        : await login({ email, password: motDePasse })
      memoriser(reponse)
    } catch (err) {
      // Le backend renvoie un message utilisable ; on ne garde le
      // générique que s'il n'a rien dit (réseau coupé, 500 nu).
      setErreur(err?.response?.data?.detail || 'Connexion impossible, réessaie.')
    } finally {
      setEnvoi(false)
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-16">
      <div className="text-center mb-8">
        <div className="text-5xl mb-2">🍲</div>
        <h1 className="text-2xl font-bold text-gray-800">Popote</h1>
        <p className="text-sm text-gray-500 mt-1">
          {inscription ? 'Créer un compte' : 'Connexion à ta cuisine'}
        </p>
      </div>

      <form onSubmit={soumettre} className="space-y-3 bg-white p-6 rounded-xl border border-gray-100">
        {inscription && (
          <input
            value={nom} onChange={e => setNom(e.target.value)}
            placeholder="Ton prénom" required maxLength={100}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-300"
          />
        )}
        <input
          type="email" value={email} onChange={e => setEmail(e.target.value)}
          placeholder="Adresse e-mail" required autoComplete="username"
          className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-300"
        />
        <input
          type="password" value={motDePasse} onChange={e => setMotDePasse(e.target.value)}
          placeholder="Mot de passe" required minLength={8}
          autoComplete={inscription ? 'new-password' : 'current-password'}
          className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-300"
        />
        {inscription && (
          <p className="text-xs text-gray-400">8 caractères minimum.</p>
        )}

        {erreur && (
          <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{erreur}</p>
        )}

        <button
          type="submit" disabled={envoi}
          className="w-full py-2 rounded-lg bg-orange-600 text-white font-medium hover:bg-orange-700 disabled:opacity-50"
        >
          {envoi ? 'Un instant…' : inscription ? 'Créer le compte' : 'Se connecter'}
        </button>
      </form>

      <button
        onClick={() => { setInscription(!inscription); setErreur(null) }}
        className="mt-4 w-full text-sm text-orange-600 hover:underline"
      >
        {inscription ? "J'ai déjà un compte" : 'Créer un compte'}
      </button>
    </div>
  )
}
