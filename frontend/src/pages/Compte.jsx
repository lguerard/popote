import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import {
  changePassword,
  createResetLink,
  createUser,
  deleteUser,
  getUsers,
  messageErreur,
  setUserRole,
} from '../api'

const champ =
  'w-full px-3 py-2 rounded-lg border border-gray-200 focus:border-orange-400 focus:ring-1 focus:ring-orange-400 outline-none'
const boutonPrincipal =
  'px-4 py-2 rounded-lg bg-orange-600 text-white font-medium hover:bg-orange-700 disabled:opacity-50'
const boutonDiscret =
  'px-3 py-1.5 rounded-lg text-sm border border-gray-200 hover:bg-orange-50 disabled:opacity-50'

export default function Compte() {
  const { user } = useAuth()
  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Mon compte</h1>
        <p className="text-gray-500 text-sm mt-1">{user.display_name} — {user.email}</p>
      </div>
      <ChangerMotDePasse />
      {user.is_admin && <GestionComptes moiId={user.id} />}
    </div>
  )
}

function Carte({ titre, children }) {
  return (
    <section className="bg-white rounded-xl border border-orange-100 shadow-sm p-5">
      <h2 className="font-semibold text-gray-800 mb-3">{titre}</h2>
      {children}
    </section>
  )
}

