import { useId, type ReactNode } from 'react'
import { GLOSSARY, type TermId } from '../lib/glossary'

interface Props {
  id: TermId
  children: ReactNode
}

/** A glossary term with a tooltip shown on hover and on keyboard focus. */
export default function Term({ id, children }: Props) {
  const tipId = useId()
  return (
    <span className="term">
      <button type="button" className="term-button" aria-describedby={tipId}>
        {children}
      </button>
      <span role="tooltip" id={tipId} className="term-tip">
        {GLOSSARY[id].text}
      </span>
    </span>
  )
}
