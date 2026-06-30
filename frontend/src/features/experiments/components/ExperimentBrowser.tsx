import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
  type ColumnFiltersState,
} from '@tanstack/react-table'
import { Panel, Group, Separator } from 'react-resizable-panels'

import { ApiError } from '../../../api/client'
import {
  buildExperimentDownloadUrl,
  cancelExperiment,
  deleteExperiment,
  getExperimentDetail,
  listExperiments,
  retryExperiment,
} from '../../../api/experiments'
import type { TaskStatus, ExperimentTaskRead } from '../../../api/types'
import { Modal } from '../../../app/Modal'

const statusOrder: TaskStatus[] = [
  'PENDING',
  'RUNNING',
  'COMPLETED',
  'FAILED',
  'CANCELLED',
]

function parseUTC(value: string) {
  return new Date(value.endsWith('Z') ? value : value + 'Z')
}

function toLocalDateTime(value: string) {
  return parseUTC(value).toLocaleString()
}

function formatDuration(exp: ExperimentTaskRead) {
  const created = parseUTC(exp.created_at).getTime()
  const updated = parseUTC(exp.updated_at).getTime()
  const now = Date.now()

  let diffMs = 0
  let label = ''

  if (exp.status === 'COMPLETED') {
    diffMs = updated - created
  } else if (exp.status === 'RUNNING') {
    diffMs = now - updated
    label = 'running'
  } else if (exp.status === 'PENDING') {
    diffMs = now - created
    label = 'idle'
  } else if (exp.status === 'FAILED') {
    diffMs = updated - created
    label = 'failed'
  } else if (exp.status === 'CANCELLED') {
    diffMs = updated - created
    label = 'cancelled'
  }

  if (diffMs < 0) diffMs = 0

  const totalSecs = Math.floor(diffMs / 1000)
  const hours = Math.floor(totalSecs / 3600)
  const mins = Math.floor((totalSecs % 3600) / 60)
  const secs = totalSecs % 60

  let timeStr = ''
  if (hours > 0) {
    timeStr = `${hours}h ${mins}m ${secs}s`
  } else if (mins > 0) {
    timeStr = `${mins}m ${secs}s`
  } else {
    timeStr = `${secs}s`
  }

  return label ? `${timeStr} (${label})` : timeStr
}

export interface ExperimentBrowserProps {
  fixedStatus?: TaskStatus
  onSelectAction?: (experiment: ExperimentTaskRead) => void
  isItemDisabled?: (experiment: ExperimentTaskRead) => boolean
  selectActionLabel?: string
  showActions?: boolean
}

const columnHelper = createColumnHelper<ExperimentTaskRead>()

