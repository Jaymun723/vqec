import { useState, useEffect, useMemo } from 'react'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Panel, Group, Separator } from 'react-resizable-panels'

import { buildExperimentDownloadUrl } from '../api/experiments'
import type { UnifiedTaskSummary } from '../api/types'
import { useParquetWorker } from '../features/visualization/hooks/useParquetWorker'
import {
  extractAxes,
  getAxisSignature,
  isCompatible,
  normalizeSweepToLayers,
} from '../features/visualization/utils/normalization'
import { Modal } from '../app/Modal'
import { ExperimentBrowser } from '../features/experiments/components/ExperimentBrowser'
import { useVisualizationStore } from '../features/visualization/store'
import { PlotEngine } from '../features/visualization/components/PlotEngine'
import type { ExperimentLayer } from '../features/visualization/types'

interface VisualizationTabProps {
  tabId: string
}

interface SortableLayerItemProps {
  layer: ExperimentLayer
  onRemove: (layerId: string) => void
  onUpdate: (layerId: string, updates: Partial<ExperimentLayer>) => void
}

function SortableLayerItem({ layer, onRemove, onUpdate }: SortableLayerItemProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: layer.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 1 : 0,
  }

  return (
    <div 
      ref={setNodeRef} 
      style={style} 
      className={`layer-item ${isDragging ? 'dragging' : ''}`}
    >
      <div 
        {...attributes} 
        {...listeners}
        style={{ cursor: 'grab', color: '#6a7184', padding: '0 4px', fontSize: '14px' }}
      >
        ⋮⋮
      </div>
      <input
        type="checkbox"
        checked={layer.visible}
        onChange={() => onUpdate(layer.id, { visible: !layer.visible })}
      />
      <input 
        type="color" 
        value={layer.color} 
        onChange={e => onUpdate(layer.id, { color: e.target.value })}
        style={{ width: '16px', height: '16px', border: 'none', padding: 0, background: 'transparent' }}
      />
      <input
        type="text"
        className="layer-label-input"
        value={layer.experimentLabel}
        onChange={e => onUpdate(layer.id, { experimentLabel: e.target.value })}
        style={{ 
          fontSize: '11px', 
          background: 'transparent', 
          color: 'inherit', 
          border: 'none',
          borderBottom: '1px solid transparent',
          padding: '2px 4px',
          flex: 1,
          minWidth: 0
        }}
        onFocus={e => e.target.style.borderBottomColor = '#3b82f6'}
        onBlur={e => e.target.style.borderBottomColor = 'transparent'}
      />
      <button type="button" className="tab-close" onClick={() => onRemove(layer.id)}>×</button>
    </div>
  )
}

