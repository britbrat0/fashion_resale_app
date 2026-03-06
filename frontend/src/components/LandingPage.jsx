import { useState, useEffect } from 'react'
import { useAuth } from '../hooks/useAuth'
import { CardCarousel, TREND_SLIDES, VINTAGE_SLIDES, HomeImageCarousel } from './HomePage'
import './LandingPage.css'

const PREVIEW_ERA_IDS = ['1920s', '1950s', 'early-1970s', 'early-1980s']
const PREVIEW_KEYWORDS = ['vintage denim', '1950s dress', 'leather jacket', 'wrap dress']

export default function LandingPage() {
  const { login, register } = useAuth()
  const [isRegister, setIsRegister] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [eraImages, setEraImages] = useState([])
  const [trendImages, setTrendImages] = useState([])

  useEffect(() => {
    Promise.all(
      PREVIEW_ERA_IDS.map(id =>
        fetch(`/api/vintage/eras/${encodeURIComponent(id)}/images`)
          .then(r => r.ok ? r.json() : null)
          .then(d => ({ label: id.replace(/-/g, ' '), imgUrl: (d?.images || [])[0]?.image_url || null }))
          .catch(() => ({ label: id, imgUrl: null }))
      )
    ).then(slides => setEraImages(slides.filter(s => s.imgUrl)))
  }, [])

  useEffect(() => {
    Promise.all(
      PREVIEW_KEYWORDS.map(kw =>
        fetch(`/api/trends/${encodeURIComponent(kw)}/images`)
          .then(r => r.ok ? r.json() : null)
          .then(d => ({ label: kw, imgUrl: (d?.images || [])[0]?.image_url || null }))
          .catch(() => ({ label: kw, imgUrl: null }))
      )
    ).then(slides => setTrendImages(slides.filter(s => s.imgUrl)))
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (isRegister) {
        await register(email, password)
      } else {
        await login(email, password)
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="lp-root">
      <div className="lp-hero">
        <h1 className="lp-title">Fashion Resale Tool</h1>
        <p className="lp-subtitle">Detect and predict fashion resale trend cycles</p>

        <div className="lp-form-card">
          <div className="lp-form-tabs">
            <button
              className={`lp-form-tab${!isRegister ? ' active' : ''}`}
              onClick={() => { setIsRegister(false); setError('') }}
              type="button"
            >Sign In</button>
            <button
              className={`lp-form-tab${isRegister ? ' active' : ''}`}
              onClick={() => { setIsRegister(true); setError('') }}
              type="button"
            >Create Account</button>
          </div>

          <form onSubmit={handleSubmit} className="lp-form">
            <div className="lp-field">
              <label htmlFor="lp-email">Email</label>
              <input
                id="lp-email"
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
              />
            </div>
            <div className="lp-field">
              <label htmlFor="lp-password">Password</label>
              <input
                id="lp-password"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Enter password"
                required
                minLength={6}
              />
            </div>
            {error && <div className="lp-error">{error}</div>}
            <button type="submit" className="lp-submit" disabled={loading}>
              {loading ? 'Please wait…' : isRegister ? 'Create Account' : 'Sign In'}
            </button>
          </form>
        </div>
      </div>

      <div className="lp-preview">
        <p className="lp-preview-label">What's inside</p>
        <p className="lp-preview-sub">Two tools to help you source smarter, price confidently, and list faster.</p>
        <div className="lp-cards">
          <div className="lp-card">
            <div className="lp-card-title">Trend Forecast</div>
            <p className="lp-card-desc">
              Track resale search demand across eBay, Etsy, Poshmark, and Depop in real time.
              See which keywords are emerging, peaking, or fading — and compare trends side by
              side to decide what to source next.
            </p>
            <CardCarousel slides={TREND_SLIDES} />
          {trendImages.length > 0 && <HomeImageCarousel items={trendImages} />}
          </div>
          <div className="lp-card">
            <div className="lp-card-title">Vintage</div>
            <p className="lp-card-desc">
              <strong>Classify</strong> any vintage garment by its era using descriptors or photos.
              Then <strong>Explore</strong> any of the 24 eras to see its full style profile,
              moodboard images, market pricing, and demand data.
            </p>
            <CardCarousel slides={VINTAGE_SLIDES} />
          {eraImages.length > 0 && <HomeImageCarousel items={eraImages} />}
          </div>
        </div>
      </div>
    </div>
  )
}