function ChangerMotDePasse() {
  const [actuel, setActuel] = useState('')
  const [nouveau, setNouveau] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [erreur, setErreur] = useState(null)
  const [ok, setOk] = useState(false)
  const [busy, setBusy] = useState(false)

  const envoyer = async (e) => {
    e.preventDefault()
    setErreur(null)
    setOk(false)
    if (nouveau.length < 8) return setErreur('Mot de passe : 8 caractères minimum.')
    if (nouveau !== confirmation) return setErreur('Les deux mots de passe ne correspondent pas.')
    setBusy(true)
    try {
      await changePassword(actuel, nouveau)
      setOk(true)
      setActuel(''); setNouveau(''); setConfirmation('')
    } catch (err) {
      setErreur(messageErreur(err, 'Changement impossible'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Carte titre="Changer le mot de passe">
      <form onSubmit={envoyer} className="space-y-3">
        <div>
          <label className="block text-sm text-gray-600 mb-1" htmlFor="actuel">Mot de passe actuel</label>
          <input id="actuel" type="password" autoComplete="current-password" required className={champ}
                 value={actuel} onChange={(e) => setActuel(e.target.value)} />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1" htmlFor="nouveau">Nouveau mot de passe (8 caractères minimum)</label>
          <input id="nouveau" type="password" autoComplete="new-password" required className={champ}
                 value={nouveau} onChange={(e) => setNouveau(e.target.value)} />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1" htmlFor="conf">Confirme le nouveau mot de passe</label>
          <input id="conf" type="password" autoComplete="new-password" required className={champ}
                 value={confirmation} onChange={(e) => setConfirmation(e.target.value)} />
        </div>
        {erreur && <p className="text-sm text-red-600">{erreur}</p>}
        {ok && <p className="text-sm text-green-700">Mot de passe modifié.</p>}
        <p className="text-xs text-gray-400">
          Tes autres appareils seront déconnectés ; ce navigateur reste connecté.
        </p>
        <button type="submit" className={boutonPrincipal} disabled={busy}>
          {busy ? 'Enregistrement…' : 'Changer le mot de passe'}
        </button>
      </form>
    </Carte>
  )
}

function GestionComptes({ moiId }) {
  const [comptes, setComptes] = useState([])
  const [erreur, setErreur] = useState(null)
  const [lien, setLien] = useState(null) // { email, reset_url }
  const [copie, setCopie] = useState(false)
  const [ajout, setAjout] = useState(false)

  const charger = () => getUsers().then(setComptes).catch((e) => setErreur(messageErreur(e)))
  useEffect(() => { charger() }, [])

  const action = async (fn) => {
    setErreur(null)
    try {
      await fn()
      await charger()
    } catch (e) {
      setErreur(messageErreur(e))
    }
  }

  const genererLien = async (id) => {
    setErreur(null)
    setCopie(false)
    try {
      setLien(await createResetLink(id))
    } catch (e) {
      setErreur(messageErreur(e))
    }
  }

  const copier = async (url) => {
    try {
      await navigator.clipboard.writeText(url)
      setCopie(true)
      setTimeout(() => setCopie(false), 2000)
    } catch {
      setCopie(false) // presse-papiers bloqué (http, permissions) : le lien reste affiché
    }
  }

  return (
    <Carte titre="Comptes">
      <p className="text-sm text-gray-500 mb-3">
        Popote n'envoie pas d'e-mail : pour un mot de passe oublié, génère un lien
        à usage unique (valable 24 h) et transmets-le toi-même.
      </p>

      {lien && (
        <div className="mb-4 p-3 rounded-lg bg-orange-50 border border-orange-200">
          <p className="text-sm font-medium text-gray-800">Lien pour {lien.email}</p>
          <code className="block mt-1 text-xs break-all bg-white rounded p-2 border border-orange-100">
            {lien.reset_url}
          </code>
          <div className="flex items-center gap-2 mt-2">
            <button type="button" className={boutonDiscret} onClick={() => copier(lien.reset_url)}>
              {copie ? 'Copié !' : 'Copier'}
            </button>
            <button type="button" className={boutonDiscret} onClick={() => setLien(null)}>Fermer</button>
          </div>
          <p className="text-xs text-gray-500 mt-2">
            Utilisable une seule fois. Il ne sera plus réaffiché : copie-le maintenant.
          </p>
        </div>
      )}

      {erreur && <p className="text-sm text-red-600 mb-3">{erreur}</p>}

      <ul className="divide-y divide-gray-100">
        {comptes.map((c) => (
          <li key={c.id} className="py-3 flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="font-medium text-gray-800 truncate">
                {c.display_name}
                {c.is_admin && (
                  <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700">admin</span>
                )}
              </p>
              <p className="text-sm text-gray-500 truncate">{c.email}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" className={boutonDiscret} onClick={() => genererLien(c.id)}>
                🔑 Lien de réinitialisation
              </button>
              <button type="button" className={boutonDiscret}
                      onClick={() => action(() => setUserRole(c.id, !c.is_admin))}>
                {c.is_admin ? 'Retirer admin' : 'Passer admin'}
              </button>
              {c.id !== moiId && (
                <button type="button" className={`${boutonDiscret} text-red-600`}
                        onClick={() => {
                          if (confirm(`Supprimer le compte de ${c.display_name} ?`)) {
                            action(() => deleteUser(c.id))
                          }
                        }}>
                  Supprimer
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>

      {ajout ? (
        <NouveauCompte
          onDone={() => { setAjout(false); charger() }}
          onCancel={() => setAjout(false)}
          onError={setErreur}
        />
      ) : (
        <button type="button" className={`${boutonDiscret} mt-3`} onClick={() => setAjout(true)}>
          + Ajouter un compte
        </button>
      )}
    </Carte>
  )
}

function NouveauCompte({ onDone, onCancel, onError }) {
  const [form, setForm] = useState({ email: '', display_name: '', password: '', is_admin: false })
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) =>
    setForm((f) => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  const envoyer = async (e) => {
    e.preventDefault()
    if (form.password.length < 8) return onError('Mot de passe : 8 caractères minimum.')
    setBusy(true)
    try {
      await createUser(form)
      onDone()
    } catch (err) {
      onError(messageErreur(err, 'Création impossible'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={envoyer} className="mt-4 pt-4 border-t border-gray-100 space-y-3">
      <div>
        <label className="block text-sm text-gray-600 mb-1" htmlFor="n-nom">Nom affiché</label>
        <input id="n-nom" required className={champ} value={form.display_name} onChange={set('display_name')} />
      </div>
      <div>
        <label className="block text-sm text-gray-600 mb-1" htmlFor="n-email">Adresse e-mail</label>
        <input id="n-email" type="email" required className={champ} value={form.email} onChange={set('email')} />
      </div>
      <div>
        <label className="block text-sm text-gray-600 mb-1" htmlFor="n-mdp">Mot de passe provisoire (8 caractères minimum)</label>
        <input id="n-mdp" type="password" required className={champ} value={form.password} onChange={set('password')} />
      </div>
      <label className="flex items-center gap-2 text-sm text-gray-600">
        <input type="checkbox" checked={form.is_admin} onChange={set('is_admin')} />
        Administrateur
      </label>
      <div className="flex gap-2">
        <button type="submit" className={boutonPrincipal} disabled={busy}>
          {busy ? 'Création…' : 'Créer le compte'}
        </button>
        <button type="button" className={boutonDiscret} onClick={onCancel}>Annuler</button>
      </div>
    </form>
  )
}
