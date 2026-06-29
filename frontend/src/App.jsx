import { Routes, Route } from 'react-router-dom'
import Accueil from './pages/Accueil'
import DetailRecette from './pages/DetailRecette'
import AjouterRecette from './pages/AjouterRecette'
import ModifierRecette from './pages/ModifierRecette'
import ModeCuisine from './pages/ModeCuisine'
import ListeCourses from './pages/ListeCourses'
import Planning from './pages/Planning'
import Succes from './pages/Succes'
import Navigation from './components/Navigation'

export default function App() {
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
        </Routes>
      </main>
      <Routes>
        <Route path="/recettes/:id/cuisine" element={<ModeCuisine />} />
      </Routes>
    </div>
  )
}
