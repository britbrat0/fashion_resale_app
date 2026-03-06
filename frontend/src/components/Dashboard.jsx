import { useState, useEffect, useRef } from 'react'
import { useAuth } from '../hooks/useAuth'
import api from '../services/api'
import TrendCard from './TrendCard'
import TrendDetail from './TrendDetail'
import CompareSection from './CompareSection'
import KeywordsPanel from './KeywordsPanel'
import ChatBot from './ChatBot'
import './Dashboard.css'

export default function Dashboard({ onGoHome, onSwitchToVintage }) {
  const { logout } = useAuth()
  const [period, setPeriod] = useState(7)
  const [searchQuery, setSearchQuery] = useState('')
  const [trends, setTrends] = useState([])
  const [loading, setLoading] = useState(true)
  const [expandedKeyword, setExpandedKeyword] = useState(null)
  const [searchResult, setSearchResult] = useState(null)
  const [searchLoading, setSearchLoading] = useState(false)
  const [similarSuggestion, setSimilarSuggestion] = useState(null) // { original, similar }
  const [view, setView] = useState('top') // 'top', 'search', or 'compare'
  const [compareKeywords, setCompareKeywords] = useState([])
  const [trackedKeywords, setTrackedKeywords] = useState([])
  const [scrapeStep, setScrapeStep] = useState(0)
  const scrapeTimerRef = useRef(null)
  const [forecastMap, setForecastMap] = useState({})
  const [challengers, setChallengers] = useState([])
  const [compareSeries, setCompareSeries] = useState([])
  const [trackFocusKeyword, setTrackFocusKeyword] = useState(null)

  const SCRAPE_STEPS = [
    'Checking Google Trends data...',
    'Scraping eBay listings...',
    'Fetching Pinterest images...',
    'Analyzing price history...',
    'Computing trend score...',
  ]

  useEffect(() => {
    if (searchLoading) {
      setScrapeStep(0)
      scrapeTimerRef.current = setInterval(() => {
        setScrapeStep(s => (s + 1) % SCRAPE_STEPS.length)
      }, 1800)
    } else {
      clearInterval(scrapeTimerRef.current)
    }
    return () => clearInterval(scrapeTimerRef.current)
  }, [searchLoading])

  useEffect(() => {
    fetchTopTrends()
  }, [period])

  useEffect(() => {
    api.get('/trends/ranking-forecast', { params: { period } })
      .then(res => {
        const map = {}
        ;(res.data.top10 || []).forEach(item => { map[item.keyword] = item })
        ;(res.data.challengers || []).forEach(item => { map[item.keyword] = item })
        setForecastMap(map)
        setChallengers(res.data.challengers || [])
      })
      .catch(() => {})
  }, [period])

  const fetchTopTrends = async () => {
    setLoading(true)
    try {
      const res = await api.get('/trends/top', { params: { period } })
      setTrends(res.data.trends || [])
    } catch {
      setTrends([])
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = async (e) => {
    e.preventDefault()
    const kw = searchQuery.trim().toLowerCase()
    if (!kw) return
    setSearchLoading(true)
    setView('search')
    setExpandedKeyword(null)
    setSimilarSuggestion(null)
    setSearchResult(null)

    try {
      const check = await api.get('/trends/similar', { params: { keyword: kw } })
      if (check.data.similar) {
        setSimilarSuggestion({ original: kw, similar: check.data.similar })
        setSearchLoading(false)
        return
      }
    } catch {
      // similarity check failure is non-fatal — proceed with search
    }

    await doSearch(kw)
  }

  const doSearch = async (kw) => {
    setSearchLoading(true)
    setSimilarSuggestion(null)
    try {
      const res = await api.get('/trends/search', {
        params: { keyword: kw, period },
      })
      setSearchResult(res.data)
    } catch {
      setSearchResult(null)
    } finally {
      setSearchLoading(false)
    }
  }

  const handleBackToTop = () => {
    setView('top')
    setSearchResult(null)
    setSearchQuery('')
    setSimilarSuggestion(null)
    setExpandedKeyword(null)
  }

  const handleCorrelationClick = (kw) => {
    const kwLower = kw.toLowerCase().trim()
    if (trackedKeywords.includes(kwLower)) {
      setView('keywords')
      setTrackFocusKeyword(kwLower)
    } else {
      setView('search')
      setSearchQuery(kwLower)
      setExpandedKeyword(null)
      setSimilarSuggestion(null)
      setSearchResult(null)
      doSearch(kwLower)
    }
  }

  const handleCardClick = (keyword) => {
    setExpandedKeyword(expandedKeyword === keyword ? null : keyword)
  }

  const handleRemoveKeyword = async (keyword) => {
    try {
      await api.delete(`/trends/keywords/${encodeURIComponent(keyword)}`)
      setTrends(trends.filter(t => t.keyword !== keyword))
      if (expandedKeyword === keyword) setExpandedKeyword(null)
    } catch {
      // Silently fail — seed keyword protection will show nothing
    }
  }

  const handleCompare = async (keyword) => {
    const kw = keyword.toLowerCase().trim()
    const isInCompare = compareKeywords.includes(kw)

    // Optimistically update UI immediately
    if (isInCompare) {
      setCompareKeywords(prev => prev.filter(k => k !== kw))
    } else {
      setCompareKeywords(prev => [...prev, kw])
    }

    try {
      if (isInCompare) {
        await api.delete(`/compare/${encodeURIComponent(kw)}`)
      } else {
        await api.post(`/compare/${encodeURIComponent(kw)}`)
      }
    } catch {
      // Revert optimistic update on failure
      if (isInCompare) {
        setCompareKeywords(prev => [...prev, kw])
      } else {
        setCompareKeywords(prev => prev.filter(k => k !== kw))
      }
    }
  }

  // Sync compareKeywords and all tracked keywords from backend on mount
  useEffect(() => {
    api.get('/compare').then(res => {
      const kws = (res.data.keywords || []).map(k => typeof k === 'object' ? k.keyword : k)
      setCompareKeywords(kws)
    }).catch(() => {})

    api.get('/trends/keywords/list').then(res => {
      setTrackedKeywords((res.data.keywords || []).map(k => k.keyword))
    }).catch(() => {})
  }, [])

  return (
    <div className="dashboard">
      <header className="vintage-header">
        <div className="vintage-header-left">
          <div className="nav-logo-wrap" onClick={onGoHome}>
            <img src="/resale-rat-logo.png" alt="Resale Rat" className="nav-logo" />
          </div>
          <div className="nav-toggle">
            <button className="nav-toggle-btn active">Trend Forecast</button>
            <button className="nav-toggle-btn" onClick={onSwitchToVintage}>Vintage</button>
          </div>
        </div>
        <button onClick={logout} className="logout-btn">Sign Out</button>
      </header>

      <div className="vintage-tabs">
        <button
          className={`vintage-tab ${view !== 'search' && view !== 'compare' && view !== 'keywords' ? 'vintage-tab--active' : ''}`}
          onClick={() => { setView('top'); setSearchResult(null); setSearchQuery(''); setExpandedKeyword(null) }}
        >
          Top 10 Trends
        </button>
        <button
          className={`vintage-tab ${view === 'keywords' ? 'vintage-tab--active' : ''}`}
          onClick={() => setView('keywords')}
        >
          Track
        </button>
        <button
          className={`vintage-tab ${view === 'compare' ? 'vintage-tab--active' : ''}`}
          onClick={() => setView('compare')}
        >
          Compare
          {compareKeywords.length > 0 && (
            <span className="dashboard-tab__badge">{compareKeywords.length}</span>
          )}
        </button>
      </div>

      <main className="dashboard-content">
        <div className="controls-bar">
          <form onSubmit={handleSearch} className="search-form">
            <input
              type="text"
              placeholder="Search a trend (e.g., vintage denim)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="search-input"
            />
            <button type="submit" className="search-btn" disabled={searchLoading}>
              {searchLoading ? 'Scraping...' : 'Search'}
            </button>
          </form>

          <select
            value={period}
            onChange={(e) => setPeriod(Number(e.target.value))}
            className="period-select"
          >
            <option value={7}>Past 7 days</option>
            <option value={14}>Past 14 days</option>
            <option value={30}>Past 30 days</option>
            <option value={60}>Past 60 days</option>
            <option value={90}>Past 90 days</option>
          </select>
        </div>

        {view === 'search' ? (
          <div className="search-results">
            <div className="search-results__header">
              <h2>
                Search Results: <span className="search-keyword">{searchResult?.keyword || searchQuery}</span>
              </h2>
              <button onClick={handleBackToTop} className="back-btn">
                Back to Top Trends
              </button>
            </div>

            {searchLoading && (
              <div className="scrape-loader">
                <div className="scrape-loader__bar">
                  <div className="scrape-loader__fill" />
                </div>
                <div className="scrape-loader__steps">
                  {SCRAPE_STEPS.map((step, i) => (
                    <span
                      key={step}
                      className={`scrape-loader__step ${i === scrapeStep ? 'scrape-loader__step--active' : ''} ${i < scrapeStep ? 'scrape-loader__step--done' : ''}`}
                    >
                      {i < scrapeStep ? '✓' : i === scrapeStep ? '›' : '·'} {step}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {!searchLoading && similarSuggestion && (
              <div className="search-suggestion">
                <p className="search-suggestion__text">
                  We're already tracking <strong>"{similarSuggestion.similar}"</strong>, which may be related to "{similarSuggestion.original}".
                  What would you like to do?
                </p>
                <div className="search-suggestion__actions">
                  <button
                    className="search-suggestion__btn search-suggestion__btn--primary"
                    onClick={() => doSearch(similarSuggestion.similar)}
                  >
                    View "{similarSuggestion.similar}" data
                  </button>
                  <span className="search-suggestion__or">or</span>
                  <button
                    className="search-suggestion__btn search-suggestion__btn--secondary"
                    onClick={() => doSearch(similarSuggestion.original)}
                  >
                    Track "{similarSuggestion.original}" separately
                  </button>
                </div>
              </div>
            )}

            {!searchLoading && searchResult && (
              <TrendDetail keyword={searchResult.keyword} period={period} onSearch={handleCorrelationClick} />
            )}

            {!searchLoading && !searchResult && !similarSuggestion && (
              <p className="status-message">No results found. Try a different keyword.</p>
            )}
          </div>
        ) : view === 'keywords' ? (
          <KeywordsPanel
            compareKeywords={compareKeywords}
            onCompare={handleCompare}
            period={period}
            focusKeyword={trackFocusKeyword}
            onCorrelationClick={handleCorrelationClick}
          />
        ) : view === 'compare' ? (
          <div>
            <CompareSection
              compareKeywords={compareKeywords}
              onKeywordsChange={setCompareKeywords}
              onSeriesChange={setCompareSeries}
              period={period}
            />
          </div>
        ) : (
          <>
            {loading && <p className="status-message">Loading trends...</p>}

            {!loading && trends.length === 0 && (
              <div className="empty-state">
                <p className="status-message">No trend data available yet.</p>
                <p className="status-detail">
                  The scheduler will scrape data automatically every 6 hours.
                  You can also search for a specific trend above to trigger an on-demand scrape.
                </p>
              </div>
            )}

            {!loading && trends.length > 0 && (
              <>
                <div className="trends-list">
                  {trends.map((trend) => (
                    <div key={trend.keyword} className="trend-list-item">
                      <TrendCard
                        trend={trend}
                        isExpanded={expandedKeyword === trend.keyword}
                        onClick={() => handleCardClick(trend.keyword)}
                        onRemove={handleRemoveKeyword}
                        onCompare={handleCompare}
                        inCompare={compareKeywords.includes(trend.keyword.toLowerCase())}
                        forecast={forecastMap[trend.keyword] || null}
                      />
                      {expandedKeyword === trend.keyword && (
                        <TrendDetail keyword={trend.keyword} period={period} inline onSearch={handleCorrelationClick} />
                      )}
                    </div>
                  ))}
                </div>

                {challengers.length > 0 && (
                  <div className="challengers-section">
                    <h3 className="challengers-section__title">⬆ Rising Challengers</h3>
                    <p className="challengers-section__subtitle">Trends ranked outside the top 10 with rising momentum</p>
                    <div className="challengers-list">
                      {challengers.map((c) => {
                        let slopeEl
                        if (c.slope > 2) slopeEl = <span className="challenger__badge challenger__badge--strong-up">⬆ surging</span>
                        else if (c.slope > 0.5) slopeEl = <span className="challenger__badge challenger__badge--up">↑ rising</span>
                        else slopeEl = <span className="challenger__badge challenger__badge--flat">→ stable</span>

                        return (
                          <div key={c.keyword} className="challenger-card">
                            <span className="challenger__rank">#{c.current_rank}</span>
                            <div className="challenger__info">
                              <span className="challenger__keyword">{c.keyword}</span>
                              <div className="challenger__meta">
                                {slopeEl}
                                {c.stage_warning && (
                                  <span className="challenger__warn" title={c.stage_warning}>⚠ {c.stage_warning}</span>
                                )}
                              </div>
                            </div>
                            <div className="challenger__proj">
                              <span className="challenger__proj-label">projected</span>
                              <span className="challenger__proj-rank">#{c.projected_rank}</span>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </main>
      <ChatBot context={{
        view,
        keyword: searchResult?.keyword || (expandedKeyword) || null,
        trendData: searchResult || null,
        topTrends: trends,
        trackedKeywords,
        compareKeywords,
        compareSeries: view === 'compare' ? compareSeries : undefined,
      }} />
    </div>
  )
}
