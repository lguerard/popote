// Contenu d'une recette tel qu'il s'AFFICHE pour le compte connecté : la
// traduction mise en cache par le serveur (recipe.translation, comptes en
// anglais) quand il y en a une, sinon l'original.
//
// Pour l'affichage seulement. Le formulaire d'édition (ModifierRecette) et
// tout ce qui est renvoyé au serveur doivent lire recipe.title,
// recipe.ingredients… tels quels : y mettre la traduction remplacerait la
// recette d'origine par sa traduction au premier enregistrement.
// Les pages publiques (/partage/) n'ont pas de compte, donc pas de
// traduction : elles n'utilisent pas ce module.
export function contenuAffiche(recipe) {
  const traduction = recipe?.translation
  if (!traduction) return recipe
  return {
    ...recipe,
    title: traduction.title ?? recipe.title,
    description: traduction.description ?? recipe.description,
    ingredients: traduction.ingredients ?? recipe.ingredients,
    steps: traduction.steps ?? recipe.steps,
    tags: traduction.tags ?? recipe.tags,
  }
}

// Fiche ouverte pendant que le serveur traduit en arrière-plan : on la
// relit jusqu'à ce que la traduction arrive (voir translation_pending).
export const DELAI_RELECTURE_TRADUCTION = 3000