export function VisualizationTab({ tabId }: VisualizationTabProps) {
  const vizTab = useVisualizationStore((s) => s.tabs.find((t) => t.tabId === tabId))
  const { 
    renameTab, addLayers, removeLayer, updateLayer, reorderLayers,
    updateSettings, updateComparison, syncComparisons
  } = useVisualizationStore()

  const [isModalOpen, setIsModalOpen] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)
  const [isParsing, setIsParsing] = useState(false)
  const [isEditingTitle, setIsEditingTitle] = useState(false)
  const [editedTitle, setEditedTitle] = useState(vizTab?.title || '')

  const { parseParquet } = useParquetWorker()

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event

    if (over && active.id !== over.id) {
      const oldIndex = layers.findIndex((l) => l.id === active.id)
      const newIndex = layers.findIndex((l) => l.id === over.id)
      reorderLayers(tabId, oldIndex, newIndex)
    }
  }

  // Ensure comparisons are synced on mount (handles legacy data)
  useEffect(() => {
    if (vizTab) {
      syncComparisons(tabId)
    }
  }, [])

  if (!vizTab) {
    return <div className="panel">Tab not found</div>
  }

  // Ensure arrays exist for old localstorage data
  const layers = vizTab.layers ?? []
  const comparisons = vizTab.comparisons ?? []

  const handleRenameSubmit = () => {
    renameTab(tabId, editedTitle)
    setIsEditingTitle(false)
  }

  const handleImport = async (task: UnifiedTaskSummary) => {
    setIsParsing(true)
    setImportError(null)
    setIsModalOpen(false)
    
    try {
      const url = buildExperimentDownloadUrl(task.id)
      const response = await fetch(url)
      if (!response.ok) throw new Error(`Failed to download task data: ${response.statusText}`)

      const buffer = await response.arrayBuffer()
      const rows = await parseParquet(buffer)

      if (rows.length === 0) throw new Error('Task result file is empty.')

      const { names, values } = extractAxes(rows)
      const sig = getAxisSignature(names, values)

      if (vizTab.axisSignature && !isCompatible(vizTab.axisSignature, sig)) {
        throw new Error(
          `Incompatible sweep axes. This tab already has axes: ${vizTab.axisSignature.axisNames.join(
            ', '
          )}`
        )
      }

      const newLayers = normalizeSweepToLayers(
        task.id,
        'sweep',
        `${task.name} (${task.config_hash.slice(0, 6)})`,
        rows,
        names,
        layers.length
      )

      addLayers(tabId, newLayers, task.id, sig)
    } catch (err) {
      setImportError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsParsing(false)
    }
  }

  const addThreshold = (compId: string) => {
    const val = prompt('Enter ratio threshold (e.g. 1.0, 0.5):')
    if (val === null) return
    const num = parseFloat(val)
    if (isNaN(num)) return

    const comp = comparisons.find(c => c.id === compId)
    if (comp) {
      updateComparison(tabId, compId, { thresholds: [...(comp.thresholds ?? []), num] })
    }
  }

  const removeThreshold = (compId: string, index: number) => {
    const comp = comparisons.find(c => c.id === compId)
    if (comp) {
      const next = [...(comp.thresholds ?? [])]
      next.splice(index, 1)
      updateComparison(tabId, compId, { thresholds: next })
    }
  }

  // Filter comparisons to only show those where both layers are visible
  const activeComparisons = useMemo(() => {
    return comparisons.filter(comp => {
      const layerA = layers.find(l => l.id === comp.layerAId)
      const layerB = layers.find(l => l.id === comp.layerBId)
      return layerA?.visible && layerB?.visible
    })
  }, [layers, comparisons])

  const isEmpty = layers.length === 0

  return (
    <section className="visualization-panel">
      {importError && (
        <div className="tasks-error" style={{ marginBottom: '16px' }}>
          {importError}
          <button 
            type="button" 
            className="tab-close" 
            onClick={() => setImportError(null)} 
            style={{ marginLeft: '12px', fontSize: '16px' }}
          >
            ×
          </button>
        </div>
      )}

      <Modal 
        title="Import Completed Sweep" 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)}
      >
        <ExperimentBrowser 
          fixedStatus="COMPLETED" 
          onSelectAction={handleImport}
          isItemDisabled={(exp) => (vizTab.importedSweepTaskIds ?? []).includes(exp.id)}
          selectActionLabel="Import this sweep"
          showActions={false}
        />
      </Modal>

      <Group orientation="horizontal" className="viz-layout" id="viz-panel-group">
        <Panel 
          id="sidebar-panel"
          defaultSize={`${typeof vizTab.sidebarWidth === 'number' ? vizTab.sidebarWidth : 20}%`} 
          minSize="15%" 
          onResize={(size) => updateSettings(tabId, { sidebarWidth: size.asPercentage })}
          className="viz-layers" 
          style={{ display: 'flex', flexDirection: 'column', gap: '20px', overflowY: 'auto' }}
        >
          <div className="viz-title-section">
            {isEditingTitle ? (
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <input 
                  type="text" 
                  value={editedTitle} 
                  onChange={e => setEditedTitle(e.target.value)}
                  onBlur={handleRenameSubmit}
                  onKeyDown={e => e.key === 'Enter' && handleRenameSubmit()}
                  autoFocus
                  style={{ width: '100%', fontSize: '16px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--accent-blue)', background: 'var(--bg-input-alt)', color: 'var(--text-main)' }}
                />
              </div>
            ) : (
              <h2 onClick={() => { setEditedTitle(vizTab.title); setIsEditingTitle(true); }} style={{ cursor: 'pointer', margin: 0, fontSize: '18px' }} title="Click to rename">
                {vizTab.title} ✎
              </h2>
            )}
            <div style={{ marginTop: '12px' }}>
              <button 
                type="button" 
                className="btn" 
                style={{ width: '100%', justifyContent: 'center' }}
                onClick={() => setIsModalOpen(true)}
              >
                Import Sweep
              </button>
              {isParsing && <div style={{ fontSize: '11px', color: '#8ec5ff', textAlign: 'center', marginTop: '4px' }}>Parsing data...</div>}
            </div>
          </div>

          {vizTab.axisSignature && (
            <div className="viz-axis-config">
              <h3>Axes</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '10px' }}>
                {(() => {
                  const { axisNames, axisValues = {} } = vizTab.axisSignature
                  const multiValueAxes = axisNames.filter(n => (axisValues[n]?.length ?? 0) > 1)
                  const singleValueAxes = axisNames.filter(n => (axisValues[n]?.length ?? 0) === 1)
                  const sliceAxes = multiValueAxes.filter(n => n !== vizTab.xAxisName && n !== vizTab.yAxisName)

                  return (
                    <>
                      {/* X Axis Selector */}
                      <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        X Axis
                        <select 
                          value={vizTab.xAxisName || ''} 
                          onChange={e => updateSettings(tabId, { xAxisName: e.target.value })}
                          style={{ background: 'var(--bg-input)', color: 'var(--text-main)', border: '1px solid var(--border-muted)', borderRadius: '4px', padding: '4px' }}
                        >
                          {multiValueAxes.map(name => <option key={name} value={name}>{name}</option>)}
                          {multiValueAxes.length === 0 && axisNames.map(name => <option key={name} value={name}>{name}</option>)}
                        </select>
                      </label>

                      {/* Y Axis Selector (conditional) */}
                      {multiValueAxes.length > 1 && (
                        <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          Y Axis (Heatmap)
                          <select 
                            value={vizTab.yAxisName || ''} 
                            onChange={e => updateSettings(tabId, { yAxisName: e.target.value })}
                            style={{ background: 'var(--bg-input)', color: 'var(--text-main)', border: '1px solid var(--border-muted)', borderRadius: '4px', padding: '4px' }}
                          >
                            <option value="">None (1D plot)</option>
                            {multiValueAxes.map(name => <option key={name} value={name}>{name}</option>)}
                          </select>
                        </label>
                      )}

                      {/* Hyper Slice Sliders */}
                      {sliceAxes.length > 0 && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '4px', padding: '8px', background: 'var(--bg-input-alt)', borderRadius: '4px' }}>
                          <span style={{ fontSize: '10px', fontWeight: 'bold', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Hyper Slices</span>
                          {sliceAxes.map(name => {
                            const values = axisValues[name]
                            const sliceValues = vizTab.sliceValues || {}
                            const currentVal = sliceValues[name] ?? values[0]
                            const currentIndex = values.indexOf(currentVal)
                            
                            return (
                              <label key={name} style={{ fontSize: '11px', color: 'var(--text-main)', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                  <span>{name.replace(/_/g, ' ')}</span>
                                  <span style={{ color: 'var(--accent-blue)', fontWeight: 'bold' }}>{currentVal}</span>
                                </div>
                                <input 
                                  type="range"
                                  min={0}
                                  max={values.length - 1}
                                  step={1}
                                  value={currentIndex >= 0 ? currentIndex : 0}
                                  onChange={e => {
                                    const nextVal = values[parseInt(e.target.value)]
                                    updateSettings(tabId, { sliceValues: { ...sliceValues, [name]: nextVal } })
                                  }}
                                  style={{ width: '100%', cursor: 'pointer' }}
                                />
                              </label>
                            )
                          })}
                        </div>
                      )}

                      {/* Fixed Axes */}
                      {singleValueAxes.length > 0 && (
                        <div style={{ marginTop: '4px' }}>
                          <span style={{ fontSize: '10px', fontWeight: 'bold', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Fixed Axes</span>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '4px' }}>
                            {singleValueAxes.map(name => (
                              <div key={name} style={{ fontSize: '10px', padding: '2px 6px', background: 'var(--bg-input)', borderRadius: '10px', border: '1px solid var(--border-muted)' }}>
                                {name}: {axisValues[name][0]}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )
                })()}
              </div>
            </div>
          )}

          <div className="viz-layers-section">
            <h3>Layers</h3>
            {isEmpty ? (
              <p style={{ fontSize: '12px', color: '#95a0ba', marginTop: '8px' }}>No data imported.</p>
            ) : (
              <div className="layers-list" style={{ marginTop: '10px' }}>
                <DndContext 
                  sensors={sensors}
                  collisionDetection={closestCenter}
                  onDragEnd={handleDragEnd}
                >
                  <SortableContext 
                    items={layers.map(l => l.id)}
                    strategy={verticalListSortingStrategy}
                  >
                    {layers.map((layer) => (
                      <SortableLayerItem 
                        key={layer.id} 
                        layer={layer} 
                        onRemove={(id) => removeLayer(tabId, id)}
                        onUpdate={(id, updates) => updateLayer(tabId, id, updates)}
                      />
                    ))}
                  </SortableContext>
                </DndContext>
              </div>
            )}
          </div>

          {activeComparisons.length > 0 && (
            <div className="viz-comparisons-section">
              <h3 style={{ marginBottom: '10px' }}>Comparisons</h3>
              <div className="layers-list">
                {activeComparisons.map((comp) => {
                  const layerA = layers.find(l => l.id === comp.layerAId)
                  const layerB = layers.find(l => l.id === comp.layerBId)
                  return (
                    <div key={comp.id} className="comp-item">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <input
                          type="checkbox"
                          checked={comp.visible}
                          onChange={() => updateComparison(tabId, comp.id, { visible: !comp.visible })}
                        />
                        <input 
                          type="color" 
                          value={comp.color} 
                          onChange={e => updateComparison(tabId, comp.id, { color: e.target.value })}
                          style={{ width: '16px', height: '16px', border: 'none', padding: 0, background: 'transparent' }}
                        />
                        <div 
                          style={{ fontSize: '11px', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                          title={`${layerA?.experimentLabel || '?'} / ${layerB?.experimentLabel || '?'}`}
                        >
                          {layerA?.experimentLabel || '?'} / {layerB?.experimentLabel || '?'}
                        </div>
                      </div>
                      
                      <div className="threshold-list">
                        {(comp.thresholds ?? []).map((t, idx) => (
                          <span key={idx} className="threshold-tag">
                            {t} <span style={{ cursor: 'pointer' }} onClick={() => removeThreshold(comp.id, idx)}>×</span>
                          </span>
                        ))}
                        <button type="button" className="threshold-add" onClick={() => addThreshold(comp.id)}>+</button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </Panel>

        <Separator className="resize-handle-outer">
          <div className="resize-handle-inner" />
        </Separator>

        <Panel id="plot-panel" minSize="30%" className="viz-content" style={{ overflow: 'hidden' }}>
          {isEmpty ? (
            <div style={{ textAlign: 'center', color: '#6a7184' }}>
              <div style={{ fontSize: '48px', marginBottom: '16px' }}>📊</div>
              <p>Import sweep data to start visualizing results.</p>
            </div>
          ) : (
            <PlotEngine state={{ ...vizTab, layers, comparisons }} />
          )}
        </Panel>
      </Group>
    </section>
  )
}
