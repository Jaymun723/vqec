import { NavLink, Route, Routes, Navigate } from 'react-router-dom'
import type { TabDefinition, TabId } from './types'
import { useVisualizationStore } from '../features/visualization/store'

interface TabLayoutProps {
  tabs: TabDefinition[]
  onCloseTab: (tabId: TabId) => void
  onAddTab: () => void
}

export function TabLayout({
  tabs,
  onCloseTab,
  onAddTab,
}: TabLayoutProps) {
  const { theme, toggleTheme } = useVisualizationStore()

  return (
    <div className="tabs-shell">
      <nav className="tabs-bar" aria-label="Main tabs">
        <div style={{ display: 'flex', gap: '6px' }}>
          {tabs.map((tab) => {
            return (
              <NavLink
                key={tab.id}
                to={tab.path}
                className={({ isActive }) => 
                  `tab-chip ${tab.pinned ? 'pinned' : ''} ${isActive ? 'active' : ''}`
                }
                style={{ textDecoration: 'none', border: 'none', appearance: 'none' }}
              >
                {tab.title}
                {!tab.pinned && (
                  <span
                    role="button"
                    tabIndex={0}
                    className="tab-close"
                    aria-label={`Close ${tab.title}`}
                    onClick={(event) => {
                      event.preventDefault()
                      event.stopPropagation()
                      onCloseTab(tab.id)
                    }}
                    onKeyDown={(event) => {
                      if (event.key !== 'Enter' && event.key !== ' ') {
                        return
                      }
                      event.preventDefault()
                      event.stopPropagation()
                      onCloseTab(tab.id)
                    }}
                  >
                    ×
                  </span>
                )}
              </NavLink>
            )
          })}
          <button
            type="button"
            className="tab-chip"
            style={{ borderRadius: '10px 10px 0 0', padding: '9px 15px', fontWeight: 'bold' }}
            onClick={onAddTab}
            title="Add new visualization tab"
          >
            +
          </button>
        </div>

        <div className="brand" style={{ paddingBottom: '4px', paddingRight: '12px' }}>
          <button 
            type="button" 
            className="theme-toggle" 
            onClick={toggleTheme}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          >
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
          <span className="brand-title">VQEC</span>
          <span className="brand-subtitle">Desktop web client</span>
        </div>
      </nav>
      <main className="tab-content">
        <Routes>
          {tabs.map(tab => (
            <Route key={tab.id} path={tab.path} element={tab.content} />
          ))}
          {/* Fallback if route matches nothing in current tabs (e.g. after closure) */}
          <Route path="*" element={<Navigate to="/experiments" replace />} />
        </Routes>
      </main>
    </div>
  )
}
