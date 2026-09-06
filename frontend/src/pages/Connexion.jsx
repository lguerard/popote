import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { messageErreur, setupFirstAccount } from '../api'

/** Écran de connexion. Tant qu'aucun compte n'existe, il propose à la place la
 *  création du premier — qui devient administrateur. */
export default function Connexion() {
  const { needsSetup, signIn, refresh, setUser } = useAuth()
  return needsSetup ? <PremierCompte onCreated={(u) => { setUser(u); refresh() }} /> : <FormulaireConnexion signIn={signIn} />
}

function Cadre({ titre, sousTitre, children }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-orange-50 px-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-sm border border-orange-100 p-6">
        <div className="text-center mb-5">
          <div className="text-4xl mb-1">🍳</div>
          <h1 className="text-xl font-bold text-orange-600">{titre}</h1>
          <p className="text-sm text-gray-500 mt-1">{sousTitre}</p>
        </div>
        {children}
      </div>
    </div>
  )
}

const champ =
  'w-full px-3 py-2 rounded-lg border border-gray-200 focus:border-orange-400 focus:ring-1 focus:ring-orange-400 outline-none'
const bouton =
  'w-full py-2 rounded-lg bg-orange-600 text-white font-medium hover:bg-orange-700 disabled:opacity-50'

function FormulaireConnexion({ signIn }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [erreur, setErreur] = useState(null)
  const [busy, setBusy] = useState(false)

  const envoyer = async (e) => {
    e.preventDefault()
    setErreur(null)
    setBusy(true)
    try {
      await signIn(email, password)
    } catch (err) {
      setErreur(messageErreur(err, 'Connexion impossible'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Cadre titre="Popote" sousTitre="Connecte-toi pour accéder aux recettes.">
      <form onSubmit={envoyer} className="space-y-3">
        <div>
          <label className="block text-sm text-gray-600 mb-1" htmlFor="email">Adresse e-mail</label>
          <input id="email" type="email" autoComplete="email" required className={champ}
                 value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1" htmlFor="password">Mot de passe</label>
          <input id="password" type="password" autoComplete="current-password" required className={champ}
                 value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {erreur && <p className="text-sm text-red-600">{erreur}</p>}
        <button type="submit" className={bouton} disabled={busy}>
          {busy ? 'Connexion…' : 'Se connecter'}
        </button>
      </form>
      <p className="text-xs text-gray-400 text-center mt-4">
        Mot de passe oublié ? Demande un lien de réinitialisation à un administrateur.
      </p>
    </Cadre>
  )
}

function PremierCompte({ onCreated }) {
  const [form, setForm] = useState({ email: '', display_name: '', password: '' })
  const [erreur, setErreur] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const envoyer = async (e) => {
    e.preventDefault()
    setErreur(null)
    if (form.password.length < 8) return setErreur('Mot de passe : 8 caractères minimum.')
    setBusy(true)
    try {
      const { user } = await setupFirstAccount(form)
      onCreated(user)
    } catch (err) {
      setErreur(messageErreur(err, 'Création impossible'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Cadre titre="Bienvenue dans Popote" sousTitre="Crée le premier compte — il sera administrateur.">
      <form onSubmit={envoyer} className="space-y-3">
        <div>
          <label className="block text-sm text-gray-600 mb-1" htmlFor="nom">Nom affiché</label>
          <input id="nom" required className={champ} value={form.display_name} onChange={set('display_name')} />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1" htmlFor="email">Adresse e-mail</label>
          <input id="email" type="email" autoComplete="email" required className={champ}
                 value={form.email} onChange={set('email')} />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1" htmlFor="mdp">Mot de passe (8 caractères minimum)</label>
          <input id="mdp" type="password" autoComplete="new-password" required className={champ}
                 value={form.password} onChange={set('password')} />
        </div>
        {erreur && <p className="text-sm text-red-600">{erreur}</p>}
        <button type="submit" className={bouton} disabled={busy}>
          {busy ? 'Création…' : 'Créer le compte'}
        </button>
      </form>
    </Cadre>
  )
}
