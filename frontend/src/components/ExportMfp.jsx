import { useState, useEffect } from 'react'
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
// Les deux exportent la version affichée : quantités × [scale], et le
// nombre de portions choisi (une fournée ×2 peut être coupée en 4 parts).
export default function ExportMfp({ recipe, scale = 1, scaleQty = (q) => q, portions: shownPortions, onShare, busy }) {
  const [portions, setPortions] = useState(shownPortions ?? '')
  useEffect(() => { setPortions(shownPortions ?? '') }, [shownPortions])
  const nbPortions = Number.parseInt(portions, 10) > 0 ? Number.parseInt(portions, 10) : null
  const scaled = (recipe.ingredients || []).map((ing) => ({ ...ing, quantity: scaleQty(ing.quantity, scale) }))
  const lignes = scaled.map(ingredientLine).filter(Boolean).join('\n')
  const lien = recipe.share_token
    ? importPageLink(recipe.share_token, {
        scale,
        // Seulement si l'export diffère de la recette enregistrée.
        portions: scale !== 1 || (nbPortions && nbPortions !== recipe.servings) ? nbPortions : null,
      })
    : null
  return (
    <div className="space-y-4 text-sm">
      {(scale !== 1 || recipe.servings) && (
        <div className="p-3 rounded-lg bg-orange-50 text-orange-900 space-y-2">
          {scale !== 1 && (
            <p>Version exportée : quantités <strong>×{String(Math.round(scale * 100) / 100).replace('.', ',')}</strong>, comme affiché sur la fiche.</p>
          )}
          <label className="flex items-center gap-2">
            <span>Portions :</span>
            <input type="number" min="1" max="10000" value={portions} onChange={(e) => setPortions(e.target.value)}
              className="w-20 px-2 py-1 rounded border border-orange-200 bg-white" />
            <span className="text-xs text-orange-700">à changer si vous coupez la fournée autrement</span>
          </label>
        </div>
      )}
      <div>
        <p className="font-medium text-gray-800 mb-1">1. Importer depuis le web (le plus simple)</p>
        <p className="text-gray-500 mb-2">
          Dans MyFitnessPal : <em>Recettes, repas et aliments → Recettes → Créer une recette → Importer depuis le Web</em>, puis collez ce lien.
          Il faut que votre serveur Popote soit accessible depuis Internet.
        </p>
        {lien ? (
          <div className="flex gap-2">
            <input readOnly value={lien} onFocus={e => e.target.select()}
              className="flex-1 min-w-0 px-3 py-2 rounded-lg border border-gray-200 bg-gray-50 text-gray-600" />
            <Copier texte={lien} label="Copier le lien" />
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
          {nbPortions ? ` et indiquez ${nbPortions} portion${nbPortions > 1 ? 's' : ''}` : ''}.
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
