import { useState, useEffect, useRef } from 'react'
import { useAuth } from '../hooks/useAuth'
import api from '../services/api'
import './HomePage.css'

export const TREND_SLIDES = [
  {
    label: 'Demand Scoring',
    content: (
      <div className="hp-slide">
        <div className="hp-slide-row">
          <span className="hp-mock-kw">vintage denim</span>
          <span className="hp-mock-badge hp-mock-badge--peak">Peak Demand</span>
        </div>
        <div className="hp-mock-scores">
          <div className="hp-mock-score"><span className="hp-mock-score-lbl">Score</span><span className="hp-mock-score-val" style={{color:'#66bb6a'}}>+24.3</span></div>
          <div className="hp-mock-score"><span className="hp-mock-score-lbl">Volume</span><span className="hp-mock-score-val" style={{color:'#66bb6a'}}>+18.2%</span></div>
          <div className="hp-mock-score"><span className="hp-mock-score-lbl">Price</span><span className="hp-mock-score-val" style={{color:'#66bb6a'}}>+9.4%</span></div>
        </div>
      </div>
    ),
  },
  {
    label: 'Lifecycle Stages',
    content: (
      <div className="hp-slide">
        <div className="hp-mock-label">Trend Lifecycle · currently accelerating</div>
        <svg viewBox="0 0 220 72" className="hp-mock-curve-svg" aria-hidden="true">
          <defs>
            <linearGradient id="curveAreaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f0a8b8" stopOpacity="0.08"/>
              <stop offset="100%" stopColor="#f0a8b8" stopOpacity="0"/>
            </linearGradient>
          </defs>
          {/* Full curve muted */}
          <path d="M 0,62 C 5,62 10,58 20,52 C 35,44 42,18 58,16 C 68,14 78,5 98,5 C 118,5 128,18 142,22 C 156,28 162,48 175,54 C 190,60 205,64 220,64"
                fill="none" stroke="#252525" strokeWidth="2" strokeLinecap="round"/>
          {/* Filled area under accent portion */}
          <path d="M 0,62 C 5,62 10,58 20,52 C 35,44 42,18 58,16 L 58,65 L 0,65 Z"
                fill="url(#curveAreaGrad)"/>
          {/* Accent portion of curve (up to Accelerating) */}
          <path d="M 0,62 C 5,62 10,58 20,52 C 35,44 42,18 58,16"
                fill="none" stroke="#f0a8b8" strokeWidth="2" strokeLinecap="round" strokeOpacity="0.8"/>
          {/* Current position dot */}
          <circle cx="58" cy="16" r="3.5" fill="#f0a8b8"/>
          <circle cx="58" cy="16" r="6" fill="#f0a8b8" fillOpacity="0.2"/>
          {/* Stage tick marks + labels */}
          {[['Emerging',20,52],['Accel.',58,16],['Peak',98,5],['Saturating',142,22],['Decline',175,54],['Dormant',214,64]].map(([s,cx,cy]) => (
            <g key={s}>
              <line x1={cx} y1={cy+3} x2={cx} y2="70" stroke="#222" strokeWidth="1"/>
              <text x={cx} y="78" textAnchor="middle" fontSize="6.5" fill={s==='Accel.' ? '#f0a8b8' : '#333'} fontWeight={s==='Accel.' ? '700' : '400'}>{s}</text>
            </g>
          ))}
        </svg>
      </div>
    ),
  },
  {
    label: '30-Day Forecast',
    content: (
      <div className="hp-slide">
        <div className="hp-mock-label">Search Volume Forecast</div>
        <svg viewBox="0 0 200 58" className="hp-mock-linechart-svg" aria-hidden="true">
          <defs>
            <linearGradient id="lineAreaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f0a8b8" stopOpacity="0.25"/>
              <stop offset="100%" stopColor="#f0a8b8" stopOpacity="0"/>
            </linearGradient>
          </defs>
          {/* Area fill under historical */}
          <path d="M 0,38 L 18,30 L 36,33 L 55,21 L 73,25 L 91,15 L 109,19 L 127,11 L 145,14 L 145,55 L 0,55 Z"
                fill="url(#lineAreaGrad)"/>
          {/* Historical line */}
          <polyline points="0,38 18,30 36,33 55,21 73,25 91,15 109,19 127,11 145,14"
                    fill="none" stroke="#f0a8b8" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round"/>
          {/* Forecast dashed line */}
          <polyline points="145,14 164,6 182,9 200,2"
                    fill="none" stroke="#f0a8b8" strokeWidth="1.5" strokeDasharray="4,3"
                    strokeOpacity="0.4" strokeLinejoin="round" strokeLinecap="round"/>
          {/* Confidence band */}
          <path d="M 145,14 C 155,10 165,2 164,6 L 200,2 L 200,16 C 182,18 165,14 145,14 Z"
                fill="#f0a8b8" fillOpacity="0.06"/>
        </svg>
        <div className="hp-mock-chart-legend">
          <span className="hp-mock-legend-line" />Historical
          <span className="hp-mock-legend-line hp-mock-legend-line--dash" />Forecast
        </div>
      </div>
    ),
  },
  {
    label: 'Top Garments to Source',
    content: (
      <div className="hp-slide">
        <div className="hp-mock-label">Top Garments to Source · vintage denim</div>
        <div className="hp-mock-sourcing">
          {[
            ["Levi's 501 (1980s–90s)", "$45–$110"],
            ["Lee Riders trucker jacket", "$55–$130"],
            ["Wrangler high-rise jeans", "$30–$75"],
          ].map(([item, price]) => (
            <div className="hp-mock-source-row" key={item}>
              <span className="hp-mock-source-item">{item}</span>
              <span className="hp-mock-source-price">{price}</span>
            </div>
          ))}
        </div>
      </div>
    ),
  },
]

