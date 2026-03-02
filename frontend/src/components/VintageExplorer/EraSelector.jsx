import { useState } from 'react'

const GROUPS = [
  {
    label: 'Historical',
    ids: ['1700-1749', '1750-1799', '1800-1824', '1825-1849', '1850-1874', '1875-1899'],
  },
  {
    label: 'Early Modern',
    ids: ['1900s', '1910s', '1920s', '1930s', '1940s', '1950s'],
  },
  {
    label: 'Contemporary Vintage',
    ids: [
      'early-1960s', 'late-1960s',
      'early-1970s', 'late-1970s',
      'early-1980s', 'late-1980s',
      'early-1990s', 'late-1990s',
      'early-2000s', 'late-2000s',
    ],
  },
]

export default function EraSelector({ eras, selectedEraId, onSelect }) {
  const [openGroups, setOpenGroups] = useState({ Historical: true, 'Early Modern': true, 'Contemporary Vintage': true })

  const eraMap = Object.fromEntries(eras.map(e => [e.id, e]))

  const toggleGroup = (label) => {
    setOpenGroups(prev => ({ ...prev, [label]: !prev[label] }))
  }

  return (
    <nav className="era-selector">
      {GROUPS.map(group => (
        <div key={group.label} className="era-group">
          <button
            className="era-group-header"
            onClick={() => toggleGroup(group.label)}
          >
            {group.label}
            <span className={`era-group-chevron ${openGroups[group.label] ? 'open' : ''}`}>▼</span>
          </button>
          {openGroups[group.label] && (
            <ul className="era-list">
              {group.ids.map(id => {
                const era = eraMap[id]
                if (!era) return null
                return (
                  <li key={id}>
                    <button
                      className={`era-list-btn ${selectedEraId === id ? 'selected' : ''}`}
                      onClick={() => onSelect(era)}
                    >
                      {era.label}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      ))}
    </nav>
  )
}
