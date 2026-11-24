import { useState } from 'react'
import { browserSupportsWebAuthn, startAuthentication } from '@simplewebauthn/browser'
import { finishPasskeyLogin, login, register, startPasskeyLogin } from '../api'
import { useAuth } from '../auth'

export default function Connexion() {
  const { memoriser } = useAuth()
  const [inscription, setInscription] = useState(false)
  const [nom, setNom] = useState('')
  const [email, setEmail] = useState('')
  const [motDePasse, setMotDePasse] = useState('')
  const [erreur, setErreur] = useState(null)
  const [message, setMessage] = useState(null)
  const [envoi, setEnvoi] = useState(false)

  async function soumettre(e) {
    e.preventDefault()
    setErreur(null)
    setMessage(null)
    setEnvoi(true)
    try {
      if (inscription) {
        // Une inscription ne renvoie pas de jeton : la demande attend la
        // validation d'un administrateur. On repasse donc en mode
        // connexion avec le message du serveur.
        const { message } = await register({ email, password: motDePasse, display_name: nom })
        setMessage(message)
        setInscription(false)
        setMotDePasse('')
        return
      }
      memoriser(await login({ email, password: motDePasse }))
    } catch (err) {
      // Le backend renvoie un message utilisable ; on ne garde le
      // générique que s'il n'a rien dit (réseau coupé, 500 nu).
      setErreur(err?.response?.data?.detail || 'Connexion impossible, réessaie.')
    } finally {
      setEnvoi(false)
    }
  }

  async function connexionPasskey() {
    setErreur(null)
    setMessage(null)
    setEnvoi(true)
    try {
      // L'e-mail est facultatif : vide, le navigateur propose les passkeys
      // qu'il connaît pour ce site.
      const { options, challenge_id } = await startPasskeyLogin(email.trim())
      let credential
      try {
        credential = await startAuthentication({ optionsJSON: options })
      } catch (err) {
        // NotAllowedError : fenêtre fermée, délai dépassé ou aucune passkey
        // choisie -- le navigateur ne dit pas lequel.
        setErreur(err?.name === 'NotAllowedError'
          ? 'Connexion par passkey annulée.'
          : "Passkey indisponible sur ce navigateur ou cette adresse (HTTPS requis).")
        return
      }
      memoriser(await finishPasskeyLogin({ challenge_id, credential }))
    } catch (err) {
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
          {inscription ? 'Demander un compte' : 'Connexion à ta cuisine'}
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

        {message && (
          <p className="text-sm text-emerald-700 bg-emerald-50 rounded-lg px-3 py-2">{message}</p>
        )}
        {erreur && (
          <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{erreur}</p>
        )}

        <button
          type="submit" disabled={envoi}
          className="w-full py-2 rounded-lg bg-orange-600 text-white font-medium hover:bg-orange-700 disabled:opacity-50"
        >
          {envoi ? 'Un instant…' : inscription ? 'Demander un compte' : 'Se connecter'}
        </button>
      </form>

      {!inscription && browserSupportsWebAuthn() && (
        <button
          type="button" onClick={connexionPasskey} disabled={envoi}
          className="mt-3 w-full py-2 rounded-lg border border-orange-200 bg-white text-orange-700 font-medium hover:bg-orange-50 disabled:opacity-50"
        >
          🔐 Se connecter avec une clé de sécurité / un passkey
        </button>
      )}

      <button
        onClick={() => { setInscription(!inscription); setErreur(null); setMessage(null) }}
        className="mt-4 w-full text-sm text-orange-600 hover:underline"
      >
        {inscription ? "J'ai déjà un compte" : 'Demander un compte'}
      </button>
    </div>
  )
}
