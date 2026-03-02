import { useState, useEffect } from 'react'
import api from '../../services/api'

function EraCard({ era, onSelect }) {
  const [imgUrl, setImgUrl] = useState(null)

  useEffect(() => {
    api.get(`/vintage/eras/${encodeURIComponent(era.id)}/images`)
      .then(res => {
        const first = res.data.images?.[0]
        if (first?.image_url) setImgUrl(first.image_url)
      })
      .catch(() => {})
  }, [era.id])

  return (
    <button className="era-era-card" onClick={() => onSelect(era)}>
      <div className="era-era-card__img">
        {imgUrl ? (
          <img src={imgUrl} alt={era.label} loading="lazy" />
        ) : (
          <div className="era-era-card__img-placeholder" />
        )}
      </div>
      <div className="era-era-card__body">
        <div className="era-era-card__label">{era.label}</div>
        <div className="era-era-card__period">{era.period}</div>
      </div>
    </button>
  )
}

export default function EraBlockEras({ block, eras, onBack, onSelectEra }) {
  const eraMap = Object.fromEntries(eras.map(e => [e.id, e]))
  const blockEras = block.ids.map(id => eraMap[id]).filter(Boolean)

  return (
    <div className="era-block-eras">
      <div className="era-block-eras__header">
        <button className="era-block-eras__back" onClick={onBack}>← All Eras</button>
        <div>
          <h2 className="era-block-eras__title">{block.label}</h2>
          <p className="era-block-eras__range">{block.range}</p>
        </div>
      </div>
      <div className="era-block-eras__grid">
        {blockEras.map(era => (
          <EraCard key={era.id} era={era} onSelect={onSelectEra} />
        ))}
      </div>
    </div>
  )
}
