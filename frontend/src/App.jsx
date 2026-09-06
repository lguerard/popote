import { Routes, Route, Link } from 'react-router-dom'
import Accueil from './pages/Accueil'
import DetailRecette from './pages/DetailRecette'
import AjouterRecette from './pages/AjouterRecette'
import ModifierRecette from './pages/ModifierRecette'
import ModeCuisine from './pages/ModeCuisine'
import ListeCourses from './pages/ListeCourses'
import Planning from './pages/Planning'
import Succes from './pages/Succes'
import Compte from './pages/Compte'
import Connexion from './pages/Connexion'
import Reinitialiser from './pages/Reinitialiser'
import Navigation from './components/Navigation'
import { useAuth } from './auth/AuthContext'

export default function App() {
  return (
    <Routes>
      {/* Seule page accessible sans compte : le lien de réinitialisation. */}
      <Route path="/reinitialiser/:token" element={<Reinitialiser />} />
      <Route path="*" element={<AppProtegee />} />
    </Routes>
  )
}

/** Tout le reste de l'application exige une session. */
function AppProtegee() {
  const { user, loading, unreachable } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-400">
        <div className="text-center">
          <div className="text-4xl mb-2">🍳</div>
          <p>Chargement…</p>
        </div>
      </div>
    )
  }

  if (unreachable) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="text-center text-gray-500">
          <div className="text-5xl mb-3">🔌</div>
          <p className="font-medium text-gray-700">Serveur injoignable</p>
          <p className="text-sm mt-1">
            Le backend Popote ne répond pas. Réessaie dans un instant.
          </p>
        </div>
      </div>
    )
  }

  if (!user) return <Connexion />

  return (
    <div className="min-h-screen flex flex-col">
      <Navigation />
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-8">
        <Routes>
          <Route path="/" element={<Accueil />} />
          <Route path="/recettes/:id" element={<DetailRecette />} />
          <Route path="/recettes/:id/modifier" element={<ModifierRecette />} />
          <Route path="/courses" element={<ListeCourses />} />
          <Route path="/planning" element={<Planning />} />
          <Route path="/ajouter" element={<AjouterRecette />} />
          <Route path="/succes" element={<Succes />} />
          <Route path="/compte" element={<Compte />} />
          <Route path="*" element={<IntrouvablePage />} />
        </Routes>
      </main>
      <Routes>
        <Route path="/recettes/:id/cuisine" element={<ModeCuisine />} />
      </Routes>
    </div>
  )
}

function IntrouvablePage() {
  return (
    <div className="text-center py-24 text-gray-400">
      <div className="text-6xl mb-4">🍽️</div>
      <p className="text-xl font-medium text-gray-500">Page introuvable</p>
      <Link to="/" className="mt-4 inline-block text-orange-600 hover:underline">← Retour aux recettes</Link>
    </div>
  )
}
