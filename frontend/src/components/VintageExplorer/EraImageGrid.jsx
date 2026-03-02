import { useState, useEffect } from 'react'
import api from '../../services/api'

function SkeletonGrid() {
  return (
    <div className="era-images-loading">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="skeleton-box era-image-skeleton" />
      ))}
    </div>
  )
}

const SOURCE_LABELS = {
  pinterest: 'Pinterest',
  wikimedia: 'Wikimedia',
}

const SOURCE_COLORS = {
  pinterest: { bg: 'rgba(230, 0, 35, 0.85)', color: '#fff' },
  wikimedia: { bg: 'rgba(36, 110, 185, 0.85)', color: '#fff' },
}

function SourceBadge({ source }) {
  if (!source) return null
  const label = SOURCE_LABELS[source] ?? source
  const style = SOURCE_COLORS[source] ?? { bg: 'rgba(0,0,0,0.6)', color: '#fff' }
  return (
    <span className="era-image-source-badge" style={{ background: style.bg, color: style.color }}>
      {label}
    </span>
  )
}

export default function EraImageGrid({ eraId }) {
  const [images, setImages] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!eraId) return
    setImages([])
    setLoading(true)
    api.get(`/vintage/eras/${encodeURIComponent(eraId)}/images`)
      .then(res => setImages(res.data.images || []))
      .catch(() => setImages([]))
      .finally(() => setLoading(false))
  }, [eraId])

  if (!eraId) return null

  return (
    <div className="era-image-grid-section">
      <div className="era-image-grid-title">Photos</div>

      {loading ? (
        <SkeletonGrid />
      ) : images.length === 0 ? (
        <p className="era-images-empty">No photos available yet.</p>
      ) : (
        <div className="era-image-grid">
          {images.slice(0, 6).map((img, i) => (
            <div key={i} className="era-image-item">
              {img.item_url ? (
                <a
                  href={img.item_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="era-image-link"
                >
                  <img src={img.image_url} alt={img.title || ''} loading="lazy" />
                </a>
              ) : (
                <img src={img.image_url} alt={img.title || ''} loading="lazy" />
              )}
              <SourceBadge source={img.source} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
