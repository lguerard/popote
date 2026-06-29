import { Link, useLocation } from 'react-router-dom'

const NAV = [
  { to: '/', label: 'Recettes', emoji: '🍽️' },
  { to: '/planning', label: 'Planning', emoji: '📅' },
  { to: '/courses', label: 'Courses', emoji: '🛒' },
  { to: '/succes', label: 'Succès', emoji: '🏆' },
]

export default function Navigation() {
  const { pathname } = useLocation()
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
        <Link
          to="/ajouter"
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium text-sm transition-colors flex-shrink-0 ${
            pathname === '/ajouter'
              ? 'bg-orange-600 text-white'
              : 'bg-orange-100 text-orange-700 hover:bg-orange-200'
          }`}
        >
          <span>+</span>
          <span>Ajouter</span>
        </Link>
      </div>
    </nav>
  )
}
