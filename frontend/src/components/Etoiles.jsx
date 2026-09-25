// Note de 1 à 5. Cliquer sur l'étoile déjà sélectionnée efface la note.
export default function Etoiles({ value, onChange, size = 'text-xl' }) {
  const lecture = !onChange
  return (
    <span className={`inline-flex ${size}`} aria-label={value ? `${value} sur 5` : 'Pas de note'}>
      {[1, 2, 3, 4, 5].map(n => (
        <button
          key={n}
          type="button"
          disabled={lecture}
          onClick={() => onChange?.(value === n ? null : n)}
          title={lecture ? undefined : `${n} étoile${n > 1 ? 's' : ''}`}
          className={`leading-none ${lecture ? 'cursor-default' : 'hover:scale-110 transition-transform'} ${
            value && n <= value ? 'text-amber-400' : 'text-gray-300'
          }`}
        >★</button>
      ))}
    </span>
  )
}
