// Map of common vintage color names → approximate CSS colors
const COLOR_MAP = {
  'black': '#111',
  'white': '#f5f5f5',
  'ivory': '#fffff0',
  'cream': '#fffdd0',
  'ecru': '#c2b280',
  'beige': '#c8b89a',
  'camel': '#c19a6b',
  'tan': '#d2b48c',
  'brown': '#795548',
  'khaki': '#c3b091',
  'grey': '#9e9e9e',
  'gray': '#9e9e9e',
  'slate': '#78909c',
  'charcoal': '#455a64',
  'navy': '#1a237e',
  'navy blue': '#1a237e',
  'royal blue': '#1565c0',
  'cobalt blue': '#1976d2',
  'cobalt': '#1976d2',
  'sky blue': '#4fc3f7',
  'powder blue': '#b3e5fc',
  'baby blue': '#b3e5fc',
  'electric blue': '#0d47a1',
  'cornflower blue': '#5c85d6',
  'blue': '#1e88e5',
  'teal': '#00897b',
  'peacock teal': '#00796b',
  'peacock blue': '#0077b6',
  'turquoise': '#26c6da',
  'aqua': '#00bcd4',
  'cyan': '#00bcd4',
  'mint': '#a5d6a7',
  'mint green': '#a5d6a7',
  'sage': '#bcaaa4',
  'sage green': '#8d9c6e',
  'forest green': '#2e7d32',
  'hunter green': '#2e7d32',
  'bottle green': '#1b5e20',
  'olive': '#827717',
  'olive green': '#827717',
  'olive drab': '#558b2f',
  'avocado green': '#76885b',
  'green': '#388e3c',
  'red': '#c62828',
  'crimson': '#b71c1c',
  'deep crimson': '#b71c1c',
  'burgundy': '#880e4f',
  'deep burgundy': '#880e4f',
  'wine': '#880e4f',
  'bordeaux': '#6d1117',
  'warm red': '#e53935',
  'power red': '#d32f2f',
  'hot pink': '#e91e63',
  'neon pink': '#ff1493',
  'fuchsia': '#ec407a',
  'pink': '#f48fb1',
  'baby pink': '#f8bbd0',
  'poodle pink': '#f48fb1',
  'millennial pink': '#f4c2c2',
  'coral': '#ff7043',
  'apricot': '#ffb380',
  'peach': '#ffccbc',
  'salmon': '#ef9a9a',
  'orange': '#ef6c00',
  'bright orange': '#ff6d00',
  'burnt orange': '#bf360c',
  'tangerine': '#f57c00',
  'rust': '#bf360c',
  'terracotta': '#bf5b36',
  'amber': '#ffa000',
  'golden amber': '#ffa000',
  'gold': '#f9a825',
  'champagne gold': '#c5a028',
  'harvest gold': '#da9100',
  'mustard': '#f57f17',
  'mustard gold': '#f57f17',
  'saffron': '#f4b400',
  'yellow': '#f9a825',
  'canary yellow': '#ffee58',
  'lemon yellow': '#ffee58',
  'pale yellow': '#fff9c4',
  'lavender': '#9575cd',
  'lilac': '#ab47bc',
  'violet': '#7b1fa2',
  'purple': '#6a1b9a',
  'electric purple': '#7b1fa2',
  'mauve': '#ce93d8',
  'dusty mauve': '#ba68c8',
  'mauveine': '#9c27b0',
  'magenta': '#e91e63',
  'hot orange': '#ff6d00',
  'silver': '#bdbdbd',
  'metallic silver': '#9e9e9e',
  'gold lamé': '#ffd700',
  'metallic': '#bdbdbd',
  'metallic lamé': '#d4af37',
  'champagne': '#f7e7ce',
  'flesh': '#ffd5b5',
  'tricolor': '#0055a4',
  'neon': '#ccff00',
  'neon yellow': '#ccff00',
  'electric': '#0d47a1',
  'fluorescent': '#ccff00',
  'acid wash blue': '#4a90d9',
  'psychedelic multi-color': '#9c27b0',
  'earth tones': '#795548',
  'warm ivory': '#fffff0',
  'pale ivory': '#fffff0',
  'soft gold': '#d4af37',
  'empire green': '#2e7d32',
  'cerulean blue': '#039be5',
  'dusty rose': '#d4a0a0',
  'pale pink': '#fce4ec',
}

function getColorSwatch(colorName) {
  const key = colorName.toLowerCase().trim()
  // Direct match
  if (COLOR_MAP[key]) return COLOR_MAP[key]
  // Partial match: check if any map key is contained in the name
  for (const [mapKey, hex] of Object.entries(COLOR_MAP)) {
    if (key.includes(mapKey) || mapKey.includes(key)) return hex
  }
  return null
}

function TopGarments({ garments, garmentPrices = {} }) {
  if (!garments?.length) return null
  return (
    <div className="era-section era-section--garments">
      <div className="era-section-label">Top Garments to Source</div>
      <div className="era-garment-list">
        {garments.map((g, i) => {
          const price = garmentPrices[g]
          return (
            <div key={i} className="era-garment-item">
              <span className="era-garment-rank">#{i + 1}</span>
              <span className="era-garment-name">{g}</span>
              {price != null
                ? <span className="era-garment-price">${price.toFixed(2)}</span>
                : <span className="era-garment-price era-garment-price--na">—</span>
              }
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Section({ label, items, showColors = false }) {
  if (!items || items.length === 0) return null
  return (
    <div className="era-section">
      <div className="era-section-label">{label}</div>
      <div className="era-chips">
        {items.map((item, i) => {
          const swatch = showColors ? getColorSwatch(item) : null
          return (
            <span key={i} className={`era-chip${showColors ? ' color-chip' : ''}`}>
              {swatch && (
                <span
                  className="color-swatch"
                  style={{ background: swatch }}
                />
              )}
              {item}
            </span>
          )
        })}
      </div>
    </div>
  )
}

export default function EraTrends({ era, marketData }) {
  if (!era) return null

  return (
    <div className="era-trends">
      <div>
        <h2 className="era-trends-title">{era.label}</h2>
        <p className="era-trends-period">{era.period}</p>
      </div>

      {era.summary && (
        <div className="era-summary">{era.summary}</div>
      )}

      <div className="era-sections">
        <Section label="Colors" items={era.colors} showColors />
        <Section label="Fabrics" items={era.fabrics} />
        <Section label="Prints & Patterns" items={era.prints} />
        <Section label="Silhouettes" items={era.silhouettes} />
        <Section label="Aesthetics" items={era.aesthetics} />
        <Section label="Brands" items={era.brands} />
        <TopGarments garments={era.key_garments} garmentPrices={marketData?.garment_prices} />
      </div>
    </div>
  )
}
