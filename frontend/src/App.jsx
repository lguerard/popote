import { Routes, Route, Link } from 'react-router-dom'
import Accueil from './pages/Accueil'
import DetailRecette from './pages/DetailRecette'
import AjouterRecette from './pages/AjouterRecette'
import ModifierRecette from './pages/ModifierRecette'
import ModeCuisine from './pages/ModeCuisine'
import ListeCourses from './pages/ListeCourses'
import Planning from './pages/Planning'
import Succes from './pages/Succes'
import Comptes from './pages/Comptes'
import Navigation from './components/Navigation'
import Connexion from './pages/Connexion'
import { useAuth } from './auth'

export default function App() {
  const { user, chargement } = useAuth()

  // Tant que /auth/me n'a pas repondu, on n'affiche ni l'application ni
  // l'ecran de connexion : sinon ce dernier clignote a chaque
  // rechargement de page alors que la session est valide.
  if (chargement) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-300 text-4xl">
        🍲
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
          {/* Route montee seulement pour un administrateur : sans ça,
              un non-admin verrait la page avant son erreur 403. */}
          {user.is_admin && <Route path="/comptes" element={<Comptes />} />}
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
