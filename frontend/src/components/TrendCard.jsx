import { useState, useEffect, useRef } from 'react'
import api from '../services/api'
import LifecycleBadge from './LifecycleBadge'
import InfoTooltip from './Charts/InfoTooltip'
import './TrendCard.css'

function ForecastColumns({ forecast }) {
  if (!forecast) return null
  const { current_rank, projected_rank, rank_delta, slope, stage_warning } = forecast

  let deltaEl = null
  if (rank_delta > 0) deltaEl = <span className="tc-delta tc-delta--up">▲{rank_delta}</span>
  else if (rank_delta < 0) deltaEl = <span className="tc-delta tc-delta--down">▼{Math.abs(rank_delta)}</span>
  else deltaEl = <span className="tc-delta tc-delta--flat">↔</span>

  return (
    <div className="trend-card__forecast" onClick={e => e.stopPropagation()}>
      <span className="tc-forecast-label">7-day forecast <InfoTooltip text="Projected rank in 7 days based on recent search volume slope. ▲ = rising, ▼ = falling, ↔ = stable." /></span>
      <div className="tc-forecast-ranks">
        <span className="tc-rank-now">#{current_rank}</span>
        <span className="tc-rank-arrow">→</span>
        <span className={`tc-rank-proj ${projected_rank < current_rank ? 'tc-rank-proj--up' : projected_rank > current_rank ? 'tc-rank-proj--down' : ''}`}>
          #{projected_rank}
        </span>
        {deltaEl}
      </div>
      {stage_warning && (
        <div className="tc-forecast-badges">
          <span className="tc-stage-warn">⚠ {stage_warning}</span>
        </div>
      )}
    </div>
  )
}

export default function TrendCard({ trend, isExpanded, onClick, onRemove, onCompare, inCompare, forecast }) {
  const [thumbs, setThumbs] = useState([])
  const cardRef = useRef(null)

  useEffect(() => {
    if (isExpanded && cardRef.current) {
      cardRef.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  }, [isExpanded])

  useEffect(() => {
    api
      .get(`/trends/${encodeURIComponent(trend.keyword)}/images`)
      .then((res) => setThumbs((res.data.images || []).slice(0, 1)))
      .catch(() => {})
  }, [trend.keyword])
  const scoreColor = trend.composite_score > 0 ? '#27ae60' : trend.composite_score < 0 ? '#e74c3c' : '#666'
  const scorePrefix = trend.composite_score > 0 ? '+' : ''
  const isSeed = trend.source === 'seed'

  const handleRemove = (e) => {
    e.stopPropagation()
    if (!isSeed && onRemove) onRemove(trend.keyword)
  }

  const handleCompare = (e) => {
    e.stopPropagation()
    if (onCompare) onCompare(trend.keyword)
  }

  return (
    <div
      ref={cardRef}
      className={`trend-card ${isExpanded ? 'trend-card--expanded' : ''}`}
      onClick={onClick}
    >
      <div className="trend-card__header">
        <span className="trend-card__rank">#{trend.rank}</span>

        {thumbs.length > 0 && (
          <div className="trend-card__thumb-wrap">
            <img
              src={thumbs[0].image_url}
              alt={thumbs[0].title || trend.keyword}
              className="trend-card__thumb"
              loading="lazy"
            />
          </div>
        )}

        <div className="trend-card__info">
          <div className="trend-card__keyword-row">
            <span className="trend-card__keyword">{trend.keyword}</span>
            <span className="trend-card__expand">
              {isExpanded ? '\u25B2' : '\u25BC'}
            </span>
          </div>
          <div className="trend-card__meta">
            <span className="trend-card__score" style={{ color: scoreColor }}>
              {scorePrefix}{trend.composite_score?.toFixed(1)}
              <InfoTooltip text="Composite score: 60% volume growth + 40% price growth. Positive = trending up, negative = declining." />
            </span>
            {trend.lifecycle_stage && (
              <LifecycleBadge stage={trend.lifecycle_stage} size="small" />
            )}
            {trend.scale === 'micro' && (
              <span className="trend-card__micro-badge">Micro Trend</span>
            )}
          </div>
        </div>
        <ForecastColumns forecast={forecast} />

        <div className="trend-card__actions">
          <button
            className={`trend-card__compare ${inCompare ? 'trend-card__compare--active' : ''}`}
            onClick={handleCompare}
            title={inCompare ? 'Remove from compare' : 'Add to compare'}
          >
            {inCompare ? '✓ Compare' : '+ Compare'}
          </button>
          {isSeed ? (
            <span className="trend-card__lock" title="Seed keyword — protected">&#128274;</span>
          ) : (
            <button
              className="trend-card__remove"
              onClick={handleRemove}
              title="Remove keyword"
            >
              &#128465;
            </button>
          )}
        </div>
      </div>

      {isExpanded && (
        <div className="trend-card__details-hint">
          <div className="trend-card__growth-row">
            <div className="trend-card__growth-item">
              <span className="growth-label">Volume Growth <InfoTooltip text="% change in Google Trends search interest comparing the first half vs second half of the selected period." /></span>
              <span className="growth-value" style={{ color: trend.volume_growth > 0 ? '#27ae60' : '#e74c3c' }}>
                {trend.volume_growth > 0 ? '+' : ''}{trend.volume_growth?.toFixed(1)}%
              </span>
            </div>
            <div className="trend-card__growth-item">
              <span className="growth-label">Price Growth <InfoTooltip text="% change in average selling price across eBay, Etsy, Poshmark, and Depop comparing the first half vs second half of the selected period." /></span>
              <span className="growth-value" style={{ color: trend.price_growth > 0 ? '#27ae60' : '#e74c3c' }}>
                {trend.price_growth > 0 ? '+' : ''}{trend.price_growth?.toFixed(1)}%
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