export const VINTAGE_SLIDES = [
  {
    label: 'Era Classification',
    content: (
      <div className="hp-slide">
        <div className="hp-mock-era-label">Boho &amp; Glam Rock (Early 1970s)</div>
        <div className="hp-mock-conf-row">
          <span className="hp-mock-conf-pct">87%</span>
          <div className="hp-mock-conf-track">
            <div className="hp-mock-conf-fill" style={{width:'87%'}} />
          </div>
        </div>
        <p className="hp-mock-reasoning">Peasant blouse silhouette, macramé trim, and earth-tone palette are hallmarks of early 1970s boho style.</p>
      </div>
    ),
  },
  {
    label: 'Descriptor Chips',
    content: (
      <div className="hp-slide">
        <div className="hp-mock-label">Selected Descriptors</div>
        <div className="hp-mock-chips">
          {['Corduroy','Bell bottoms','Peasant blouse','Macramé','Burnt orange','Tie-dye','Platform boot'].map(c => (
            <span className="hp-mock-chip" key={c}>{c}</span>
          ))}
        </div>
      </div>
    ),
  },
  {
    label: 'Market Pricing',
    content: (
      <div className="hp-slide">
        <div className="hp-mock-label">Market Data · Early 1970s</div>
        <div className="hp-mock-price-stats">
          <div className="hp-mock-pstat"><span>Min</span><strong>$18</strong></div>
          <div className="hp-mock-pstat hp-mock-pstat--avg"><span>Avg</span><strong>$64</strong></div>
          <div className="hp-mock-pstat"><span>Max</span><strong>$210</strong></div>
        </div>
        <div className="hp-mock-badge hp-mock-badge--peak" style={{marginTop:'0.5rem',alignSelf:'flex-start'}}>Peak Demand · 24.3</div>
      </div>
    ),
  },
  {
    label: 'Similar on Etsy',
    content: (
      <div className="hp-slide">
        <div className="hp-mock-label">Similar on Etsy · 1970s vintage peasant blouse</div>
        <div className="hp-mock-sourcing">
          {[
            ['Vintage 70s Cotton Peasant Blouse', '$38.00'],
            ['1970s Embroidered Prairie Top', '$52.00'],
            ['Boho Folk Blouse w/ Lace Trim', '$44.50'],
          ].map(([t, p]) => (
            <div className="hp-mock-source-row" key={t}>
              <span className="hp-mock-source-item">{t}</span>
              <span className="hp-mock-source-price">{p}</span>
            </div>
          ))}
        </div>
      </div>
    ),
  },
]

