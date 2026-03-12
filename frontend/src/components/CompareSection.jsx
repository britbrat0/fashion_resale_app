import { useState, useEffect, useRef } from 'react'
import api from '../services/api'
import { useAuth } from '../hooks/useAuth'
import CompareChart from './Charts/CompareChart'
import LifecycleBadge from './LifecycleBadge'
import './CompareSection.css'

const COLORS = ['#cc3333', '#7c3aed', '#db2777', '#0891b2', '#b45309', '#0f766e']
const MAX_COMPARE = 6

export default function CompareSection({ compareKeywords, onKeywordsChange, onSeriesChange, period = 30 }) {
  const { isAuthenticated } = useAuth()
  const [compareData, setCompareData] = useState({ keywords: [], series: [] })
  const [inputValue, setInputValue] = useState('')
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState('')
  // Track last fetched keyword string to avoid re-fetching on same data
  const lastGuestKeywordsRef = useRef(null)

  useEffect(() => {
    if (isAuthenticated) {
      fetchCompareData()
      return
    }
    // For guests: include period in the cache key so period changes trigger a re-fetch
    const kwStr = (compareKeywords || []).slice().sort().join(',')
    const cacheKey = `${kwStr}::${period}`
    if (cacheKey === lastGuestKeywordsRef.current) return
    lastGuestKeywordsRef.current = cacheKey
    fetchGuestCompareData()
  }, [period, isAuthenticated, compareKeywords])

  const fetchCompareData = async () => {
    setLoading(true)
    try {
      const res = await api.get('/compare/data', { params: { period } })
      setCompareData(res.data)
      if (onKeywordsChange) onKeywordsChange(res.data.keywords || [])
      if (onSeriesChange) onSeriesChange(res.data.series || [])
    } catch {
      setCompareData({ keywords: [], series: [] })
    } finally {
      setLoading(false)
    }
  }

  const fetchGuestCompareData = async () => {
    if (!compareKeywords || compareKeywords.length === 0) {
      setCompareData({ keywords: [], series: [] })
      if (onSeriesChange) onSeriesChange([])
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const res = await api.get('/compare/public-data', {
        params: { keywords: compareKeywords.join(','), period },
      })
      // Use compareKeywords (prop) as authoritative list — don't call onKeywordsChange
      // to avoid triggering an infinite re-fetch loop
      const data = { keywords: compareKeywords, series: res.data.series || [] }
      setCompareData(data)
      if (onSeriesChange) onSeriesChange(data.series)
    } catch {
      setCompareData({ keywords: compareKeywords, series: [] })
    } finally {
      setLoading(false)
    }
  }

  const handleAdd = async (keyword) => {
    const kw = keyword.toLowerCase().trim()
    if (!kw) return
    if (compareData.keywords.includes(kw)) {
      setError(`"${kw}" is already in your comparison`)
      return
    }
    if (compareData.keywords.length >= MAX_COMPARE) {
      setError(`Maximum ${MAX_COMPARE} keywords. Remove one first.`)
      return
    }

    setAdding(true)
    setError('')
    try {
      await api.post(`/compare/${encodeURIComponent(kw)}`)
      await fetchCompareData()  // fetchCompareData calls onKeywordsChange
      setInputValue('')
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to add keyword')
    } finally {
      setAdding(false)
    }
  }

  const handleRemove = async (keyword) => {
    try {
      await api.delete(`/compare/${encodeURIComponent(keyword)}`)
      setCompareData(prev => {
        const updated = {
          keywords: prev.keywords.filter(k => k !== keyword),
          series: prev.series.filter(s => s.keyword !== keyword),
        }
        if (onKeywordsChange) onKeywordsChange(updated.keywords)
        return updated
      })
    } catch {
      // ignore
    }
  }

  const handleClear = async () => {
    try {
      await api.delete('/compare')
      setCompareData({ keywords: [], series: [] })
      if (onKeywordsChange) onKeywordsChange([])
    } catch {
      // ignore
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    handleAdd(inputValue)
  }

  return (
    <div className="compare-section">
      <div className="compare-header">
        <h2>Compare Trends</h2>
        {compareData.keywords.length > 0 && (
          <button className="compare-clear-btn" onClick={handleClear}>
            Clear all
          </button>
        )}
      </div>

      <form className="compare-add-form" onSubmit={handleSubmit}>
        <input
          type="text"
          className="compare-input"
          placeholder="Add a trend to compare (e.g. gorpcore)..."
          value={inputValue}
          onChange={(e) => { setInputValue(e.target.value); setError('') }}
          disabled={adding}
        />
        <button
          type="submit"
          className="compare-add-btn"
          disabled={adding || !inputValue.trim() || compareData.keywords.length >= MAX_COMPARE}
        >
          {adding ? 'Scraping...' : '+ Add'}
        </button>
      </form>

      {error && <p className="compare-error">{error}</p>}

      {loading && <p className="compare-status">Loading comparison...</p>}

      {!loading && compareData.keywords.length === 0 && (
        <div className="compare-empty">
          <p>No trends added yet.</p>
          <p className="compare-empty-hint">
            Type a keyword above, or click <strong>+ Compare</strong> on any trend card to add it here.
          </p>
        </div>
      )}

      {!loading && compareData.keywords.length > 0 && (
        <>
          {/* Keyword chips */}
          <div className="compare-chips">
            {compareData.keywords.map((kw, i) => (
              <span
                key={kw}
                className="compare-chip"
                style={{ borderColor: COLORS[i % COLORS.length] }}
              >
                <span
                  className="compare-chip__dot"
                  style={{ background: COLORS[i % COLORS.length] }}
                />
                {kw}
                <button
                  className="compare-chip__remove"
                  onClick={() => handleRemove(kw)}
                >
                  ×
                </button>
              </span>
            ))}
          </div>

          {/* Chart */}
          <div className="compare-chart-wrapper">
            <h3 className="compare-chart-title">Search Volume Over Time</h3>
            <CompareChart series={compareData.series} />
          </div>

          {/* Scores grid */}
          <div className="compare-scores-grid">
            {compareData.series.map((s, i) => (
              <div
                key={s.keyword}
                className="compare-score-card"
                style={{ borderTopColor: COLORS[i % COLORS.length] }}
              >
                <div className="compare-score-card__keyword">{s.keyword}</div>
                <div className="compare-score-card__score">
                  {s.composite_score != null ? (
                    <span style={{ color: s.composite_score >= 0 ? '#27ae60' : '#e74c3c' }}>
                      {s.composite_score >= 0 ? '+' : ''}{s.composite_score.toFixed(1)}
                    </span>
                  ) : '—'}
                </div>
                {s.lifecycle_stage && (
                  <LifecycleBadge stage={s.lifecycle_stage} size="small" />
                )}
                <div className="compare-score-card__metrics">
                  <div className="compare-score-card__metric">
                    <span className="metric-label">Vol</span>
                    <span
                      className="metric-value"
                      style={{ color: s.volume_growth > 0 ? '#27ae60' : s.volume_growth < 0 ? '#e74c3c' : '#666' }}
                    >
                      {s.volume_growth != null ? `${s.volume_growth >= 0 ? '+' : ''}${s.volume_growth.toFixed(1)}%` : '—'}
                    </span>
                  </div>
                  <div className="compare-score-card__metric">
                    <span className="metric-label">Price</span>
                    <span className="metric-value">
                      {s.avg_price != null ? `$${s.avg_price.toFixed(0)}` : '—'}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
