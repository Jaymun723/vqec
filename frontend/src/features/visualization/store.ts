import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import type { VisualizationTabState, ExperimentLayer, SweepAxisSignature, ComparisonConfig } from './types'

interface VisualizationStore {
  tabs: VisualizationTabState[]
  theme: 'dark' | 'light'
  
  // App-wide
  toggleTheme: () => void
  
  // Tab Management
  addTab: (tabId: string, title: string) => void
  removeTab: (tabId: string) => void
  renameTab: (tabId: string, title: string) => void
  
  // Layer Management
  addLayers: (tabId: string, layers: ExperimentLayer[], taskId: number, axisSignature: SweepAxisSignature) => void
  removeLayer: (tabId: string, layerId: string) => void
  updateLayer: (tabId: string, layerId: string, updates: Partial<ExperimentLayer>) => void
  reorderLayers: (tabId: string, startIndex: number, endIndex: number) => void
  
  // Comparison Management
  updateComparison: (tabId: string, comparisonId: string, updates: Partial<ComparisonConfig>) => void
  syncComparisons: (tabId: string) => void
  
  // Settings Management
  updateSettings: (tabId: string, updates: Partial<VisualizationTabState>) => void
}

const DEFAULT_PHYSICAL_BASELINE = {
  t1Us: 1000,
  t2StarUs: 50,
  roundTimeUs: 1,
  comparisonRounds: 10,
}

const COLORS = [
  '#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316',
]

/**
 * Ensures all pairwise combinations of layers exist as comparisons.
 */
function syncComparisons(layers: ExperimentLayer[], existing: ComparisonConfig[]): ComparisonConfig[] {
  const next: ComparisonConfig[] = []
  
  for (let i = 0; i < layers.length; i++) {
    for (let j = i + 1; j < layers.length; j++) {
      const a = layers[i]
      const b = layers[j]
      const id = `comp-${a.id}-${b.id}`
      
      const found = existing.find(c => c.id === id)
      if (found) {
        next.push(found)
      } else {
        next.push({
          id,
          layerAId: a.id,
          layerBId: b.id,
          thresholds: [1.0],
          visible: true,
          color: COLORS[next.length % COLORS.length]
        })
      }
    }
  }
  return next
}