export function ExperimentBrowser({
  fixedStatus,
  onSelectAction,
  isItemDisabled,
  selectActionLabel = 'Select',
  showActions = true,
}: ExperimentBrowserProps) {
  const queryClient = useQueryClient()

  const [sorting, setSorting] = useState<SortingState>([{ id: 'id', desc: true }])
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])
  const [globalFilter, setGlobalFilter] = useState('')

  // Selected Experiment Inspector State
  const [detailExpId, setDetailExpId] = useState<number | null>(null)

  // Local state to tick every second so running/pending durations increment smoothly
  const [, setTick] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => setTick(t => t + 1), 1000)
    return () => clearInterval(timer)
  }, [])
  
  // Dialog Modals States
  const [expToDelete, setExpToDelete] = useState<number | null>(null)
  const [expToCancel, setExpToCancel] = useState<number | null>(null)

  // 1. Fetch Experiment Lists
  const {
    data: experiments = [],
    isLoading,
    isFetching,
    error,
    refetch,
  } = useQuery({
    queryKey: ['experiments', 'list', fixedStatus],
    queryFn: listExperiments,
    refetchInterval: 5000,
  })

  // 2. Fetch Detail for Inspector
  const detailQuery = useQuery({
    queryKey: ['experiments', 'detail', detailExpId],
    queryFn: () => {
      if (detailExpId === null) throw new Error('No selected experiment')
      return getExperimentDetail(detailExpId)
    },
    enabled: detailExpId !== null,
  })

  // Mutations
  const retryMutation = useMutation({
    mutationFn: (id: number) => retryExperiment(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['experiments'] }),
  })

  const cancelMutation = useMutation({
    mutationFn: (id: number) => cancelExperiment(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
      setExpToCancel(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteExperiment(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
      setExpToDelete(null)
      setDetailExpId(null) // Close inspector if deleted
    },
  })

  const columns = useMemo(() => [
    columnHelper.accessor('id', {
      header: 'ID',
      cell: info => <code>#{info.getValue()}</code>,
      size: 70,
    }),
    columnHelper.accessor('name', {
      header: 'Experiment Name',
      cell: info => <span style={{ fontWeight: '600' }}>{info.getValue()}</span>,
      size: 160,
    }),
    columnHelper.accessor('status', {
      header: 'Status',
      cell: info => {
        const val = info.getValue()
        return (
          <span className={`status-badge status-${val.toLowerCase()}`}>
            {val}
          </span>
        )
      },
      size: 100,
    }),
    columnHelper.display({
      id: 'duration',
      header: 'Duration',
      cell: info => {
        const exp = info.row.original
        return (
          <span style={{ fontSize: '12px', color: 'var(--text-main)', fontFamily: 'monospace' }}>
            {formatDuration(exp)}
          </span>
        )
      },
      size: 130,
    }),
    columnHelper.display({
      id: 'progress',
      header: 'Progress (Jobs)',
      cell: info => {
        const row = info.row.original
        const completed = row.completed_jobs
        const total = row.total_jobs
        const pct = total > 0 ? Math.round((completed / total) * 100) : 0
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', width: '100%', paddingRight: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', fontWeight: '500' }}>
              <span>{completed}/{total}</span>
              <span>{pct}%</span>
            </div>
            <div style={{
              height: '6px',
              borderRadius: '3px',
              background: 'var(--bg-input-alt)',
              border: '1px solid var(--border-muted)',
              overflow: 'hidden',
              position: 'relative',
            }}>
              <div style={{
                height: '100%',
                width: `${pct}%`,
                background: row.status === 'FAILED' ? '#ef4444' : row.status === 'CANCELLED' ? '#f59e0b' : '#3b82f6',
                borderRadius: '3px',
                transition: 'width 0.4s ease',
              }} />
            </div>
          </div>
        )
      },
      size: 140,
    }),
    columnHelper.accessor('created_at', {
      header: 'Submitted',
      cell: info => parseUTC(info.getValue()).toLocaleDateString(),
      size: 100,
    }),
    columnHelper.display({
      id: 'actions',
      header: 'Actions',
      cell: info => {
        const exp = info.row.original
        const disabled = isItemDisabled?.(exp) ?? false
        const canRetry = ['FAILED', 'CANCELLED', 'RUNNING'].includes(exp.status)
        const canCancel = ['PENDING', 'RUNNING'].includes(exp.status)
        const canDownload = exp.status === 'COMPLETED'
        const busy = retryMutation.isPending || cancelMutation.isPending || deleteMutation.isPending

        return (
          <div className="row-actions" onClick={e => e.stopPropagation()}>
            {onSelectAction && (
              <button
                type="button"
                className={`btn btn-row ${disabled ? 'btn-disabled' : ''}`}
                style={{ background: '#3b82f6', color: 'white', border: 'none' }}
                disabled={disabled}
                onClick={() => onSelectAction(exp)}
              >
                {disabled ? 'Imported' : selectActionLabel}
              </button>
            )}
            <button
              type="button"
              className="btn btn-row"
              style={{
                background: detailExpId === exp.id ? 'var(--border-muted)' : undefined,
                fontWeight: detailExpId === exp.id ? '700' : '400',
              }}
              onClick={() => setDetailExpId(detailExpId === exp.id ? null : exp.id)}
            >
              Details
            </button>
            {showActions && (
              <>
                <button
                  type="button"
                  className="btn btn-row"
                  disabled={!canRetry || busy}
                  onClick={() => retryMutation.mutate(exp.id)}
                >
                  Retry
                </button>
                {canCancel ? (
                  <button
                    type="button"
                    className="btn btn-row"
                    style={{ color: '#f59e0b' }}
                    disabled={busy}
                    onClick={() => setExpToCancel(exp.id)}
                  >
                    Cancel
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn btn-row"
                    style={{ color: '#ef4444' }}
                    disabled={busy}
                    onClick={() => setExpToDelete(exp.id)}
                  >
                    Delete
                  </button>
                )}
                <a
                  className={`btn btn-row ${canDownload ? '' : 'btn-disabled'}`}
                  href={canDownload ? buildExperimentDownloadUrl(exp.id) : undefined}
                  onClick={e => !canDownload && e.preventDefault()}
                >
                  Download
                </a>
              </>
            )}
          </div>
        )
      },
      size: 260,
    }),
  ], [isItemDisabled, onSelectAction, selectActionLabel, showActions, retryMutation, cancelMutation, deleteMutation, detailExpId])

  const table = useReactTable({
    data: experiments,
    columns,
    state: {
      sorting,
      columnFilters,
      globalFilter,
    },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    columnResizeMode: 'onChange',
  })

  const expNames = useMemo(() => Array.from(new Set(experiments.map(e => e.name))).sort(), [experiments])

  const mutationError = retryMutation.error ?? cancelMutation.error ?? deleteMutation.error

  return (
    <div className="tasks-panel" style={{ height: '100%', border: 'none', background: 'transparent', padding: 0, display: 'flex', flexDirection: 'column' }}>
      
      {/* 1. Header (Spans across full div) */}
      <header className="tasks-header">
        <div>
          <p>{table.getFilteredRowModel().rows.length} experiment(s) listed</p>
        </div>
        <div className="tasks-header-actions" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button type="button" className="btn" onClick={() => refetch()} disabled={isFetching}>
            {isFetching ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </header>

      {/* 2. Filters (Spans across full div) */}
      <div className="tasks-filters" style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '16px' }}>
        {!fixedStatus && (
          <label>
            Status
            <select
              value={(table.getColumn('status')?.getFilterValue() as string) ?? 'all'}
              onChange={e => table.getColumn('status')?.setFilterValue(e.target.value === 'all' ? undefined : e.target.value)}
            >
              <option value="all">All</option>
              {statusOrder.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        )}

        <label>
          Name Filter
          <select
            value={(table.getColumn('name')?.getFilterValue() as string) ?? 'all'}
            onChange={e => table.getColumn('name')?.setFilterValue(e.target.value === 'all' ? undefined : e.target.value)}
          >
            <option value="all">All</option>
            {expNames.map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>

        <label className="search-input-wrap">
          Search
          <input
            type="text"
            value={globalFilter ?? ''}
            onChange={e => setGlobalFilter(e.target.value)}
            placeholder="Search experiment names or hashes..."
          />
        </label>
      </div>

      {mutationError && (
        <div className="tasks-error" style={{ marginBottom: '16px' }}>
          Action failed: {mutationError instanceof ApiError ? mutationError.message : 'Connection failed.'}
        </div>
      )}
      {error && (
        <div className="tasks-error" style={{ marginBottom: '16px' }}>
          Failed to list experiments: {error instanceof ApiError ? error.message : 'Server Connection Refused. Please ensure the backend server is running at http://localhost:8000.'}
        </div>
      )}

      {/* 3. Resizable Panel Splitter Layout */}
      <Group orientation="horizontal" style={{ flex: 1, minHeight: 0, display: 'flex', gap: '4px' }}>
        
        {/* Left Panel: Table List (Removed extra box styles so it spans naturally) */}
        <Panel id="list-panel" defaultSize={60} minSize={30} style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="tasks-table-wrap" style={{ flex: 1, overflow: 'auto', height: '100%' }}>
            <table className="tasks-table" style={{ width: '100%', minWidth: table.getCenterTotalSize() }}>
              <thead>
                {table.getHeaderGroups().map(headerGroup => (
                  <tr key={headerGroup.id}>
                    {headerGroup.headers.map(header => (
                      <th
                        key={header.id}
                        style={{ width: header.getSize(), position: 'relative' }}
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        <div style={{ cursor: header.column.getCanSort() ? 'pointer' : 'default', userSelect: 'none', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {{
                            asc: ' 🔼',
                            desc: ' 🔽',
                          }[header.column.getIsSorted() as string] ?? null}
                        </div>
                        {header.column.getCanResize() && (
                          <div
                            onMouseDown={header.getResizeHandler()}
                            onTouchStart={header.getResizeHandler()}
                            className={`resizer ${header.column.getIsResizing() ? 'isResizing' : ''}`}
                          />
                        )}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.length === 0 ? (
                  <tr>
                    <td colSpan={columns.length} className="tasks-empty">
                      {isLoading ? 'Scanning experiments...' : 'No historical experiments found.'}
                    </td>
                  </tr>
                ) : (
                  table.getRowModel().rows.map(row => {
                    const disabled = isItemDisabled?.(row.original) ?? false
                    const isSelected = detailExpId === row.original.id
                    return (
                      <tr
                        key={row.id}
                        onDoubleClick={() => {
                          if (onSelectAction) {
                            if (!disabled) onSelectAction(row.original)
                          } else {
                            setDetailExpId(isSelected ? null : row.original.id)
                          }
                        }}
                        style={{
                          cursor: 'pointer',
                          background: isSelected ? 'rgba(59, 130, 246, 0.05)' : undefined,
                          borderLeft: isSelected ? '3px solid #3b82f6' : undefined,
                          opacity: disabled ? 0.5 : 1,
                        }}
                      >
                        {row.getVisibleCells().map(cell => (
                          <td key={cell.id} style={{ width: cell.column.getSize() }}>
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        ))}
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </Panel>

        {/* Resizable Draggable Handle */}
        {detailExpId !== null && (
          <Separator style={{
            width: '8px',
            cursor: 'col-resize',
            background: 'transparent',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            position: 'relative',
          }}>
            <div className="panel-resize-handle" style={{
              width: '4px',
              height: '40px',
              borderRadius: '2px',
              background: 'var(--border-muted)',
              transition: 'background 0.2s',
            }} />
          </Separator>
        )}

        {/* Right Box: Dynamic Experiment Inspector Details */}
        {detailExpId !== null && (
          <Panel id="inspector-panel" defaultSize={40} minSize={25} style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              background: 'var(--bg-card)',
              border: '1px solid var(--border-muted)',
              borderRadius: '8px',
              padding: '16px',
              overflow: 'hidden',
              position: 'relative',
              gap: '16px',
            }}>
              
              {/* Close Handle */}
              <button 
                type="button" 
                onClick={() => setDetailExpId(null)}
                style={{
                  position: 'absolute',
                  top: '16px',
                  right: '16px',
                  border: 'none',
                  background: 'transparent',
                  fontSize: '20px',
                  cursor: 'pointer',
                  color: 'var(--text-muted)',
                  fontWeight: '600',
                  zIndex: 10,
                }}
                title="Close Inspector"
              >
                ×
              </button>

              {detailQuery.isLoading ? (
                <p style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>Retrieving details...</p>
              ) : detailQuery.data ? (
                <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: '16px', overflow: 'hidden' }}>
                  
                  {/* Inspector Header */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', paddingRight: '24px' }}>
                    <h3 style={{ margin: 0, textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                      <code>{detailQuery.data.name}</code>
                    </h3>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span className={`status-badge status-${detailQuery.data.status.toLowerCase()}`}>
                        {detailQuery.data.status}
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>ID: #{detailQuery.data.id}</span>
                    </div>
                  </div>

                  {detailQuery.data.error_message && (
                    <div className="tasks-error" style={{ margin: 0, padding: '10px', fontSize: '12px' }}>
                      <strong>Error:</strong> {detailQuery.data.error_message}
                    </div>
                  )}

                  {/* Summary grid */}
                  <div style={{
                    background: 'var(--bg-input-alt)',
                    border: '1px solid var(--border-muted)',
                    borderRadius: '6px',
                    padding: '10px 12px',
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr 1fr',
                    gap: '12px',
                  }}>
                    <div>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>Sub-jobs</span>
                      <span style={{ fontWeight: '700', fontSize: '14px' }}>{detailQuery.data.completed_jobs} / {detailQuery.data.total_jobs}</span>
                    </div>
                    <div>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>Submitted</span>
                      <span style={{ fontSize: '12px', fontWeight: '500' }}>{toLocalDateTime(detailQuery.data.created_at)}</span>
                    </div>
                    <div>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>Duration</span>
                      <span style={{ fontSize: '12px', fontWeight: '700', color: 'var(--accent-blue)' }}>{formatDuration(detailQuery.data)}</span>
                    </div>
                  </div>

                  {/* Inspector Stacked Details (optimized for panel widths) */}
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '16px', minHeight: 0, overflowY: 'auto', paddingRight: '4px' }}>
                    
                    {/* Config JSON */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      <label style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: '600', textTransform: 'uppercase' }}>Config spec</label>
                      <pre style={{
                        margin: 0,
                        background: 'var(--bg-input-alt)',
                        border: '1px solid var(--border-muted)',
                        borderRadius: '6px',
                        padding: '10px',
                        color: 'var(--text-main)',
                        fontSize: '11px',
                        lineHeight: '1.4',
                        maxHeight: '160px',
                        overflow: 'auto',
                        fontFamily: 'monospace',
                      }}>
                        {JSON.stringify(detailQuery.data.config, null, 2)}
                      </pre>
                    </div>

                    {/* Jobs grid status table */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1, minHeight: '180px' }}>
                      <label style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: '600', textTransform: 'uppercase' }}>Sub-jobs progress</label>
                      <div style={{
                        flex: 1,
                        background: 'var(--bg-input-alt)',
                        border: '1px solid var(--border-muted)',
                        borderRadius: '6px',
                        overflow: 'auto',
                      }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', textAlign: 'left' }}>
                          <thead style={{ background: 'var(--bg-input)', position: 'sticky', top: 0, borderBottom: '1px solid var(--border-muted)', zIndex: 2 }}>
                            <tr>
                              <th style={{ padding: '6px 8px' }}>Job ID</th>
                              <th style={{ padding: '6px 8px' }}>Status</th>
                              <th style={{ padding: '6px 8px' }}>Error Rate</th>
                              <th style={{ padding: '6px 8px' }}>Time</th>
                            </tr>
                          </thead>
                          <tbody>
                            {detailQuery.data.jobs.length === 0 ? (
                              <tr>
                                <td colSpan={4} style={{ padding: '12px', textAlign: 'center', color: 'var(--text-muted)' }}>No jobs.</td>
                              </tr>
                            ) : detailQuery.data.jobs.map(job => (
                              <tr key={job.id} style={{ borderBottom: '1px solid var(--border-muted)' }}>
                                <td style={{ padding: '6px 8px' }}><code>#{job.id}</code></td>
                                <td style={{ padding: '6px 8px' }}>
                                  <span className={`status-badge status-${job.status.toLowerCase()}`} style={{ fontSize: '9px', padding: '1px 4px' }}>
                                    {job.status}
                                  </span>
                                </td>
                                <td style={{ padding: '6px 8px' }}>
                                  {job.logical_error_rate !== null ? job.logical_error_rate.toFixed(5) : '-'}
                                </td>
                                <td style={{ padding: '6px 8px' }}>
                                  {job.time_total_s !== null ? `${job.time_total_s.toFixed(2)}s` : '-'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <p style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>Failed to load details.</p>
              )}
            </div>
          </Panel>
        )}
      </Group>

      {/* Delete Confirmation Modal */}
      <Modal title="Confirm Deletion" isOpen={expToDelete !== null} onClose={() => setExpToDelete(null)}>
        <div className="confirmation-dialog">
          <p>Permanently delete experiment <strong>#{expToDelete}</strong>? This action is irreversible.</p>
          <div className="modal-actions" style={{ marginTop: '20px', display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
            <button type="button" className="btn" onClick={() => setExpToDelete(null)}>Cancel</button>
            <button
              type="button"
              className="btn"
              style={{ background: '#ef4444', color: 'white', border: 'none' }}
              onClick={() => expToDelete && deleteMutation.mutate(expToDelete)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? 'Deleting...' : 'Confirm Delete'}
            </button>
          </div>
        </div>
      </Modal>

      {/* Cancel Confirmation Modal */}
      <Modal title="Confirm Cancellation" isOpen={expToCancel !== null} onClose={() => setExpToCancel(null)}>
        <div className="confirmation-dialog">
          <p>Cancel active sweep execution for experiment <strong>#{expToCancel}</strong>? All running/pending sub-jobs will be stopped.</p>
          <div className="modal-actions" style={{ marginTop: '20px', display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
            <button type="button" className="btn" onClick={() => setExpToCancel(null)}>Go Back</button>
            <button
              type="button"
              className="btn"
              style={{ background: '#f59e0b', color: 'white', border: 'none' }}
              onClick={() => expToCancel && cancelMutation.mutate(expToCancel)}
              disabled={cancelMutation.isPending}
            >
              {cancelMutation.isPending ? 'Stopping sweep...' : 'Confirm Cancel'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
