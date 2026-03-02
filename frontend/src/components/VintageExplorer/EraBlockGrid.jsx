import { useState, useEffect } from 'react'
import api from '../../services/api'

export const ERA_BLOCKS = [
  {
    id: 'historical',
    label: 'Historical',
    range: '1700–1899',
    description: 'Baroque grandeur through Victorian opulence — court fashion, structured silhouettes, and elaborate ornamentation spanning two centuries.',
    ids: ['1700-1749', '1750-1799', '1800-1824', '1825-1849', '1850-1874', '1875-1899'],
    previewIds: ['1750-1799', '1825-1849', '1850-1874', '1875-1899'],
  },
  {
    id: 'early-modern',
    label: 'Early Modern',
    range: '1900–1959',
    description: 'Edwardian elegance to the New Look — defining the silhouette of the 20th century through wartime, jazz, and postwar optimism.',
    ids: ['1900s', '1910s', '1920s', '1930s', '1940s', '1950s'],
    previewIds: ['1920s', '1930s', '1940s', '1950s'],
  },
  {
    id: 'contemporary-vintage',
    label: 'Contemporary Vintage',
    range: '1960–2009',
    description: 'Swinging Sixties through Streetwear — counterculture, disco, power dressing, grunge, and the rise of the digital age.',
    ids: [
      'early-1960s', 'late-1960s', 'early-1970s', 'late-1970s',
      'early-1980s', 'late-1980s', 'early-1990s', 'late-1990s',
      'early-2000s', 'late-2000s',
    ],
    previewIds: ['early-1960s', 'early-1970s', 'early-1980s', 'early-1990s'],
  },
]

function BlockCard({ block, eras, onSelect }) {
  const [images, setImages] = useState({})

  useEffect(() => {
    block.previewIds.forEach(id => {
      api.get(`/vintage/eras/${encodeURIComponent(id)}/images`)
        .then(res => {
          const first = res.data.images?.[0]
          if (first?.image_url) {
            setImages(prev => ({ ...prev, [id]: first.image_url }))
          }
        })
        .catch(() => {})
    })
  }, [])

  const eraMap = Object.fromEntries(eras.map(e => [e.id, e]))

  return (
    <button className="era-block-card" onClick={() => onSelect(block)}>
      <div className="era-block-card__images">
        {block.previewIds.map(id => (
          <div key={id} className="era-block-card__image-cell">
            {images[id] ? (
              <img src={images[id]} alt="" loading="lazy" />
            ) : (
              <div className="era-block-card__image-placeholder" />
            )}
            <span className="era-block-card__image-label">
              {eraMap[id]?.period || id}
            </span>
          </div>
        ))}
      </div>
      <div className="era-block-card__footer">
        <div className="era-block-card__title">{block.label}</div>
        <div className="era-block-card__range">{block.range}</div>
        <p className="era-block-card__desc">{block.description}</p>
        <span className="era-block-card__cta">Explore →</span>
      </div>
    </button>
  )
}

export default function EraBlockGrid({ eras, onSelectBlock }) {
  return (
    <div className="era-block-grid">
      {ERA_BLOCKS.map(block => (
        <BlockCard
          key={block.id}
          block={block}
          eras={eras}
          onSelect={onSelectBlock}
        />
      ))}
    </div>
  )
}