export const useVisualizationStore = create<VisualizationStore>()(
  persist(
    (set) => ({
      tabs: [],
      theme: 'dark',

      toggleTheme: () => set((state) => ({ 
        theme: state.theme === 'dark' ? 'light' : 'dark' 
      })),

      addTab: (tabId, title) => set((state) => ({
        tabs: [
          ...state.tabs,
          {
            tabId,
            title,
            importedSweepTaskIds: [],
            axisSignature: null,
            xAxisName: null,
            yAxisName: null,
            sliceValues: {},
            layers: [],
            comparisons: [],
            includePhysicalBaseline: false,
            physicalBaseline: DEFAULT_PHYSICAL_BASELINE,
            sidebarWidth: 20,
          },
        ],
      })),

      removeTab: (tabId) => set((state) => ({
        tabs: state.tabs.filter((t) => t.tabId !== tabId),
      })),

      renameTab: (tabId, title) => set((state) => ({
        tabs: state.tabs.map((t) => (t.tabId === tabId ? { ...t, title } : t)),
      })),

      addLayers: (tabId, newLayers, taskId, axisSignature) => set((state) => ({
        tabs: state.tabs.map((t) => {
          if (t.tabId !== tabId) return t
          const currentLayers = t.layers ?? []
          const allLayers = [...currentLayers, ...newLayers]
          
          const multiValueAxes = axisSignature.axisNames.filter(
            name => (axisSignature.axisValues[name]?.length ?? 0) > 1
          )

          const xAxisName = t.xAxisName || multiValueAxes[0] || axisSignature.axisNames[0] || null
          const yAxisName = t.yAxisName || (multiValueAxes.length > 1 ? multiValueAxes[1] : null)
          
          const sliceValues = { ...t.sliceValues }
          axisSignature.axisNames.forEach(name => {
            if (sliceValues[name] === undefined) {
              sliceValues[name] = axisSignature.axisValues[name][0]
            }
          })

          return {
            ...t,
            layers: allLayers,
            comparisons: syncComparisons(allLayers, t.comparisons ?? []),
            importedSweepTaskIds: [...(t.importedSweepTaskIds ?? []), taskId],
            axisSignature: t.axisSignature || axisSignature,
            xAxisName,
            yAxisName,
            sliceValues,
          }
        }),
      })),

      removeLayer: (tabId, layerId) => set((state) => ({
        tabs: state.tabs.map((t) => {
          if (t.tabId !== tabId) return t
          const currentLayers = t.layers ?? []
          const remainingLayers = currentLayers.filter((l) => l.id !== layerId)
          const remainingTaskIds = Array.from(new Set(remainingLayers.map((l) => l.sourceTaskId)))
          
          return {
            ...t,
            layers: remainingLayers,
            comparisons: syncComparisons(remainingLayers, t.comparisons ?? []),
            importedSweepTaskIds: remainingTaskIds,
            axisSignature: remainingLayers.length === 0 ? null : t.axisSignature,
          }
        }),
      })),

      updateLayer: (tabId, layerId, updates) => set((state) => ({
        tabs: state.tabs.map((t) => {
          if (t.tabId !== tabId) return t
          return {
            ...t,
            layers: (t.layers ?? []).map((l) => (l.id === layerId ? { ...l, ...updates } : l)),
          }
        }),
      })),

      reorderLayers: (tabId, startIndex, endIndex) => set((state) => ({
        tabs: state.tabs.map((t) => {
          if (t.tabId !== tabId) return t
          const newLayers = Array.from(t.layers ?? [])
          const [removed] = newLayers.splice(startIndex, 1)
          newLayers.splice(endIndex, 0, removed)
          
          return {
            ...t,
            layers: newLayers,
            comparisons: syncComparisons(newLayers, t.comparisons ?? [])
          }
        })
      })),

      updateComparison: (tabId, comparisonId, updates) => set((state) => ({
        tabs: state.tabs.map((t) => {
          if (t.tabId !== tabId) return t
          return {
            ...t,
            comparisons: (t.comparisons ?? []).map(c => c.id === comparisonId ? { ...c, ...updates } : c)
          }
        })
      })),

      syncComparisons: (tabId) => set((state) => ({
        tabs: state.tabs.map((t) => {
          if (t.tabId !== tabId) return t
          const layers = t.layers ?? []
          
          let axisSignature = t.axisSignature
          let sliceValues = t.sliceValues || {}

          // Repair legacy axisSignature if axisValues is missing
          if (axisSignature && !axisSignature.axisValues && layers.length > 0) {
            const values: Record<string, Set<number>> = {}
            axisSignature.axisNames.forEach(name => values[name] = new Set())
            
            layers.forEach(l => {
              l.data.forEach(d => {
                axisSignature!.axisNames.forEach(name => {
                  if (d.params[name] !== undefined) values[name].add(d.params[name])
                })
              })
            })

            const repairedAxisValues = Object.fromEntries(
              Object.entries(values).map(([name, set]) => [name, Array.from(set).sort((a, b) => a - b)])
            )

            axisSignature = {
              ...axisSignature,
              axisValues: repairedAxisValues
            }

            // Initialize sliceValues from repaired axisValues if needed
            axisSignature.axisNames.forEach(name => {
              if (sliceValues[name] === undefined) {
                sliceValues[name] = repairedAxisValues[name][0]
              }
            })
          }

          return {
            ...t,
            axisSignature,
            sliceValues,
            comparisons: syncComparisons(layers, t.comparisons ?? [])
          }
        })
      })),

      updateSettings: (tabId, updates) => set((state) => ({
        tabs: state.tabs.map((t) => (t.tabId === tabId ? { ...t, ...updates } : t)),
      })),
    }),
    {
      name: 'vqec-visualization-storage',
      storage: createJSONStorage(() => localStorage),
    }
  )
)
