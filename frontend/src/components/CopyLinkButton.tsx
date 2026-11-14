import { useState } from 'react'

export default function CopyLinkButton() {
  const [status, setStatus] = useState<string>('')

  const handleClick = () => {
    navigator.clipboard.writeText(window.location.href).then(
      () => setStatus('Link copied'),
      () => setStatus('Copy failed: copy the address bar instead'),
    )
  }

  return (
    <>
      <button type="button" onClick={handleClick}>
        Copy link
      </button>
      <span className="muted" aria-live="polite">
        {status}
      </span>
    </>
  )
}
