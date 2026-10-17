// Parties d'une recette (« Pâte », « Garniture ») : un intertitre devant le
// premier ingrédient ou la première étape de chaque partie.

/** Nom de la partie qui commence à l'élément i, sinon null. */
export const sectionStart = (items, i) => {
  const section = items[i]?.section
  return section && section !== items[i - 1]?.section ? section : null
}

export function SectionTitle({ children, className = '' }) {
  return (
    <li className={`list-none text-xs font-bold uppercase tracking-wide text-orange-700 ${className}`}>
      {children}
    </li>
  )
}