export function CardCarousel({ slides }) {
  const [active, setActive] = useState(0)
  const [paused, setPaused] = useState(false)

  useEffect(() => {
    if (paused) return
    const t = setInterval(() => setActive(i => (i + 1) % slides.length), 3500)
    return () => clearInterval(t)
  }, [slides.length, paused])

  const prev = (e) => {
    e.stopPropagation()
    setPaused(true)
    setActive(i => (i - 1 + slides.length) % slides.length)
  }

  const next = (e) => {
    e.stopPropagation()
    setPaused(true)
    setActive(i => (i + 1) % slides.length)
  }

  return (
    <div className="hp-carousel">
      <div className="hp-carousel-inner">
        <button className="hp-carousel-arrow hp-carousel-arrow--prev" onClick={prev} type="button" aria-label="Previous">‹</button>
        <div className="hp-carousel-window">
          {slides.map((slide, i) => (
            <div
              key={i}
              className={`hp-carousel-slide${i === active ? ' active' : ''}`}
            >
              {slide.content}
            </div>
          ))}
        </div>
        <button className="hp-carousel-arrow hp-carousel-arrow--next" onClick={next} type="button" aria-label="Next">›</button>
      </div>
      <div className="hp-carousel-footer">
        <div className="hp-carousel-dots">
          {slides.map((_, i) => (
            <button
              key={i}
              className={`hp-carousel-dot${i === active ? ' active' : ''}`}
              onClick={e => { e.stopPropagation(); setPaused(true); setActive(i) }}
              type="button"
              aria-label={slides[i].label}
            />
          ))}
        </div>
        <span className="hp-carousel-label">{slides[active].label}</span>
      </div>
    </div>
  )
}

const ERA_IMAGE_IDS = [
  { label: '1930s', id: '1930s' },
  { label: '1950s', id: '1950s' },
  { label: 'Early 1970s', id: 'early-1970s' },
  { label: 'Early 1980s', id: 'early-1980s' },
]

