import { useState, useEffect } from 'react'
import api from '../services/api'
import VolumeChart from './Charts/VolumeChart'
import PriceChart from './Charts/PriceChart'
import SalesVolumeChart from './Charts/SalesVolumeChart'
import VolatilityDisplay from './Charts/VolatilityDisplay'
import SentimentChart from './Charts/SentimentChart'
import SocialMentionsChart from './Charts/SocialMentionsChart'
import SeasonalChart from './Charts/SeasonalChart'
import SellThroughChart from './Charts/SellThroughChart'
import CorrelationPanel from './CorrelationPanel'
import RegionHeatmap from './RegionHeatmap'
import LifecycleBadge from './LifecycleBadge'
import TrendMoodboard from './TrendMoodboard'
import TrendCycleIndicator from './TrendCycleIndicator'
import InfoTooltip from './Charts/InfoTooltip'
import './TrendDetail.css'

const HORIZON_OPTIONS = [
  { label: '7 days', value: 7 },
  { label: '14 days', value: 14 },
  { label: '30 days', value: 30 },
]

export default function TrendDetail({ keyword, period, inline = false, onSearch }) {
  const [details, setDetails] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showForecast, setShowForecast] = useState(false)
  const [forecastHorizon, setForecastHorizon] = useState(14)
  const [forecastData, setForecastData] = useState(null)
  const [forecastLoading, setForecastLoading] = useState(false)
  const [forecastError, setForecastError] = useState('')
  const [seasonalData, setSeasonalData] = useState([])
  const [showSourcing, setShowSourcing] = useState(false)
  const [sourcingData, setSourcingData] = useState(null)
  const [sourcingLoading, setSourcingLoading] = useState(false)
  const [sourcingError, setSourcingError] = useState('')

  useEffect(() => {
    if (!keyword) return
    setLoading(true)
    api
      .get(`/trends/${encodeURIComponent(keyword)}/details`, { params: { period } })
      .then((res) => setDetails(res.data))
      .catch(() => setDetails(null))
      .finally(() => setLoading(false))
  }, [keyword, period])

  useEffect(() => {
    if (!keyword) return
    api
      .get(`/trends/${encodeURIComponent(keyword)}/seasonal`)
      .then((res) => setSeasonalData(res.data.seasonal || []))
      .catch(() => setSeasonalData([]))
  }, [keyword])

  useEffect(() => {
    if (!showSourcing || sourcingData || sourcingLoading) return
    setSourcingLoading(true)
    setSourcingError('')
    api
      .get(`/trends/keywords/${encodeURIComponent(keyword)}/sourcing`)
      .then(res => setSourcingData(res.data.garments || []))
      .catch(() => setSourcingError('Failed to load sourcing suggestions.'))
      .finally(() => setSourcingLoading(false))
  }, [showSourcing, keyword])

  useEffect(() => {
    if (!showForecast) return
    setForecastLoading(true)
    setForecastError('')
    api
      .get(`/trends/${encodeURIComponent(keyword)}/forecast`, { params: { horizon: forecastHorizon } })
      .then((res) => {
        if (res.data.insufficient_data) {
          setForecastError('Not enough historical data to generate a forecast yet.')
          setForecastData(null)
        } else {
          setForecastData(res.data.forecast)
        }
      })
      .catch(() => setForecastError('Failed to load forecast.'))
      .finally(() => setForecastLoading(false))
  }, [showForecast, forecastHorizon, keyword])

  if (loading) {
    return <div className="trend-detail__loading">Loading trend details...</div>
  }

  if (!details) {
    return <div className="trend-detail__empty">No details available for "{keyword}"</div>
  }

  return (
    <div className={`trend-detail${inline ? ' trend-detail--inline' : ''}`}>
      {!inline && details.score?.lifecycle_stage && (
        <div className="trend-detail__header">
          <LifecycleBadge stage={details.score.lifecycle_stage} size="large" />
        </div>
      )}

      {!inline && details.score && (
        <div className="trend-detail__scores">
          <div className="score-item">
            <span className="score-label">Composite Score <InfoTooltip text="Weighted trend score: 60% volume growth + 40% price growth. Positive = trending up, negative = declining." /></span>
            <span className="score-value" style={{ color: details.score.composite_score > 0 ? '#27ae60' : details.score.composite_score < 0 ? '#e74c3c' : '#aaa' }}>
              {details.score.composite_score > 0 ? '+' : ''}{details.score.composite_score?.toFixed(1)}
            </span>
          </div>
          <div className="score-item">
            <span className="score-label">Volume Growth <InfoTooltip text="% change in Google Trends search interest comparing the first half vs second half of the selected period." /></span>
            <span className="score-value" style={{ color: details.score.volume_growth > 0 ? '#27ae60' : details.score.volume_growth < 0 ? '#e74c3c' : '#aaa' }}>
              {details.score.volume_growth > 0 ? '+' : ''}{details.score.volume_growth?.toFixed(1)}%
            </span>
          </div>
          <div className="score-item">
            <span className="score-label">Price Growth <InfoTooltip text="% change in average selling price across eBay, Etsy, Poshmark, and Depop comparing the first half vs second half of the selected period." /></span>
            <span className="score-value" style={{ color: details.score.price_growth > 0 ? '#27ae60' : details.score.price_growth < 0 ? '#e74c3c' : '#aaa' }}>
              {details.score.price_growth > 0 ? '+' : ''}{details.score.price_growth?.toFixed(1)}%
            </span>
          </div>
        </div>
      )}

      <TrendMoodboard keyword={keyword} />

      <TrendCycleIndicator stage={details.score?.lifecycle_stage} />

      <div className="trend-detail__charts">
        {/* Search volume chart with forecast controls */}
        <div className="forecast-chart-wrapper">
          <div className="forecast-controls">
            <button
              className={`forecast-toggle ${showForecast ? 'forecast-toggle--active' : ''}`}
              onClick={() => setShowForecast(v => !v)}
            >
              {showForecast ? '✕ Hide Forecast' : '◆ Show Forecast'}
            </button>
            {showForecast && (
              <div className="forecast-horizon-tabs">
                {HORIZON_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    className={`forecast-horizon-tab ${forecastHorizon === opt.value ? 'forecast-horizon-tab--active' : ''}`}
                    onClick={() => setForecastHorizon(opt.value)}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {showForecast && forecastLoading && (
            <p className="forecast-status">Generating forecast...</p>
          )}
          {showForecast && forecastError && (
            <p className="forecast-error">{forecastError}</p>
          )}

          <VolumeChart
            data={details.search_volume}
            forecastData={showForecast && !forecastLoading && !forecastError ? forecastData : null}
          />

          {showForecast && forecastData && (
            <p className="forecast-legend">
              <span className="forecast-legend__historical" /> Historical &nbsp;
              <span className="forecast-legend__forecast" /> Forecast &nbsp;
              <span className="forecast-legend__band" /> 95% confidence interval
            </p>
          )}
        </div>

        <PriceChart data={details.ebay_avg_price} />
        <SalesVolumeChart data={details.sales_volume} />
        <VolatilityDisplay value={details.price_volatility} cv={details.price_volatility_cv} />
        <SocialMentionsChart
          reddit={details.social_mentions?.reddit}
          tiktok={details.social_mentions?.tiktok}
          news={details.social_mentions?.news}
        />
        <SentimentChart
          newsData={details.social_mentions?.news_sentiment}
          redditSentiment={details.social_mentions?.reddit_sentiment}
          tiktokSentiment={details.social_mentions?.tiktok_sentiment}
        />
        <SellThroughChart data={details.sell_through} />
        <SeasonalChart data={seasonalData} />
        <CorrelationPanel keyword={keyword} period={period} onSearch={onSearch} />
      </div>

      <RegionHeatmap usRegions={details.regions_us} />

      {/* ── Top Garments to Source ── */}
      <div className="sourcing-panel">
        <button
          className={`sourcing-toggle${showSourcing ? ' sourcing-toggle--active' : ''}`}
          onClick={() => setShowSourcing(v => !v)}
          type="button"
        >
          {showSourcing ? '✕ Hide Garments to Source' : '◆ Top Garments to Source'}
        </button>

        {showSourcing && (
          <div className="sourcing-body">
            {sourcingLoading && (
              <p className="sourcing-status">Generating recommendations…</p>
            )}
            {sourcingError && (
              <p className="sourcing-error">{sourcingError}</p>
            )}
            {sourcingData && sourcingData.length > 0 && (
              <div className="sourcing-list">
                {sourcingData.map((g, i) => (
                  <div className="sourcing-item" key={i}>
                    <div className="sourcing-item-header">
                      <span className="sourcing-item-name">{g.item}</span>
                      <span className="sourcing-item-price">{g.price_range}</span>
                    </div>
                    <p className="sourcing-item-why">{g.why}</p>
                    <p className="sourcing-item-tip">
                      <span className="sourcing-tip-label">How to find: </span>
                      {g.sourcing_tip}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
