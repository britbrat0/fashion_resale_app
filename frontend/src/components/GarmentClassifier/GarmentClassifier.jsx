import { useState, useEffect, useRef, useCallback } from 'react'
import { useAuth } from '../../hooks/useAuth'
import api from '../../services/api'
import ChatBot from '../ChatBot'
import './GarmentClassifier.css'

const DESCRIPTOR_LABELS = {
  fabrics: 'Fabrics',
  prints: 'Prints',
  silhouettes: 'Silhouettes',
  brands: 'Brands',
  colors: 'Colors',
  aesthetics: 'Aesthetics',
  key_garments: 'Key Garments',
  hardware: 'Hardware & Closures',
  embellishments: 'Embellishments',
  labels: 'Labels',
}

// Options not derived from era_data.json — hardcoded domain knowledge
const STATIC_OPTIONS = {
  hardware: [
    'Metal zipper', 'Plastic zipper', 'Invisible zipper', 'Exposed zipper',
    'Metal buttons', 'Plastic buttons', 'Shank buttons', 'Horn buttons',
    'Pearl / shell buttons', 'Toggle buttons', 'Snap buttons',
    'Hook and eye', 'Hook and bar', 'Lacing / corset closure', 'Drawstring', 'Velcro',
    'Buckle', 'D-ring', 'Grommets', 'Rivets',
    'Brass hardware', 'Gold-tone hardware', 'Silver-tone hardware', 'Shoulder pads',
    'Full elastic waist', 'Partial elastic waist', 'Elastic cuffs', 'Elastic hem',
    'Exposed elastic', 'Smocking', 'Shirring', 'Boning / stays', 'Underwire',
  ],
  embellishments: [
    'Sequins', 'Paillettes', 'Beading', 'Seed beads', 'Bugle beads',
    'Rhinestones', 'Crystal embellishment', 'Pearls', 'Metallic thread', 'Lurex',
    'Embroidery', 'Appliqué', 'Broderie anglaise / cutwork',
    'Smocking', 'Pintucks', 'Pleating', 'Ruching', 'Ruffles',
    'Lace trim', 'Fringe', 'Tassels', 'Feather trim', 'Fur trim',
    'Ribbon trim', 'Passementerie / braid trim', 'Pom-poms',
    'Studs / spikes', 'Safety pins', 'Patches', 'Bows',
  ],
  labels: [
    'ILGWU', 'ACWA', 'Union Made', 'Lot # label', 'RN # label', 'WPL # label',
    'No care label', 'Care label present', 'No content label', 'Content label present', 'Two-digit date code',
    'Talon zipper', 'Crown zipper', 'Scovill zipper',
    'Made in USA', 'Made in Japan', 'Made in Hong Kong', 'Made in England',
    'Woven label', 'Printed label', 'Chain stitch construction',
  ],
}

const MAX_IMAGES = 10
const MAX_HISTORY = 20
const getHistoryKey = (email) => email ? `gc_history_${email}` : 'gc_history_guest'

const LIFECYCLE_CONFIG = {
  'Emerging':     { label: 'Emerging',    color: '#4fc3f7', bg: 'rgba(79,195,247,0.1)'  },
  'Accelerating': { label: 'Accelerating',color: '#66bb6a', bg: 'rgba(102,187,106,0.1)' },
  'Peak':         { label: 'Peak Demand', color: '#ffa726', bg: 'rgba(255,167,38,0.1)'  },
  'Saturation':   { label: 'Saturating',  color: '#ff7043', bg: 'rgba(255,112,67,0.1)'  },
  'Decline':      { label: 'Declining',   color: '#ef5350', bg: 'rgba(239,83,80,0.1)'   },
  'Dormant':      { label: 'Dormant',     color: '#666',    bg: 'rgba(255,255,255,0.05)'},
  'Revival':      { label: 'Reviving',    color: '#ab47bc', bg: 'rgba(171,71,188,0.1)'  },
}

function getLifecycleStyle(stage) {
  if (!stage) return null
  if (LIFECYCLE_CONFIG[stage]) return LIFECYCLE_CONFIG[stage]
  for (const [key, cfg] of Object.entries(LIFECYCLE_CONFIG)) {
    if (stage.toLowerCase().includes(key.toLowerCase())) return cfg
  }
  return { label: stage, color: '#888', bg: 'rgba(255,255,255,0.05)' }
}