export function HomeImageCarousel({ items }) {
  // items: [{label, imgUrl}] — already resolved
  const [active, setActive] = useState(0)
  const [paused, setPaused] = useState(false)
  const timerRef = useRef(null)

  useEffect(() => {
    if (items.length < 2 || paused) return
    timerRef.current = setInterval(() => setActive(i => (i + 1) % items.length), 4000)
    return () => clearInterval(timerRef.current)
  }, [items.length, paused])

  if (items.length === 0) return <div className="hp-img-car hp-img-car--loading" />

  const slide = items[active]
  const prev = (e) => { e.stopPropagation(); setPaused(true); setActive(i => (i - 1 + items.length) % items.length) }
  const next = (e) => { e.stopPropagation(); setPaused(true); setActive(i => (i + 1) % items.length) }

  return (
    <div className="hp-img-car">
      <div className="hp-img-car-inner">
        <button className="hp-img-car-arrow" onClick={prev} type="button" aria-label="Previous">‹</button>
        <div className="hp-img-car-window">
          {slide.imgUrl ? (
            <img src={slide.imgUrl} alt={slide.label} className="hp-img-car-img" />
          ) : (
            <div className="hp-img-car-placeholder">
              <span className="hp-img-car-placeholder-text">{slide.label}</span>
            </div>
          )}
        </div>
        <button className="hp-img-car-arrow" onClick={next} type="button" aria-label="Next">›</button>
      </div>
      <div className="hp-img-car-footer">
        <span className="hp-img-car-label">{slide.label}</span>
        <div className="hp-img-car-dots">
          {items.map((_, i) => (
            <button
              key={i}
              className={`hp-img-car-dot${i === active ? ' active' : ''}`}
              onClick={e => { e.stopPropagation(); setPaused(true); setActive(i) }}
              type="button"
              aria-label={items[i].label}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

export default function HomePage({ onGoToDashboard, onGoToVintage }) {
  const { logout, isAuthenticated, openSignIn } = useAuth()
  const [trendImages, setTrendImages] = useState([])
  const [eraImages, setEraImages] = useState([])

  useEffect(() => {
    // Fetch images only for seed keywords
    api.get('/trends/keywords/list')
      .then(res => {
        const seeds = (res.data.keywords || [])
          .filter(k => k.source === 'seed')
          .slice(0, 4)
        return Promise.all(
          seeds.map(k =>
            api.get(`/trends/${encodeURIComponent(k.keyword)}/images`)
              .then(r => ({ label: k.keyword, imgUrl: (r.data.images || [])[0]?.image_url || null }))
              .catch(() => ({ label: k.keyword, imgUrl: null }))
          )
        )
      })
      .then(slides => setTrendImages(slides))
      .catch(() => {})
  }, [])

  useEffect(() => {
    // Fetch one image per fixed era
    Promise.all(
      ERA_IMAGE_IDS.map(({ label, id }) =>
        api.get(`/vintage/eras/${encodeURIComponent(id)}/images`)
          .then(r => ({ label, imgUrl: (r.data.images || [])[0]?.image_url || null }))
          .catch(() => ({ label, imgUrl: null }))
      )
    ).then(slides => setEraImages(slides))
  }, [])

  return (
    <div className="hp-root">
      <div className="hp-body">
        <div className="hp-hero">
          <img src="/ratatat-logo-sq.jpg" alt="ratadat" className="hp-hero-logo" />
          <p className="hp-subtitle">
            Market insight and trend forecasting for secondhand and vintage fashion resellers. Two tools to help you source smarter, price confidently, and list faster.
          </p>
          {isAuthenticated
            ? <button className="logout-btn hp-hero-auth-btn" onClick={logout}>Sign Out</button>
            : <button className="logout-btn hp-hero-auth-btn" onClick={openSignIn}>Sign In</button>
          }
        </div>

        <div className="hp-cards">
          <button className="hp-card" onClick={onGoToDashboard}>
            <div className="hp-card-content">
              <div className="hp-card-title">Trend Forecast</div>
              <p className="hp-card-desc">
                Track resale search demand across eBay, Etsy, Poshmark, and Depop in real time.
                See which keywords are emerging, peaking, or fading — and compare trends side by
                side to decide what to source next. Forecasts project 30-day demand so you can
                get ahead of the market before it moves.
              </p>
            </div>
            <CardCarousel slides={TREND_SLIDES} />
            {trendImages.length > 0 && <HomeImageCarousel items={trendImages} />}
            <div className="hp-card-cta">Open Trend Forecast →</div>
          </button>

          <button className="hp-card" onClick={onGoToVintage}>
            <div className="hp-card-content">
              <div className="hp-card-title">Vintage</div>
              <p className="hp-card-desc">
                <strong>Classify</strong> any vintage garment by its era —
                select descriptors like fabrics, silhouettes, hardware, and labels, or upload
                photos, and get a primary era match with confidence score and reasoning.
                Then <strong>Explore</strong> any of the 24 eras to see its full style profile,
                moodboard images, market pricing, and demand data.
              </p>
            </div>
            <CardCarousel slides={VINTAGE_SLIDES} />
            {eraImages.length > 0 && <HomeImageCarousel items={eraImages} />}
            <div className="hp-card-cta">Open Vintage →</div>
          </button>
        </div>
      </div>
    </div>
  )
}
