interface Props {
  notices: readonly string[]
  onDismiss: () => void
}

export default function Notices({ notices, onDismiss }: Props) {
  if (notices.length === 0) return null
  return (
    <div className="notices" aria-live="polite">
      <ul>
        {notices.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
      <button type="button" onClick={onDismiss} aria-label="Dismiss notices">
        ✕
      </button>
    </div>
  )
}
