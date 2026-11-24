import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { browserSupportsWebAuthn, startRegistration } from '@simplewebauthn/browser'
import { deletePasskey, finishPasskeyRegistration, listPasskeys, startPasskeyRegistration } from '../api'
import { useAuth } from '../auth'

const NAV = [
  { to: '/', label: 'nav.recipes', emoji: '🍽️' },
  { to: '/frigo', label: 'nav.fridge', emoji: '🧊', title: 'nav.fridgeTitle' },
  { to: '/carnets', label: 'nav.collections', emoji: '📚' },
  { to: '/planning', label: 'nav.planning', emoji: '📅' },
  { to: '/courses', label: 'nav.shopping', emoji: '🛒' },
  { to: '/partager', label: 'nav.share', emoji: '👥', title: 'nav.shareTitle' },
  { to: '/succes', label: 'nav.achievements', emoji: '🏆' },
]

// Menu du bouton de compte : passkeys et déconnexion.
function MenuCompte() {
  const { user, deconnexion, t } = useAuth()
  const [ouvert, setOuvert] = useState(false)
  const [passkeys, setPasskeys] = useState(null)
  const [nom, setNom] = useState('')
  const [erreur, setErreur] = useState(null)
  const [envoi, setEnvoi] = useState(false)
  const zone = useRef(null)

  useEffect(() => {
    if (!ouvert) return
    setErreur(null)
    rafraichir()
    function fermer(e) { if (!zone.current?.contains(e.target)) setOuvert(false) }
    document.addEventListener('mousedown', fermer)
    return () => document.removeEventListener('mousedown', fermer)
  }, [ouvert])

  function rafraichir() {
    return listPasskeys().then(setPasskeys).catch(() => setErreur(t('passkeys.loadFailed')))
  }

  async function ajouter() {
    setErreur(null)
    setEnvoi(true)
    try {
      const { options, challenge_id } = await startPasskeyRegistration()
      let credential
      try {
        credential = await startRegistration({ optionsJSON: options })
      } catch (err) {
        setErreur(
          err?.code === 'ERROR_AUTHENTICATOR_PREVIOUSLY_REGISTERED' ? t('passkeys.alreadyRegistered')
            : err?.name === 'NotAllowedError' ? t('passkeys.cancelled')
              : t('passkeys.unsupported'),
        )
        return
      }
      await finishPasskeyRegistration({ challenge_id, credential, label: nom.trim() || null })
      setNom('')
      await rafraichir()
    } catch (err) {
      setErreur(err?.response?.status === 409 ? t('passkeys.alreadyRegistered') : t('passkeys.addFailed'))
    } finally {
      setEnvoi(false)
    }
  }

  async function supprimer(id) {
    setErreur(null)
    try {
      await deletePasskey(id)
      await rafraichir()
    } catch {
      setErreur(t('passkeys.deleteFailed'))
    }
  }

  return (
    <div ref={zone} className="relative flex-shrink-0">
      <button
        onClick={() => setOuvert(o => !o)}
        title={t('nav.loggedInAs', { name: user?.display_name || '' })}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium text-sm hover:text-orange-600 hover:bg-orange-50 ${
          ouvert ? 'bg-orange-50 text-orange-600' : 'text-gray-500'
        }`}
      >
        <span>👤</span>
        <span className="hidden lg:block">{user?.display_name}</span>
      </button>
      {ouvert && (
        <div className="absolute right-0 mt-2 w-72 max-w-[calc(100vw-2rem)] bg-white rounded-xl border border-gray-100 shadow-lg p-4 z-50 text-sm">
          <p className="font-medium text-gray-800 truncate">{user?.display_name}</p>
          <p className="text-xs text-gray-400 truncate mb-3">{user?.email}</p>

          <p className="font-medium text-gray-700 mb-1">{t('passkeys.title')}</p>
          <p className="text-xs text-gray-400 mb-2">{t('passkeys.hint')}</p>
          {passkeys === null ? (
            <p className="text-xs text-gray-400">{t('common.loading')}</p>
          ) : passkeys.length === 0 ? (
            <p className="text-xs text-gray-400">{t('passkeys.none')}</p>
          ) : (
            <ul className="space-y-1 mb-2">
              {passkeys.map(p => (
                <li key={p.id} className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-gray-700">{p.device_label || t('passkeys.unnamed')}</p>
                    <p className="text-xs text-gray-400">
                      {t('passkeys.addedOn', { date: new Date(p.created_at).toLocaleDateString(t('common.locale')) })}
                    </p>
                  </div>
                  <button
                    onClick={() => supprimer(p.id)}
                    title={t('passkeys.remove')}
                    className="text-xs text-red-500 hover:underline flex-shrink-0"
                  >
                    {t('common.delete')}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {browserSupportsWebAuthn() ? (
            <div className="flex gap-2 mt-2">
              <input
                value={nom} onChange={e => setNom(e.target.value)} maxLength={100}
                placeholder={t('passkeys.labelPlaceholder')}
                className="min-w-0 flex-1 px-2 py-1 border border-gray-200 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-orange-300"
              />
              <button
                onClick={ajouter} disabled={envoi}
                className="px-2 py-1 rounded-lg bg-orange-100 text-orange-700 text-xs font-medium hover:bg-orange-200 disabled:opacity-50 flex-shrink-0"
              >
                {envoi ? t('passkeys.adding') : t('passkeys.add')}
              </button>
            </div>
          ) : (
            <p className="text-xs text-gray-400 mt-2">{t('passkeys.unsupported')}</p>
          )}
          {erreur && <p className="text-xs text-red-600 bg-red-50 rounded-lg px-2 py-1 mt-2">{erreur}</p>}

          <button
            onClick={deconnexion}
            className="mt-4 w-full py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50"
          >
            {t('passkeys.logout')}
          </button>
        </div>
      )}
    </div>
  )
}

export default function Navigation() {
  const { pathname } = useLocation()
  const { user, t, lang, changerLangue } = useAuth()
  return (
    <nav className="bg-white shadow-sm border-b border-orange-100 sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between gap-2 sm:gap-4">
        <Link to="/" className="flex items-center gap-2 text-lg font-bold text-orange-600 flex-shrink-0">
          <span>🥘</span>
          <span className="hidden sm:block">Popote</span>
        </Link>
        <div className="flex items-center gap-0.5 sm:gap-1 overflow-x-auto scrollbar-hide min-w-0">
          {NAV.map(({ to, label, emoji, title }) => (
            <Link
              key={to}
              to={to}
              title={t(title || label)}
              className={`flex items-center gap-1.5 px-2 lg:px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                (to === '/' ? pathname === '/' : pathname.startsWith(to))
                  ? 'bg-orange-100 text-orange-700'
                  : 'text-gray-600 hover:text-orange-600 hover:bg-orange-50'
              }`}
            >
              <span>{emoji}</span>
              <span className="hidden lg:block">{t(label)}</span>
            </Link>
          ))}
        </div>
        {user?.is_admin && (
          <Link
            to="/comptes"
            title={t('nav.accountsTitle')}
            className={`flex items-center gap-1.5 px-2 lg:px-3 py-1.5 rounded-lg font-medium text-sm flex-shrink-0 ${
              pathname === '/comptes'
                ? 'bg-orange-100 text-orange-700'
                : 'text-gray-600 hover:text-orange-600 hover:bg-orange-50'
            }`}
          >
            <span>🔑</span>
            <span className="hidden lg:block">{t('nav.accounts')}</span>
          </Link>
        )}
        <Link
          to="/sauvegarde"
          title={t('nav.backupTitle')}
          className={`flex items-center px-2 py-1.5 rounded-lg text-sm flex-shrink-0 ${
            pathname === '/sauvegarde' ? 'bg-orange-100 text-orange-700' : 'text-gray-500 hover:text-orange-600 hover:bg-orange-50'
          }`}
        >
          💾
        </Link>
        <MenuCompte />
        <button
          onClick={() => changerLangue(lang === 'en' ? 'fr' : 'en').catch(() => {})}
          title={t('nav.switchLanguage')}
          className="flex items-center gap-1 px-2 py-1.5 rounded-lg font-medium text-sm text-gray-500 hover:text-orange-600 hover:bg-orange-50 flex-shrink-0"
        >
          <span>🌐</span>
          <span>{lang === 'en' ? 'FR' : 'EN'}</span>
        </button>
        <Link
          to="/ajouter"
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium text-sm transition-colors flex-shrink-0 ${
            pathname === '/ajouter'
              ? 'bg-orange-600 text-white'
              : 'bg-orange-100 text-orange-700 hover:bg-orange-200'
          }`}
        >
          <span>+</span>
          <span className="hidden sm:inline">{t('nav.add')}</span>
        </Link>
      </div>
    </nav>
  )
}