const makeThumbnail = (file) =>
  new Promise((resolve) => {
    const img = new Image()
    const url = URL.createObjectURL(file)
    img.onload = () => {
      const canvas = document.createElement('canvas')
      const size = 56
      canvas.width = size
      canvas.height = size
      const ctx = canvas.getContext('2d')
      const min = Math.min(img.naturalWidth, img.naturalHeight)
      ctx.drawImage(img, (img.naturalWidth - min) / 2, (img.naturalHeight - min) / 2, min, min, 0, 0, size, size)
      URL.revokeObjectURL(url)
      resolve(canvas.toDataURL('image/jpeg', 0.6))
    }
    img.onerror = () => { URL.revokeObjectURL(url); resolve(null) }
    img.src = url
  })

function decadeFromEraId(eraId) {
  if (!eraId) return null
  // "early-1990s", "late-1970s", "1920s", "1700-1749" → extract last 4-digit year group
  const m = eraId.match(/(\d{4})/)
  if (!m) return null
  const year = parseInt(m[1])
  return `${Math.floor(year / 10) * 10}s`
}

function relativeTime(ts) {
  const diff = Math.floor((Date.now() - ts) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`
  return new Date(ts).toLocaleDateString()
}

function loadHistory(key) {
  try { return JSON.parse(localStorage.getItem(key) || '[]') }
  catch { return [] }
}

function saveHistory(key, entries) {
  localStorage.setItem(key, JSON.stringify(entries))
}

export default function GarmentClassifier({ onGoHome, onSwitchToDashboard, onSwitchToVintage, onExploreEra }) {
  const { logout, isAuthenticated, email, openSignIn } = useAuth()
  const stellaRef = useRef(null)

  // Descriptor chip state
  const [options, setOptions] = useState({})
  const [selected, setSelected] = useState({
    fabrics: [], prints: [], silhouettes: [], brands: [],
    colors: [], aesthetics: [], key_garments: [],
    hardware: [], embellishments: [], labels: [],
  })
  const [customInputs, setCustomInputs] = useState({
    fabrics: '', prints: '', silhouettes: '', brands: '',
    colors: '', aesthetics: '', key_garments: '',
    hardware: '', embellishments: '', labels: '',
  })

  // Accordion expand state (all collapsed by default)
  const [expanded, setExpanded] = useState(
    Object.fromEntries(Object.keys(DESCRIPTOR_LABELS).map(k => [k, false]))
  )

  // Per-category search filter
  const [search, setSearch] = useState(
    Object.fromEntries(Object.keys(DESCRIPTOR_LABELS).map(k => [k, '']))
  )

  const toggleExpanded = (cat) =>
    setExpanded(prev => ({ ...prev, [cat]: !prev[cat] }))

  // Notes
  const [notes, setNotes] = useState('')

  // Images
  const [images, setImages] = useState([])
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef(null)

  // Results
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [resultThumbnail, setResultThumbnail] = useState(null)
  const [marketData, setMarketData] = useState(null)
  const [eraDetail, setEraDetail] = useState(null)
  const [etsyListings, setEtsyListings] = useState(null)
  const [etsyQuery, setEtsyQuery] = useState(null)
  const [error, setError] = useState(null)
  const [resultSource, setResultSource] = useState(null) // 'classify' | 'history'
  const resultsPanelRef = useRef(null)

  // Keyword tracking
  const [trackedKeywords, setTrackedKeywords] = useState(new Set())
  const [trackingSet, setTrackingSet] = useState(new Set())

  // Toast
  const [toast, setToast] = useState(null)
  const toastTimerRef = useRef(null)

  // History
  const [history, setHistory] = useState([])

  // Load descriptor options, history, and tracked keywords on mount
  useEffect(() => {
    api.get('/vintage/descriptor-options')
      .then(res => setOptions({ ...res.data, ...STATIC_OPTIONS }))
      .catch(() => setOptions(STATIC_OPTIONS))
    setHistory(loadHistory(getHistoryKey(email)))
    api.get('/trends/keywords/list')
      .then(res => setTrackedKeywords(new Set((res.data.keywords || []).map(k => k.keyword))))
      .catch(() => {})
  }, [])

  const toggleChip = (category, value) => {
    setSelected(prev => {
      const current = prev[category]
      return {
        ...prev,
        [category]: current.includes(value)
          ? current.filter(v => v !== value)
          : [...current, value],
      }
    })
  }

  const addCustomTerm = (category) => {
    const term = customInputs[category].trim()
    if (!term) return
    setOptions(prev => ({
      ...prev,
      [category]: prev[category] ? [...new Set([...prev[category], term])] : [term],
    }))
    setSelected(prev => ({
      ...prev,
      [category]: prev[category].includes(term) ? prev[category] : [...prev[category], term],
    }))
    setCustomInputs(prev => ({ ...prev, [category]: '' }))
  }

  const handleAddImages = useCallback((files) => {
    const toAdd = Array.from(files).slice(0, MAX_IMAGES - images.length)
    toAdd.forEach(file => {
      const preview = URL.createObjectURL(file)
      setImages(prev => prev.length < MAX_IMAGES ? [...prev, { file, preview }] : prev)
    })
  }, [images.length])

  const removeImage = (index) => {
    setImages(prev => {
      URL.revokeObjectURL(prev[index].preview)
      return prev.filter((_, i) => i !== index)
    })
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    handleAddImages(e.dataTransfer.files)
  }

  const hasInput = () => {
    const anyChip = Object.values(selected).some(arr => arr.length > 0)
    return anyChip || notes.trim() || images.length > 0
  }

  const showToast = (msg) => {
    setToast(msg)
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    toastTimerRef.current = setTimeout(() => setToast(null), 3000)
  }

  const handleTrackKeyword = async (kw) => {
    if (!isAuthenticated) { openSignIn('Sign in to track keywords on Trend Forecast'); return }
    if (trackedKeywords.has(kw) || trackingSet.has(kw)) return
    setTrackingSet(prev => new Set([...prev, kw]))
    try {
      await api.post(`/trends/keywords/${encodeURIComponent(kw)}/track`)
      setTrackedKeywords(prev => new Set([...prev, kw]))
      showToast(`Now tracking "${kw}" on Trend Forecast`)
    } catch {}
    setTrackingSet(prev => { const s = new Set(prev); s.delete(kw); return s })
  }

  const handleClear = () => {
    setResult(null)
    setResultThumbnail(null)
    setMarketData(null)
    setEraDetail(null)
    setEtsyListings(null)
    setEtsyQuery(null)
    setError(null)
    setResultSource(null)
    setNotes('')
    setSelected(Object.fromEntries(Object.keys(DESCRIPTOR_LABELS).map(k => [k, []])))
    setSearch(Object.fromEntries(Object.keys(DESCRIPTOR_LABELS).map(k => [k, ''])))
    setImages(prev => { prev.forEach(img => URL.revokeObjectURL(img.preview)); return [] })
  }

  const handleClassify = async () => {
    if (!hasInput()) return
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const formData = new FormData()
      formData.append('fabrics', JSON.stringify(selected.fabrics))
      formData.append('prints', JSON.stringify(selected.prints))
      formData.append('silhouettes', JSON.stringify(selected.silhouettes))
      formData.append('brands', JSON.stringify(selected.brands))
      formData.append('colors', JSON.stringify(selected.colors))
      formData.append('aesthetics', JSON.stringify(selected.aesthetics))
      formData.append('key_garments', JSON.stringify(selected.key_garments))
      formData.append('hardware', JSON.stringify(selected.hardware))
      formData.append('embellishments', JSON.stringify(selected.embellishments))
      formData.append('labels', JSON.stringify(selected.labels))
      formData.append('notes', notes)
      images.forEach(({ file }, i) => formData.append(`image_${i}`, file))

      const res = await api.post('/vintage/classify', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const classifyResult = res.data.result
      setResult(classifyResult)

      // Generate thumbnail from first image
      let thumbnail = null
      if (images.length > 0) {
        thumbnail = await makeThumbnail(images[0].file).catch(() => null)
        setResultThumbnail(thumbnail)
      }

      // Fetch era detail, market data, and Etsy listings in parallel
      let eraDetailData = null
      let marketDataData = null
      let etsyData = null
      const primaryEraId = classifyResult.primary_era?.id
      const topKeyword = classifyResult.related_keywords?.[0]
      const decade = decadeFromEraId(primaryEraId)
      const etsyQuery = (() => {
        if (!topKeyword) return null
        const prefix = [decade, 'vintage'].filter(Boolean)
        const kwWords = topKeyword.split(/\s+/)
        const seen = new Set(prefix.map(w => w.toLowerCase()))
        const deduped = kwWords.filter(w => {
          const lw = w.toLowerCase()
          if (seen.has(lw)) return false
          seen.add(lw)
          return true
        })
        return [...prefix, ...deduped].join(' ')
      })()
      const fetches = []
      if (primaryEraId) {
        fetches.push(
          api.get(`/vintage/eras/${encodeURIComponent(primaryEraId)}`),
          api.get(`/vintage/eras/${encodeURIComponent(primaryEraId)}/market`),
        )
      }
      if (etsyQuery) {
        fetches.push(api.get(`/vintage/etsy-listings?q=${encodeURIComponent(etsyQuery)}`))
      }
      try {
        const results = await Promise.all(fetches)
        let i = 0
        if (primaryEraId) {
          eraDetailData = results[i++].data
          marketDataData = results[i++].data
          setEraDetail(eraDetailData)
          setMarketData(marketDataData)
        }
        if (etsyQuery) {
          etsyData = results[i].data.listings || []
          setEtsyListings(etsyData)
          setEtsyQuery(etsyQuery)
        }
      } catch {}

      // Background: collect Etsy validation samples for this era (fire and forget, auth required)
      if (primaryEraId && isAuthenticated) {
        api.post(`/vintage/validation/collect-era?era_id=${encodeURIComponent(primaryEraId)}&target=5`)
          .catch(() => {})
      }

      // Build descriptor summary: first 6 selected chips across all categories
      const allChips = Object.values(selected).flat()
      if (notes.trim()) allChips.push(notes.trim().slice(0, 40))
      const entry = {
        id: Date.now(),
        timestamp: Date.now(),
        chips: allChips.slice(0, 6),
        imageCount: images.length,
        thumbnail,
        result: classifyResult,
        eraDetail: eraDetailData,
        marketData: marketDataData,
        etsyListings: etsyData,
        etsyQuery: etsyQuery || null,
        // era_accuracy lives inside classifyResult already
      }
      const updated = [entry, ...history].slice(0, MAX_HISTORY)
      setHistory(updated)
      saveHistory(getHistoryKey(email), updated)
      setResultSource('classify')
    } catch (err) {
      setError(err.response?.data?.detail || 'Classification failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const deleteHistoryEntry = (id) => {
    const updated = history.filter(e => e.id !== id)
    setHistory(updated)
    saveHistory(getHistoryKey(email), updated)
  }

  const clearHistory = () => {
    setHistory([])
    saveHistory(getHistoryKey(email), [])
  }

  // Scroll to top whenever loading starts or a result appears
  useEffect(() => {
    if (result || loading) {
      window.scrollTo({ top: 0, behavior: 'instant' })
      resultsPanelRef.current?.scrollTo({ top: 0, behavior: 'instant' })
    }
  }, [result, loading])

  const confidencePct = (val) => Math.round((val || 0) * 100)

  return (
    <div className="gc-root">
      <header className="vintage-header">
        <div className="vintage-header-left">
          <div className="nav-logo-wrap" onClick={onGoHome}>
            <img src="/ratatat-logo.jpg" alt="ratadat" className="nav-logo" />
          </div>
          <div className="nav-toggle">
            <button className="nav-toggle-btn" onClick={onSwitchToDashboard}>
              Trend Forecast
              {isAuthenticated && trackedKeywords.size > 0 && (
                <span className="nav-toggle-badge">{trackedKeywords.size}</span>
              )}
            </button>
            <button className="nav-toggle-btn active">Vintage</button>
          </div>
        </div>
        {isAuthenticated
          ? <button className="logout-btn" onClick={logout}>Sign Out</button>
          : <button className="logout-btn" onClick={openSignIn}>Sign In</button>
        }
      </header>

      <div className="vintage-tabs">
        <button className="vintage-tab vintage-tab--active">Classify</button>
        <button className="vintage-tab" onClick={onSwitchToVintage}>Explore</button>
      </div>

      <div className="gc-intro">
        <p className="gc-intro-text">
          Identify the fashion era of any vintage garment. Select descriptors that match what you observe — fabrics, silhouettes, prints, hardware, labels — and optionally upload photos. The classifier will analyze your inputs and return a primary era match with confidence score and reasoning, plus two alternate era suggestions.
        </p>
      </div>

      <div className="gc-layout">
        {/* ── Left: Input Form ── */}
        <aside className="gc-form-panel">
          <h2 className="gc-panel-title">Describe the Garment</h2>

          {/* Descriptor chip groups — accordion */}
          {Object.keys(DESCRIPTOR_LABELS).map(cat => {
            const isOpen = expanded[cat]
            const count = selected[cat].length
            const q = search[cat].toLowerCase()
            const filtered = (options[cat] || []).filter(v =>
              v.toLowerCase().includes(q)
            )
            return (
              <div className="gc-chip-group" key={cat}>
                <button
                  className="gc-chip-group-header"
                  onClick={() => toggleExpanded(cat)}
                  type="button"
                >
                  <span className="gc-chip-group-title">{DESCRIPTOR_LABELS[cat]}</span>
                  <div className="gc-chip-group-header-right">
                    {count > 0 && <span className="gc-selected-badge">{count}</span>}
                    <span className={`gc-chevron${isOpen ? ' open' : ''}`}>›</span>
                  </div>
                </button>

                {isOpen && (
                  <div className="gc-chip-group-body">
                    <input
                      className="gc-search-input"
                      placeholder={`Search ${DESCRIPTOR_LABELS[cat].toLowerCase()}…`}
                      value={search[cat]}
                      onChange={e => setSearch(prev => ({ ...prev, [cat]: e.target.value }))}
                      onKeyDown={e => {
                        if (e.key === 'Enter') {
                          const term = search[cat].trim()
                          if (term && !(options[cat] || []).some(v => v.toLowerCase() === term.toLowerCase())) {
                            setOptions(prev => ({ ...prev, [cat]: [...new Set([...(prev[cat] || []), term])] }))
                            setSelected(prev => ({ ...prev, [cat]: prev[cat].includes(term) ? prev[cat] : [...prev[cat], term] }))
                            setSearch(prev => ({ ...prev, [cat]: '' }))
                          }
                        }
                      }}
                    />
                    <div className="gc-chips">
                      {filtered.map(val => (
                        <button
                          key={val}
                          className={`gc-chip${selected[cat].includes(val) ? ' selected' : ''}`}
                          onClick={() => toggleChip(cat, val)}
                          type="button"
                        >
                          {val}
                        </button>
                      ))}
                      {search[cat].trim() && !(options[cat] || []).some(v => v.toLowerCase() === search[cat].trim().toLowerCase()) && (
                        <button
                          className="gc-chip gc-chip-add-new"
                          onClick={() => {
                            const term = search[cat].trim()
                            setOptions(prev => ({ ...prev, [cat]: [...new Set([...(prev[cat] || []), term])] }))
                            setSelected(prev => ({ ...prev, [cat]: prev[cat].includes(term) ? prev[cat] : [...prev[cat], term] }))
                            setSearch(prev => ({ ...prev, [cat]: '' }))
                          }}
                          type="button"
                        >
                          + Add "{search[cat].trim()}"
                        </button>
                      )}
                      {filtered.length === 0 && !search[cat].trim() && (
                        <span className="gc-no-results">No matches</span>
                      )}
                    </div>
                    <div className="gc-custom-input-row">
                      <input
                        className="gc-custom-input"
                        placeholder="Add custom…"
                        value={customInputs[cat]}
                        onChange={e => setCustomInputs(prev => ({ ...prev, [cat]: e.target.value }))}
                        onKeyDown={e => e.key === 'Enter' && addCustomTerm(cat)}
                      />
                      <button
                        className="gc-custom-add-btn"
                        onClick={() => addCustomTerm(cat)}
                        type="button"
                      >+</button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}

          {/* Notes */}
          <div className="gc-flat-group">
            <div className="gc-chip-group-label">Additional Notes</div>
            <textarea
              className="gc-notes"
              placeholder="Describe anything else: construction details, hardware, tags, provenance…"
              value={notes}
              onChange={e => setNotes(e.target.value)}
              rows={3}
            />
          </div>

          {/* Image upload */}
          <div className="gc-flat-group">
            <div className="gc-chip-group-label">Images (up to {MAX_IMAGES})</div>
            <div
              className={`gc-dropzone${dragOver ? ' drag-over' : ''}`}
              onDragOver={e => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => images.length < MAX_IMAGES && fileInputRef.current?.click()}
            >
              {images.length < MAX_IMAGES
                ? <span>Drag &amp; drop images here, or click to browse</span>
                : <span>Maximum {MAX_IMAGES} images reached</span>
              }
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                multiple
                style={{ display: 'none' }}
                onChange={e => handleAddImages(e.target.files)}
              />
            </div>
            {images.length > 0 && (
              <div className="gc-image-thumb-grid">
                {images.map(({ preview }, i) => (
                  <div className="gc-thumb" key={i}>
                    <img src={preview} alt={`Upload ${i + 1}`} />
                    <button
                      className="gc-thumb-remove"
                      onClick={() => removeImage(i)}
                      type="button"
                      aria-label="Remove image"
                    >✕</button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="gc-btn-row">
            <button
              className="gc-classify-btn"
              onClick={handleClassify}
              disabled={!hasInput() || loading}
              type="button"
            >
              {loading ? <span className="gc-spinner" /> : null}
              {loading ? 'Classifying…' : 'Classify Garment'}
            </button>
            {(result || hasInput()) && (
              <button
                className="gc-clear-btn"
                onClick={handleClear}
                disabled={loading}
                type="button"
              >
                Clear
              </button>
            )}
          </div>

          {error && <div className="gc-error">{error}</div>}
        </aside>

        {/* ── Right: Results + History ── */}
        <main className="gc-results-panel" ref={resultsPanelRef}>
          {!result && !loading && history.length === 0 && (
            <div className="gc-results-empty">
              <span className="gc-results-empty-icon">🧵</span>
              <p>Select descriptors or upload images, then click <strong>Classify Garment</strong></p>
            </div>
          )}

          {loading && (
            <div className="gc-results-loading">
              <div className="gc-spinner-lg" />
              <p>Analyzing garment…</p>
            </div>
          )}

          {result && !isAuthenticated && (
            <div className="guest-notice">
              <span>Results are session-only.</span>
              <button className="guest-notice__btn" onClick={openSignIn} type="button">Sign in to save →</button>
            </div>
          )}

          {result && (
            <div className="gc-results">
              <div className="gc-results-topbar">
                {resultSource === 'history' ? (
                  <button className="gc-clear-btn" onClick={handleClear} type="button">← History</button>
                ) : (
                  <div className="gc-clear-tooltip-wrap">
                    <button className="gc-clear-btn" onClick={handleClear} type="button">Clear</button>
                    <span className="gc-clear-tooltip">Result will be saved to History</span>
                  </div>
                )}
                {resultThumbnail && (
                  <img className="gc-result-thumb" src={resultThumbnail} alt="Uploaded garment" />
                )}
              </div>

              {/* ── 1. Primary era ── */}
              <div className="gc-result-card gc-primary-card">
                <div className="gc-result-card-header">
                  <div>
                    <div className="gc-era-label">{result.primary_era?.label}</div>
                    <div className="gc-confidence-label">
                      {confidencePct(result.primary_era?.confidence)}% confidence
                      {result.era_accuracy?.decade_accuracy != null && (
                        <span className="gc-verified-badge">
                          · {Math.round(result.era_accuracy.decade_accuracy * 100)}% verified
                          <span className="gc-verified-sub"> ({result.era_accuracy.samples} Etsy samples)</span>
                        </span>
                      )}
                    </div>
                  </div>
                  <button
                    className="gc-explore-btn"
                    onClick={() => onExploreEra(result.primary_era?.id)}
                    type="button"
                  >
                    Explore this era →
                  </button>
                </div>
                <div className="gc-confidence-bar-track">
                  <div className="gc-confidence-bar-fill" style={{ width: `${confidencePct(result.primary_era?.confidence)}%` }} />
                </div>
                <p className="gc-reasoning">{result.primary_era?.reasoning}</p>
              </div>

              {/* ── Matching features ── */}
              {result.matching_features?.length > 0 && (
                <div className="gc-result-card">
                  <div className="gc-section-label">Matching Features</div>
                  <div className="gc-chips gc-feature-chips">
                    {result.matching_features.map((f, i) => (
                      <span className="gc-chip selected" key={i}>{f}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* ── Market data ── */}
              {marketData && (
                <div className="gc-result-card gc-market-card">
                  <div className="gc-market-header">
                    <div className="gc-section-label">Market Data</div>
                    {marketData.lifecycle_stage && (() => {
                      const cfg = getLifecycleStyle(marketData.lifecycle_stage)
                      return (
                        <span className="gc-lifecycle-badge" style={{ color: cfg.color, background: cfg.bg, borderColor: cfg.color + '55' }}>
                          {cfg.label}{marketData.demand_score != null ? ` · ${marketData.demand_score}` : ''}
                        </span>
                      )
                    })()}
                  </div>

                  <div className="gc-price-stats-row">
                    {[
                      { label: 'Min', val: marketData.price_stats?.min },
                      { label: 'Avg', val: marketData.price_stats?.avg, highlight: true },
                      { label: 'Max', val: marketData.price_stats?.max },
                    ].map(({ label, val, highlight }) => (
                      <div key={label} className={`gc-price-stat${highlight ? ' gc-price-stat--avg' : ''}`}>
                        <span className="gc-price-stat-label">{label}</span>
                        <span className="gc-price-stat-value">{val != null ? `$${val.toFixed(2)}` : '—'}</span>
                      </div>
                    ))}
                    <div className="gc-price-stat gc-price-stat--muted">
                      <span className="gc-price-stat-label">Listings</span>
                      <span className="gc-price-stat-value">{marketData.price_stats?.count ?? '—'}</span>
                    </div>
                  </div>

                  <div className="gc-platform-row">
                    {['ebay', 'etsy', 'poshmark', 'depop'].map(p => {
                      const d = (marketData.by_platform || {})[p]
                      return (
                        <div key={p} className={`gc-platform-chip${d ? '' : ' gc-platform-chip--empty'}`}>
                          <span className="gc-platform-name">{p}</span>
                          <span className="gc-platform-price">{d ? `$${d.avg.toFixed(2)}` : '—'}</span>
                        </div>
                      )
                    })}
                  </div>

                  {!marketData.price_stats && Object.keys(marketData.by_platform || {}).length === 0 && (
                    <p className="gc-market-empty-note">
                      Price data populates as keywords matching this era are tracked in Trend Forecast.
                    </p>
                  )}
                </div>
              )}

              {/* ── Related Keywords ── */}
              {result.related_keywords?.length > 0 && (
                <div className="gc-result-card">
                  <div className="gc-section-label">Related Keywords</div>
                  <p className="gc-kw-hint">Track these to start collecting market data for this specific garment.</p>
                  <div className="gc-chips gc-feature-chips">
                    {result.related_keywords.map((kw, i) => {
                      const isTracked = trackedKeywords.has(kw)
                      const isTracking = trackingSet.has(kw)
                      return (
                        <button
                          key={i}
                          className={`gc-track-chip${isTracked ? ' gc-track-chip--tracked' : ''}${isTracking ? ' gc-track-chip--loading' : ''}`}
                          onClick={() => handleTrackKeyword(kw)}
                          disabled={isTracked || isTracking}
                          type="button"
                          title={isTracked ? 'Already tracking' : 'Click to track'}
                        >
                          {kw}
                          <span className="gc-track-chip-icon">
                            {isTracking ? '…' : isTracked ? '✓' : '+'}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* ── Buyers are searching for ── */}
              {eraDetail?.aesthetics?.length > 0 && (
                <div className="gc-result-card">
                  <div className="gc-section-label">Buyers Are Searching For</div>
                  <p className="gc-kw-hint">Click to track on Trend Forecast.</p>
                  <div className="gc-chips gc-feature-chips">
                    {eraDetail.aesthetics.map((a, i) => {
                      const isTracked = trackedKeywords.has(a)
                      const isTracking = trackingSet.has(a)
                      return (
                        <button
                          key={i}
                          className={`gc-track-chip${isTracked ? ' gc-track-chip--tracked' : ''}${isTracking ? ' gc-track-chip--loading' : ''}`}
                          onClick={() => handleTrackKeyword(a)}
                          disabled={isTracked || isTracking}
                          type="button"
                          title={isTracked ? 'Already tracking' : 'Click to track'}
                        >
                          {a}
                          <span className="gc-track-chip-icon">
                            {isTracking ? '…' : isTracked ? '✓' : '+'}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* ── Similar on Etsy ── */}
              {etsyQuery && (
                <div className="gc-result-card">
                  <div className="gc-etsy-header">
                    <div className="gc-section-label">Similar on Etsy</div>
                    <a
                      className="gc-etsy-search-link"
                      href={`https://www.etsy.com/search?q=${encodeURIComponent(etsyQuery)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Search: "{etsyQuery}" →
                    </a>
                  </div>
                  {etsyListings?.length > 0 ? (
                    <div className="gc-etsy-list">
                      {etsyListings.map((item, i) => (
                        <a
                          key={i}
                          className="gc-etsy-item"
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <span className="gc-etsy-title">{item.title}</span>
                          <span className="gc-etsy-price">
                            {item.price != null ? `$${item.price.toFixed(2)}` : '—'}
                          </span>
                        </a>
                      ))}
                    </div>
                  ) : (
                    <p className="gc-etsy-fallback">Click the search link above to browse live listings on Etsy.</p>
                  )}
                </div>
              )}

              {/* ── Alternate eras ── */}
              {result.alternate_eras?.length > 0 && (
                <div className="gc-result-card">
                  <div className="gc-section-label">Alternate Matches</div>
                  <div className="gc-alternates">
                    {result.alternate_eras.map((alt, i) => (
                      <div className="gc-alt-card" key={i}>
                        <div className="gc-alt-header">
                          <span className="gc-alt-label">{alt.label}</span>
                          <span className="gc-alt-confidence">{confidencePct(alt.confidence)}%</span>
                        </div>
                        <div className="gc-confidence-bar-track gc-alt-track">
                          <div className="gc-confidence-bar-fill gc-alt-fill" style={{ width: `${confidencePct(alt.confidence)}%` }} />
                        </div>
                        <p className="gc-alt-reasoning">{alt.reasoning}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── History ── */}
          {!result && history.length > 0 && (
            <div className="gc-history">
              {!isAuthenticated && (
                <div className="guest-notice">
                  <span>History is session-only.</span>
                  <button className="guest-notice__btn" onClick={openSignIn} type="button">Sign in to save →</button>
                </div>
              )}
              <div className="gc-history-header">
                <span className="gc-history-title">History</span>
                <button
                  className="gc-history-clear"
                  onClick={clearHistory}
                  type="button"
                >
                  Clear all
                </button>
              </div>
              <div className="gc-history-list">
                {history.map(entry => (
                  <div
                    className="gc-history-entry"
                    key={entry.id}
                    onClick={() => {
                      setResult(entry.result)
                      setResultThumbnail(entry.thumbnail || null)
                      setEraDetail(entry.eraDetail || null)
                      setMarketData(entry.marketData || null)
                      setEtsyListings(entry.etsyListings || null)
                      setEtsyQuery(entry.etsyQuery || null)
                      setResultSource('history')
                    }}
                    role="button"
                    tabIndex={0}
                    onKeyDown={e => e.key === 'Enter' && e.currentTarget.click()}
                  >
                    {entry.thumbnail && (
                      <img className="gc-history-thumb" src={entry.thumbnail} alt="" />
                    )}
                    <div className="gc-history-entry-top">
                      <div className="gc-history-era">
                        <span className="gc-history-era-label">
                          {entry.result.primary_era?.label}
                        </span>
                        <span className="gc-history-confidence">
                          {confidencePct(entry.result.primary_era?.confidence)}%
                        </span>
                      </div>
                      <div className="gc-history-actions">
                        <span className="gc-history-time">{relativeTime(entry.timestamp)}</span>
                        <button
                          className="gc-history-delete"
                          onClick={e => { e.stopPropagation(); deleteHistoryEntry(entry.id) }}
                          type="button"
                          aria-label="Remove"
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                    {entry.chips.length > 0 && (
                      <div className="gc-history-chips">
                        {entry.chips.map((c, i) => (
                          <span className="gc-history-chip" key={i}>{c}</span>
                        ))}
                        {entry.imageCount > 0 && (
                          <span className="gc-history-chip gc-history-chip-img">
                            {entry.imageCount} image{entry.imageCount > 1 ? 's' : ''}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </main>
      </div>
      <ChatBot
        ref={stellaRef}
        context={{ view: 'classify', classifyResult: result || null }}
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
