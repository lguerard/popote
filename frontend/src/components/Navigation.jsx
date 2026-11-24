import { Link, useLocation } from 'react-router-dom'
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

export default function Navigation() {
  const { pathname } = useLocation()
  const { user, deconnexion, t, lang, changerLangue } = useAuth()
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
        <button
          onClick={deconnexion}
          title={t('nav.loggedInAs', { name: user?.display_name || '' })}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium text-sm text-gray-500 hover:text-orange-600 hover:bg-orange-50 flex-shrink-0"
        >
          <span>👤</span>
          <span className="hidden lg:block">{user?.display_name}</span>
        </button>
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
