import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const NAV = [
  { to: '/', label: 'Recettes', emoji: '🍽️' },
  { to: '/planning', label: 'Planning', emoji: '📅' },
  { to: '/courses', label: 'Courses', emoji: '🛒' },
  { to: '/succes', label: 'Succès', emoji: '🏆' },
]

export default function Navigation() {
  const { pathname } = useLocation()
  const { user, signOut } = useAuth()
  const [menuOuvert, setMenuOuvert] = useState(false)

  return (
    <nav className="bg-white shadow-sm border-b border-orange-100 sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
        <Link to="/" className="flex items-center gap-2 text-lg font-bold text-orange-600 flex-shrink-0">
          <span>🍳</span>
          <span className="hidden sm:block">Popote</span>
        </Link>
        <div className="flex items-center gap-1">
          {NAV.map(({ to, label, emoji }) => (
            <Link
              key={to}
              to={to}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                pathname === to
                  ? 'bg-orange-100 text-orange-700'
                  : 'text-gray-600 hover:text-orange-600 hover:bg-orange-50'
              }`}
            >
              <span>{emoji}</span>
              <span className="hidden sm:block">{label}</span>
            </Link>
          ))}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Link
            to="/ajouter"
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium text-sm transition-colors ${
              pathname === '/ajouter'
                ? 'bg-orange-600 text-white'
                : 'bg-orange-100 text-orange-700 hover:bg-orange-200'
            }`}
          >
            <span>+</span>
            <span>Ajouter</span>
          </Link>

          <div className="relative">
            <button
              type="button"
              onClick={() => setMenuOuvert((o) => !o)}
              aria-haspopup="menu"
              aria-expanded={menuOuvert}
              title={user?.display_name}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                pathname === '/compte'
                  ? 'bg-orange-100 text-orange-700'
                  : 'text-gray-600 hover:text-orange-600 hover:bg-orange-50'
              }`}
            >
              <span>👤</span>
              <span className="hidden md:block max-w-[8rem] truncate">{user?.display_name}</span>
            </button>

            {menuOuvert && (
              <>
                {/* Clic à côté : referme le menu. */}
                <div className="fixed inset-0 z-40" onClick={() => setMenuOuvert(false)} />
                <div className="absolute right-0 mt-1 w-48 bg-white rounded-lg shadow-lg border border-orange-100 py-1 z-50">
                  <Link
                    to="/compte"
                    onClick={() => setMenuOuvert(false)}
                    className="block px-4 py-2 text-sm text-gray-700 hover:bg-orange-50"
                  >
                    Mon compte
                  </Link>
                  <button
                    type="button"
                    onClick={() => { setMenuOuvert(false); signOut() }}
                    className="block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-orange-50"
                  >
                    Se déconnecter
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </nav>
  )
}
