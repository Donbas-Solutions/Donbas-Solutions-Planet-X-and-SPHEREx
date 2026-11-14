import { useId, useState, type ReactNode } from 'react'
import { GLOSSARY, type TermId } from '../lib/glossary'

interface Props {
  id: TermId
  children: ReactNode
}

/** A glossary term with a tooltip on hover, focus or tap; Escape hides it without moving the pointer (WCAG 1.4.13). */
export default function Term({ id, children }: Props) {
  const tipId = useId()
  const [isDismissed, setIsDismissed] = useState(false)
  return (
    <span
      className={isDismissed ? 'term is-dismissed' : 'term'}
      onMouseLeave={() => setIsDismissed(false)}
      onBlur={() => setIsDismissed(false)}
    >
      <button
        type="button"
        className="term-button"
        aria-describedby={tipId}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setIsDismissed(true)
        }}
      >
        {children}
      </button>
      <span role="tooltip" id={tipId} className="term-tip">
        {GLOSSARY[id].text}
      </span>
    </span>
  )
}
