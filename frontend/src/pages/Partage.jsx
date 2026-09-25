import { useEffect, useState } from 'react'
import { Link, Route, Routes, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  checkPublicShoppingItem, getPublicCollection, getPublicCollectionRecipe,
  getPublicRecipe, getPublicShopping,
} from '../api'
import VueRecette from '../components/VueRecette'
import { ListeParRayon } from './ListeCourses'

// Pages ouvertes par un lien partagé : aucune connexion requise, rien
// d'autre que la ressource partagée n'est visible.
export default function Partage() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white shadow-sm border-b border-orange-100">
        <div className="max-w-4xl mx-auto px-4 h-14 flex items-center gap-2 text-lg font-bold text-orange-600">
          <span>🍳</span><span>Popote</span>
        </div>
      </header>
      <main className="flex-1 max-w-4xl mx-auto w-full px-4 py-8">
        <Routes>
          <Route path="r/:token" element={<RecettePartagee />} />
          <Route path="c/:token" element={<CarnetPartage />} />
          <Route path="c/:token/:recipeId" element={<RecetteDeCarnet />} />
          <Route path="courses/:token" element={<CoursesPartagees />} />
          <Route path="*" element={<Invalide />} />
        </Routes>
      </main>
    </div>
  )
}

function Invalide() {
  return (
    <div className="text-center py-24 text-gray-400">
      <div className="text-6xl mb-4">🔒</div>
      <p className="text-xl font-medium text-gray-500">Lien invalide ou révoqué</p>
    </div>
  )
}

function Chargement() {
  return <div className="animate-pulse text-gray-400 py-12 text-center">Chargement…</div>
}

function RecettePartagee() {
  const { token } = useParams()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['public-recipe', token], queryFn: () => getPublicRecipe(token), retry: false,
  })
  if (isLoading) return <Chargement />
  if (isError) return <Invalide />
  return <VueRecette recipe={data} />
}

function CarnetPartage() {
  const { token } = useParams()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['public-collection', token], queryFn: () => getPublicCollection(token), retry: false,
  })
  if (isLoading) return <Chargement />
  if (isError) return <Invalide />
  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900">{data.emoji} {data.name}</h1>
      <p className="text-gray-400 text-sm mt-1">Carnet de {data.owner_name} · {data.recipes.length} recette{data.recipes.length !== 1 ? 's' : ''}</p>
      {data.description && <p className="text-gray-600 mt-3">{data.description}</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mt-6">
        {data.recipes.map(r => (
          <Link key={r.id} to={`/partage/c/${token}/${r.id}`}
            className="group bg-white rounded-2xl shadow-sm hover:shadow-md overflow-hidden">
            <div className="aspect-video bg-orange-50 flex items-center justify-center text-5xl overflow-hidden">
              {r.thumbnail_url ? <img src={r.thumbnail_url} alt="" className="w-full h-full object-cover" /> : '🍽️'}
            </div>
            <p className="p-4 font-semibold text-gray-900 group-hover:text-orange-600">{r.title}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}

function RecetteDeCarnet() {
  const { token, recipeId } = useParams()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['public-collection-recipe', token, recipeId],
    queryFn: () => getPublicCollectionRecipe(token, recipeId), retry: false,
  })
  if (isLoading) return <Chargement />
  if (isError) return <Invalide />
  return (
    <div>
      <Link to={`/partage/c/${token}`} className="text-sm text-orange-600 hover:underline mb-4 inline-block">← Retour au carnet</Link>
      <VueRecette recipe={data} />
    </div>
  )
}

function CoursesPartagees() {
  const { token } = useParams()
  const qc = useQueryClient()
  const key = ['public-shopping', token]
  // Rafraîchie toutes les 5 s : ce que coche quelqu'un d'autre en magasin
  // apparaît sans recharger la page.
  const { data, isLoading, isError } = useQuery({
    queryKey: key, queryFn: () => getPublicShopping(token), retry: false, refetchInterval: 5000,
  })
  const [erreur, setErreur] = useState(null)
  useEffect(() => { if (erreur) { const t = setTimeout(() => setErreur(null), 3000); return () => clearTimeout(t) } }, [erreur])

  if (isLoading) return <Chargement />
  if (isError) return <Invalide />

  const toggle = async (item) => {
    qc.setQueryData(key, prev => ({
      ...prev, items: prev.items.map(i => i.id === item.id ? { ...i, checked: !i.checked } : i),
    }))
    try {
      await checkPublicShoppingItem(token, item.id, !item.checked)
    } catch {
      setErreur('Modification non enregistrée')
      qc.invalidateQueries({ queryKey: key })
    }
  }
  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900">🛒 Courses de {data.owner_name}</h1>
      <p className="text-sm text-gray-400 mb-6">Cochez au fur et à mesure : la liste se met à jour chez tout le monde.</p>
      {erreur && <p className="mb-3 text-sm text-red-600">{erreur}</p>}
      <ListeParRayon items={data.items} aisles={data.aisles} onToggle={toggle} />
    </div>
  )
}
