import { useState } from 'react'
import { importPageLink } from '../api'

export const ingredientLine = (ing) => {
  const main = [ing.quantity, ing.unit, ing.name].filter(Boolean).join(' ')
  return main && ing.notes ? `${main}, ${ing.notes}` : main
}

function Copier({ texte, label }) {
  const [copie, setCopie] = useState(false)
  const copier = async () => {
    try {
      await navigator.clipboard.writeText(texte)
      setCopie(true)
      setTimeout(() => setCopie(false), 2000)
    } catch { /* presse-papiers indisponible : le texte reste sélectionnable */ }
  }
  return (
    <button onClick={copier} className="px-3 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 flex-shrink-0">
      {copie ? '✓ Copié' : label}
    </button>
  )
}

// MyFitnessPal n'a pas d'API : on lui donne soit un lien qu'il sait importer
// (page avec données schema.org), soit la liste d'ingrédients à coller.
export default function ExportMfp({ recipe, onShare, busy }) {
  const lignes = (recipe.ingredients || []).map(ingredientLine).filter(Boolean).join('\n')
  return (
    <div className="space-y-4 text-sm">
      <div>
        <p className="font-medium text-gray-800 mb-1">1. Importer depuis le web (le plus simple)</p>
        <p className="text-gray-500 mb-2">
          Dans MyFitnessPal : <em>Recettes, repas et aliments → Recettes → Créer une recette → Importer depuis le Web</em>, puis collez ce lien.
          Il faut que votre serveur Popote soit accessible depuis Internet.
        </p>
        {recipe.share_token ? (
          <div className="flex gap-2">
            <input readOnly value={importPageLink(recipe.share_token)} onFocus={e => e.target.select()}
              className="flex-1 min-w-0 px-3 py-2 rounded-lg border border-gray-200 bg-gray-50 text-gray-600" />
            <Copier texte={importPageLink(recipe.share_token)} label="Copier le lien" />
          </div>
        ) : (
          <button onClick={onShare} disabled={busy}
            className="px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg disabled:opacity-50">
            🔗 Créer le lien d'import
          </button>
        )}
      </div>
      <div>
        <p className="font-medium text-gray-800 mb-1">2. Ou saisir les ingrédients à la main</p>
        <p className="text-gray-500 mb-2">
          <em>Créer une recette → Saisir manuellement</em> : collez la liste (un ingrédient par ligne)
          {recipe.servings ? ` et indiquez ${recipe.servings} portions` : ''}.
        </p>
        <div className="flex gap-2 items-start">
          <textarea readOnly value={lignes} rows={Math.min(8, Math.max(3, recipe.ingredients?.length || 0))}
            onFocus={e => e.target.select()}
            className="flex-1 min-w-0 px-3 py-2 rounded-lg border border-gray-200 bg-gray-50 text-gray-600 resize-none" />
          <Copier texte={lignes} label="Copier" />
        </div>
      </div>
    </div>
  )
}
