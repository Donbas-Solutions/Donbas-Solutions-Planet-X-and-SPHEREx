export default function Landing() {
  const demo = `${import.meta.env.BASE_URL}?manifest=${encodeURIComponent(`${import.meta.env.BASE_URL}mock/sequence.json`)}`
  return (
    <section className="landing">
      <h2>Blink NASA SPHEREx images of any patch of sky</h2>
      <p>
        Enter a position or an object name, or pick one of the five test targets above. The images of that patch are
        shown in time order, so stars that move or change brightness stand out.
      </p>
      <p>
        Example: <a href={demo}>a synthetic demo sequence</a> with one moving star.
      </p>
    </section>
  )
}
