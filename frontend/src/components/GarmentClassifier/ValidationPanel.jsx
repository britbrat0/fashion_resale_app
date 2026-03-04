import { useState, useEffect } from 'react'
import api from '../../services/api'
import './ValidationPanel.css'

function AccuracyBar({ value }) {
  if (value == null) return <span className="vp-na">—</span>
  const pct = Math.round(value * 100)
  const color = pct >= 75 ? '#66bb6a' : pct >= 50 ? '#ffa726' : '#ef5350'
  return (
    <div className="vp-acc-bar-wrap">
      <div className="vp-acc-bar-track">
        <div className="vp-acc-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="vp-acc-pct" style={{ color }}>{pct}%</span>
    </div>
  )
}

export default function ValidationPanel() {
  const [open, setOpen] = useState(false)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)
  const [collecting, setCollecting] = useState(false)
  const [running, setRunning] = useState(false)
  const [runResult, setRunResult] = useState(null)
  const [error, setError] = useState(null)

  const fetchStats = () => {
    setLoading(true)
    api.get('/vintage/validation/stats')
      .then(res => setStats(res.data))
      .catch(() => setStats(null))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (open && !stats) fetchStats()
  }, [open])

  const handleCollect = () => {
    setCollecting(true)
    setError(null)
    api.post('/vintage/validation/collect?target=20')
      .then(() => {
        // Collection runs in background — poll stats after a delay
        setTimeout(fetchStats, 5000)
      })
      .catch(() => setError('Collection failed.'))
      .finally(() => setCollecting(false))
  }

  const handleRun = () => {
    setRunning(true)
    setRunResult(null)
    setError(null)
    api.post('/vintage/validation/run?limit=100')
      .then(res => {
        setRunResult(res.data)
        fetchStats()
      })
      .catch(() => setError('Validation run failed.'))
      .finally(() => setRunning(false))
  }

  const overall = stats?.overall || {}
  const hasData = stats && stats.total_collected > 0

  return (
    <div className="vp-root">
      <button
        className="vp-toggle"
        onClick={() => setOpen(o => !o)}
        type="button"
      >
        <span>Classifier Accuracy</span>
        <span className={`vp-chevron${open ? ' open' : ''}`}>›</span>
      </button>

      {open && (
        <div className="vp-body">
          <p className="vp-desc">
            Validate the era classifier against real Etsy vintage listings. Etsy sellers
            self-label items with decade tags ("1970s", "90s vintage") which serve as
            ground truth. Accuracy is measured at the decade level.
          </p>

          <div className="vp-actions">
            <button
              className="vp-btn"
              onClick={handleCollect}
              disabled={collecting}
              type="button"
            >
              {collecting ? <span className="vp-spinner" /> : null}
              {collecting ? 'Collecting…' : 'Collect Etsy Samples'}
            </button>
            <button
              className="vp-btn vp-btn--run"
              onClick={handleRun}
              disabled={running || !hasData}
              type="button"
            >
              {running ? <span className="vp-spinner" /> : null}
              {running ? `Running…` : 'Run Validation'}
            </button>
            <button
              className="vp-btn vp-btn--refresh"
              onClick={fetchStats}
              disabled={loading}
              type="button"
            >
              ↺
            </button>
          </div>

          {error && <p className="vp-error">{error}</p>}

          {runResult && (
            <p className="vp-run-result">
              Ran {runResult.total_run} items — decade correct: {runResult.decade_correct}, era correct: {runResult.era_correct}
            </p>
          )}

          {loading && <div className="vp-loading">Loading…</div>}

          {stats && (
            <>
              {/* Overall stats */}
              <div className="vp-overall">
                <div className="vp-stat-group">
                  <div className="vp-stat">
                    <span className="vp-stat-label">Collected</span>
                    <span className="vp-stat-value">{stats.total_collected}</span>
                  </div>
                  <div className="vp-stat">
                    <span className="vp-stat-label">Validated</span>
                    <span className="vp-stat-value">{stats.total_validated}</span>
                  </div>
                  <div className="vp-stat">
                    <span className="vp-stat-label">Pending</span>
                    <span className="vp-stat-value">{stats.pending}</span>
                  </div>
                  <div className="vp-stat">
                    <span className="vp-stat-label">Avg Confidence</span>
                    <span className="vp-stat-value">
                      {overall.avg_confidence != null ? `${Math.round(overall.avg_confidence * 100)}%` : '—'}
                    </span>
                  </div>
                </div>

                {stats.total_validated > 0 && (
                  <div className="vp-accuracy-row">
                    <div className="vp-accuracy-item">
                      <span className="vp-accuracy-label">Decade accuracy</span>
                      <AccuracyBar value={overall.decade_accuracy} />
                      <span className="vp-accuracy-sub">
                        {overall.decade_correct}/{stats.total_validated} correct
                      </span>
                    </div>
                    <div className="vp-accuracy-item">
                      <span className="vp-accuracy-label">Era accuracy</span>
                      <AccuracyBar value={overall.era_accuracy} />
                      <span className="vp-accuracy-sub">
                        {overall.era_correct}/{stats.total_validated} correct
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* Per-era table */}
              {stats.per_era?.length > 0 && (
                <div className="vp-table-wrap">
                  <table className="vp-table">
                    <thead>
                      <tr>
                        <th>Era</th>
                        <th>Decade</th>
                        <th>Samples</th>
                        <th>Decade acc.</th>
                        <th>Era acc.</th>
                        <th>Avg conf.</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.per_era.map(row => (
                        <tr key={row.era_id}>
                          <td className="vp-era-name">{row.era_label}</td>
                          <td className="vp-decade">{row.decade}</td>
                          <td>{row.samples}</td>
                          <td><AccuracyBar value={row.decade_accuracy} /></td>
                          <td><AccuracyBar value={row.era_accuracy} /></td>
                          <td>{row.avg_confidence != null ? `${Math.round(row.avg_confidence * 100)}%` : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {!hasData && (
                <p className="vp-empty">
                  No samples yet. Click <strong>Collect Etsy Samples</strong> to build the dataset.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
