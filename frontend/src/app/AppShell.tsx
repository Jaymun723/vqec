import { useEffect, useMemo } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'

import { TabLayout } from './TabLayout'
import type { TabDefinition, TabId } from './types'
import { ExperimentCreationTab } from '../tabs/ExperimentCreationTab'
import { ExperimentsTab } from '../tabs/ExperimentsTab'
import { VisualizationTab } from '../tabs/VisualizationTab'
import { useVisualizationStore } from '../features/visualization/store'

const PINNED_EXPERIMENTS_TAB_ID: TabId = 'pinned:experiments'
const PINNED_EXPERIMENT_CREATION_TAB_ID: TabId = 'pinned:experiment-creation'

export function AppShell() {
  const navigate = useNavigate()
  const location = useLocation()
  
  const { tabs: vizTabs, addTab, removeTab, theme } = useVisualizationStore()

  // Apply theme to document
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  // Recover dynamic tabs from URL on mount if possible
  useEffect(() => {
    if (location.pathname.startsWith('/visualization/')) {
      const id = location.pathname.split('/').pop() as string
      if (id && !vizTabs.some(t => t.tabId === id)) {
        addTab(id, 'Restored Tab')
      }
    }
  }, [])

  const tabs = useMemo<TabDefinition[]>(() => {
    const pinnedTabs: TabDefinition[] = [
      {
        id: PINNED_EXPERIMENTS_TAB_ID,
        title: 'Experiment list',
        pinned: true,
        path: '/experiments',
        content: <ExperimentsTab />,
      },
      {
        id: PINNED_EXPERIMENT_CREATION_TAB_ID,
        title: 'Experiment creation',
        pinned: true,
        path: '/experiment-creation',
        content: (
          <ExperimentCreationTab onOpenExperimentsTab={() => navigate('/experiments')} />
        ),
      },
    ]

    const dynamicTabs: TabDefinition[] = vizTabs.map((vizTab) => ({
      id: vizTab.tabId as TabId,
      title: vizTab.title,
      pinned: false,
      path: `/visualization/${vizTab.tabId}`,
      content: (
        <VisualizationTab
          tabId={vizTab.tabId}
        />
      ),
    }))

    return [...pinnedTabs, ...dynamicTabs]
  }, [vizTabs, navigate])

  const openVisualizationTab = () => {
    const nextCount = vizTabs.length + 1
    const newTabId = `viz-${crypto.randomUUID()}`
    addTab(newTabId, `Visualization ${nextCount}`)
    navigate(`/visualization/${newTabId}`)
  }

  const closeTab = (tabId: TabId) => {
    removeTab(tabId)
    if (location.pathname.includes(tabId)) {
      const remaining = vizTabs.filter(t => t.tabId !== tabId)
      const fallback = remaining.length > 0 ? `/visualization/${remaining.at(-1)?.tabId}` : '/experiments'
      navigate(fallback)
    }
  }

  return (
    <div className="app-shell">
      <TabLayout
        tabs={tabs}
        onCloseTab={closeTab}
        onAddTab={openVisualizationTab}
      />
    </div>
  )
}
