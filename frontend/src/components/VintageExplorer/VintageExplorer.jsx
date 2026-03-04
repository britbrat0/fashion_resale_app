import { useState, useEffect, useRef, useCallback } from 'react'
import { useAuth } from '../../hooks/useAuth'
import api from '../../services/api'
import EraSelector from './EraSelector'
import EraTrends from './EraTrends'
import EraImageGrid from './EraImageGrid'
import EraBlockGrid, { ERA_BLOCKS } from './EraBlockGrid'
import EraBlockEras from './EraBlockEras'
import ChatBot from '../ChatBot'
import './VintageExplorer.css'

const findBlock = (eraId) => ERA_BLOCKS.find(b => b.ids.includes(eraId)) || null

export default function VintageExplorer({ onGoHome, onSwitchToDashboard, onSwitchToClassify, initialEraId }) {
  const { logout } = useAuth()
  const stellaRef = useRef(null)
  const [eras, setEras] = useState([])
  const [selectedEra, setSelectedEra] = useState(null)
  const [eraDetail, setEraDetail] = useState(null)
  const [marketData, setMarketData] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [exploreStep, setExploreStep] = useState(initialEraId ? 'detail' : 'blocks')
  const [selectedBlock, setSelectedBlock] = useState(
    initialEraId ? findBlock(initialEraId) : null
  )

  // Keyword tracking
  const [trackedKeywords, setTrackedKeywords] = useState(new Set())
  const [toast, setToast] = useState(null)
  const toastTimerRef = useRef(null)

  // Load tracked keywords on mount
  useEffect(() => {
    api.get('/trends/keywords/list')
      .then(res => setTrackedKeywords(new Set((res.data.keywords || []).map(k => k.keyword))))
      .catch(() => {})
  }, [])

  const showToast = useCallback((msg) => {
    setToast(msg)
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    toastTimerRef.current = setTimeout(() => setToast(null), 3000)
  }, [])

  const handleTrackKeyword = useCallback(async (kw) => {
    if (trackedKeywords.has(kw)) return
    try {
      await api.post(`/trends/keywords/${encodeURIComponent(kw)}/track`)
      setTrackedKeywords(prev => new Set([...prev, kw]))
      showToast(`Now tracking "${kw}" on Trend Forecast`)
    } catch {}
  }, [trackedKeywords, showToast])

  // Fetch era list on mount; pre-select initialEraId if provided
  useEffect(() => {
    api.get('/vintage/eras')
      .then(res => {
        const list = res.data.eras || []
        setEras(list)
        if (initialEraId) {
          const match = list.find(e => e.id === initialEraId)
          if (match) setSelectedEra(match)
        }
      })
      .catch(() => setEras([]))
  }, [])

  // Fetch full era detail + market data when selection changes
  useEffect(() => {
    if (!selectedEra) {
      setEraDetail(null)
      setMarketData(null)
      return
    }
    setDetailLoading(true)
    const id = encodeURIComponent(selectedEra.id)
    Promise.all([
      api.get(`/vintage/eras/${id}`),
      api.get(`/vintage/eras/${id}/market`),
    ])
      .then(([detailRes, marketRes]) => {
        setEraDetail(detailRes.data)
        setMarketData(marketRes.data)
      })
      .catch(() => { setEraDetail(null); setMarketData(null) })
      .finally(() => setDetailLoading(false))
  }, [selectedEra])

  const handleSelectBlock = (block) => {
    setSelectedBlock(block)
    setExploreStep('eras')
  }

  const handleSelectEra = (era) => {
    setSelectedEra(era)
    setSelectedBlock(findBlock(era.id))
    setExploreStep('detail')
  }

  return (
    <div className="vintage-explorer">
      <header className="vintage-header">
        <div className="vintage-header-left">
          <h1 className="hp-nav-title" onClick={onGoHome}>Fashion Resale Tool</h1>
          <div className="nav-toggle">
            <button className="nav-toggle-btn" onClick={onSwitchToDashboard}>
              Trend Forecast
            </button>
            <button className="nav-toggle-btn active">
              Vintage
            </button>
          </div>
        </div>
        <button className="logout-btn" onClick={logout}>Sign Out</button>
      </header>

      <div className="vintage-tabs">
        <button className="vintage-tab" onClick={onSwitchToClassify}>Classify</button>
        <button className="vintage-tab vintage-tab--active">Explore</button>
      </div>

      {exploreStep === 'blocks' && (
        <EraBlockGrid eras={eras} onSelectBlock={handleSelectBlock} />
      )}

      {exploreStep === 'eras' && selectedBlock && (
        <EraBlockEras
          block={selectedBlock}
          eras={eras}
          onBack={() => setExploreStep('blocks')}
          onSelectEra={handleSelectEra}
        />
      )}

      {exploreStep === 'detail' && (
        <div className="vintage-body">
          <EraSelector
            eras={eras}
            selectedEraId={selectedEra?.id}
            onSelect={handleSelectEra}
          />
          <main className="vintage-panel">
            <button
              className="era-detail-back-btn"
              onClick={() => setExploreStep(selectedBlock ? 'eras' : 'blocks')}
            >
              ← {selectedBlock ? selectedBlock.label : 'All Eras'}
            </button>

            {!selectedEra ? (
              <div className="vintage-empty-state">
                <span className="vintage-empty-state-icon">🧵</span>
                <p>Select a time period to explore its fashion</p>
              </div>
            ) : detailLoading ? (
              <div className="vintage-empty-state">
                <p>Loading…</p>
              </div>
            ) : (
              <>
                <EraTrends
                  era={eraDetail}
                  marketData={marketData}
                  onTrack={handleTrackKeyword}
                  trackedKeywords={trackedKeywords}
                />
                <EraImageGrid eraId={selectedEra?.id} />
              </>
            )}
          </main>
        </div>
      )}

      <ChatBot
        ref={stellaRef}
        context={{ view: 'vintage', era: selectedEra?.label || null }}
      />

      {toast && (
        <div className="gc-toast">
          <span className="gc-toast-icon">✓</span>
          {toast}
        </div>
      )}
    </div>
  )
}
