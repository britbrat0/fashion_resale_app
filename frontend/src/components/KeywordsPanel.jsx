import { useState, useEffect } from 'react'
import api from '../services/api'
import TrendDetail from './TrendDetail'
import './KeywordsPanel.css'

function timeAgo(dateStr) {
  if (!dateStr) return '—'
  const date = new Date(dateStr)
  if (isNaN(date)) return '—'
  const seconds = Math.floor((Date.now() - date) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export default function KeywordsPanel({ compareKeywords = [], onCompare, period = 7, focusKeyword = null, onCorrelationClick }) {
  const [keywords, setKeywords] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [removing, setRemoving] = useState(null)
  const [expandedKeyword, setExpandedKeyword] = useState(null)

  useEffect(() => {
    if (!focusKeyword) return
    setExpandedKeyword(focusKeyword)
    // Wait for the row to render, then scroll it into view
    setTimeout(() => {
      const el = document.querySelector(`[data-kw-row="${CSS.escape(focusKeyword)}"]`)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 80)
  }, [focusKeyword])

  useEffect(() => {
    fetchKeywords()
  }, [])

  const fetchKeywords = async () => {
    setLoading(true)
    try {
      const res = await api.get('/trends/keywords/list')
      setKeywords(res.data.keywords || [])
    } catch {
      setKeywords([])
    } finally {
      setLoading(false)
    }
  }

  const handleRemove = async (keyword) => {
    setRemoving(keyword)
    try {
      await api.delete(`/trends/keywords/${encodeURIComponent(keyword)}`)
      setKeywords(prev => prev.filter(k => k.keyword !== keyword))
    } catch {
      // seed keyword or other error — silently ignore
    } finally {
      setRemoving(null)
    }
  }

  const seedCount = keywords.filter(k => k.source === 'seed').length
  const userCount = keywords.filter(k => k.source !== 'seed').length

  const filtered = keywords.filter(k =>
    k.keyword.toLowerCase().includes(filter.toLowerCase())
  )

  return (
    <div className="keywords-panel">
      <div className="keywords-panel__header">
        <div>
          <h2>Tracked Keywords</h2>
          <p className="keywords-panel__subtitle">
            {keywords.length} total &nbsp;·&nbsp;
            <span className="kw-count kw-count--seed">{seedCount} seed</span>
            &nbsp;·&nbsp;
            <span className="kw-count kw-count--user">{userCount} user</span>
          </p>
        </div>
      </div>

      <div className="keywords-panel__toolbar">
        <input
          type="text"
          className="keywords-panel__search"
          placeholder="Filter keywords..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
        />
      </div>

      {loading && <p className="keywords-panel__status">Loading keywords...</p>}

      {!loading && filtered.length === 0 && (
        <p className="keywords-panel__status">
          {filter ? `No keywords match "${filter}"` : 'No keywords tracked yet.'}
        </p>
      )}

      {!loading && filtered.length > 0 && (
        <table className="keywords-table">
          <thead>
            <tr>
              <th>Keyword</th>
              <th>Source</th>
              <th>Last Active</th>
              <th>Added</th>
              <th></th>
              <th></th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(kw => {
              const inCompare = compareKeywords.includes(kw.keyword.toLowerCase())
              const isExpanded = expandedKeyword === kw.keyword
              return (
                <>
                  <tr
                    key={kw.keyword}
                    data-kw-row={kw.keyword}
                    className={`kw-row--clickable ${isExpanded ? 'kw-row--expanded' : ''}`}
                    onClick={() => setExpandedKeyword(isExpanded ? null : kw.keyword)}
                  >
                    <td className="keywords-table__keyword">
                      {kw.keyword}
                      {kw.scale === 'micro' && (
                        <span className="kw-micro-badge">Micro Trend</span>
                      )}
                    </td>
                    <td>
                      <span className={`kw-source-badge kw-source-badge--${kw.source === 'seed' ? 'seed' : 'user'}`}>
                        {kw.source === 'seed' ? '🌱 seed' : '👤 user'}
                      </span>
                    </td>
                    <td className="keywords-table__muted">
                      {timeAgo(kw.last_searched_at || kw.added_at)}
                    </td>
                    <td className="keywords-table__muted">
                      {kw.added_at ? new Date(kw.added_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="keywords-table__action">
                      <span className="kw-expand-hint">{isExpanded ? '▲' : '▼'}</span>
                    </td>
                    <td className="keywords-table__action" onClick={e => e.stopPropagation()}>
                      {onCompare && (
                        <button
                          className={`kw-compare-btn ${inCompare ? 'kw-compare-btn--active' : ''}`}
                          onClick={() => onCompare(kw.keyword)}
                        >
                          {inCompare ? '✓ Compare' : '+ Compare'}
                        </button>
                      )}
                    </td>
                    <td className="keywords-table__action" onClick={e => e.stopPropagation()}>
                      {kw.source === 'seed' ? (
                        <span className="kw-lock" title="Seed keyword — protected">🔒</span>
                      ) : (
                        <button
                          className="kw-remove-btn"
                          onClick={() => handleRemove(kw.keyword)}
                          disabled={removing === kw.keyword}
                        >
                          {removing === kw.keyword ? 'Removing...' : 'Remove'}
                        </button>
                      )}
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr key={`${kw.keyword}-detail`} className="kw-detail-row">
                      <td colSpan={7} className="kw-detail-cell">
                        <TrendDetail keyword={kw.keyword} period={period} onSearch={onCorrelationClick} />
                      </td>
                    </tr>
                  )}
                </>
              )
            })}
          </tbody>
        </table>
      )}

      <p className="keywords-panel__hint">
        User-searched keywords are automatically removed after 30 days of inactivity.
      </p>
    </div>
  )
}
