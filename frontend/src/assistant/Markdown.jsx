import { Link } from 'react-router-dom'

// Markdown « sûr » des réponses de l'assistant : construit des éléments
// React, jamais de HTML brut (pas de dangerouslySetInnerHTML). Le texte est
// donc toujours échappé, et seuls deux types de liens passent : les fiches
// recettes de l'appli (/recettes/<id>) et les adresses http(s).
// Couvre ce que le modèle produit : paragraphes, titres, listes, gras,
// italique, code, liens. Une réponse incomplète (en cours de flux) s'affiche
// sans erreur : un ** pas encore refermé reste du texte.

const RECIPE_LINK = /^\/recettes\/[0-9a-f-]{36}$/i
const WEB_LINK = /^https?:\/\/[^\s]+$/i
const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\[[^\]\n]+\]\([^)\s]+\))|(\*[^*\s][^*\n]*\*)/

function inline(text, onRecipe, key = 'i') {
  const out = []
  let rest = text
  let n = 0
  while (rest) {
    const m = rest.match(INLINE)
    if (!m) { out.push(rest); break }
    if (m.index) out.push(rest.slice(0, m.index))
    const token = m[0]
    const k = `${key}-${n++}`
    if (m[1]) {
      out.push(<code key={k} className="px-1 py-0.5 rounded bg-orange-50 text-orange-800 text-[0.85em]">{token.slice(1, -1)}</code>)
    } else if (m[2]) {
      out.push(<strong key={k}>{inline(token.slice(2, -2), onRecipe, k)}</strong>)
    } else if (m[3]) {
      const [, label, href] = token.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/)
      if (RECIPE_LINK.test(href)) {
        out.push(
          <Link key={k} to={href} onClick={onRecipe}
            className="text-orange-700 font-medium underline decoration-orange-300 underline-offset-2 hover:text-orange-800">
            {label}
          </Link>
        )
      } else if (WEB_LINK.test(href)) {
        out.push(<a key={k} href={href} target="_blank" rel="noopener noreferrer nofollow" className="text-orange-700 underline">{label}</a>)
      } else {
        out.push(label)
      }
    } else if (m[4]) {
      out.push(<em key={k}>{inline(token.slice(1, -1), onRecipe, k)}</em>)
    }
    rest = rest.slice(m.index + token.length)
  }
  return out
}

function blocks(text) {
  const lines = text.replace(/\r\n?/g, '\n').split('\n')
  const out = []
  let para = []
  let list = null
  const flushPara = () => { if (para.length) out.push({ type: 'p', text: para.join('\n') }); para = [] }
  const flushList = () => { if (list) out.push(list); list = null }
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (/^\s*```/.test(line)) {
      flushPara(); flushList()
      const code = []
      while (++i < lines.length && !/^\s*```/.test(lines[i])) code.push(lines[i])
      out.push({ type: 'code', text: code.join('\n') })
      continue
    }
    const heading = line.match(/^\s*(#{1,4})\s+(.*)$/)
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/)
    const numbered = line.match(/^\s*(\d+)[.)]\s+(.*)$/)
    if (!line.trim()) { flushPara(); flushList(); continue }
    if (heading) { flushPara(); flushList(); out.push({ type: 'h', text: heading[2] }); continue }
    if (bullet || numbered) {
      flushPara()
      const type = bullet ? 'ul' : 'ol'
      if (!list || list.type !== type) { flushList(); list = { type, items: [], start: numbered ? Number(numbered[1]) : 1 } }
      list.items.push(bullet ? bullet[1] : numbered[2])
      continue
    }
    if (list && /^\s{2,}\S/.test(line)) { list.items[list.items.length - 1] += ` ${line.trim()}`; continue }
    flushList()
    para.push(line)
  }
  flushPara(); flushList()
  return out
}

export default function Markdown({ text, onRecipe }) {
  return (
    <div className="space-y-2 leading-relaxed break-words">
      {blocks(text || '').map((b, i) => {
        if (b.type === 'h') return <p key={i} className="font-semibold text-gray-900 pt-1">{inline(b.text, onRecipe, `h${i}`)}</p>
        if (b.type === 'code') return <pre key={i} className="p-2 rounded-lg bg-gray-50 text-xs overflow-x-auto whitespace-pre-wrap">{b.text}</pre>
        if (b.type === 'ul') {
          return (
            <ul key={i} className="list-disc pl-5 space-y-1">
              {b.items.map((it, j) => <li key={j}>{inline(it, onRecipe, `u${i}-${j}`)}</li>)}
            </ul>
          )
        }
        if (b.type === 'ol') {
          return (
            <ol key={i} start={b.start} className="list-decimal pl-5 space-y-1">
              {b.items.map((it, j) => <li key={j}>{inline(it, onRecipe, `o${i}-${j}`)}</li>)}
            </ol>
          )
        }
        return (
          <p key={i}>
            {b.text.split('\n').map((l, j) => (
              <span key={j}>{j > 0 && <br />}{inline(l, onRecipe, `p${i}-${j}`)}</span>
            ))}
          </p>
        )
      })}
    </div>
  )
}
