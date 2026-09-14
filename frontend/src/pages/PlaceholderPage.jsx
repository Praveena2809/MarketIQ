export default function PlaceholderPage({ title, description }) {
  return (
    <div className="mx-auto max-w-4xl px-10 py-12">
      <h2 className="font-serif text-2xl text-ink">{title}</h2>
      <div className="mt-6 border border-dashed border-hairline px-6 py-10 text-center">
        <p className="text-[0.925rem] text-ink">Not built yet</p>
        <p className="mx-auto mt-1 max-w-sm text-[0.85rem] text-ink-soft">{description}</p>
      </div>
    </div>
  )
}
