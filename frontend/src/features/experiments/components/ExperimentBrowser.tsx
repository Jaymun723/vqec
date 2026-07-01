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
  'IN_FLIGHT',
  'DONE',
  'ERROR',
  'CANCELLED',
]

function parseUTC(value: string) {
  return new Date(value.endsWith('Z') ? value : value + 'Z')
}

function toLocalDateTime(value: string) {
  return parseUTC(value).toLocaleString()
}

function formatAge(exp: ExperimentTaskRead) {
  const created = parseUTC(exp.submitted_at).getTime()
  const now = Date.now()
  let diffMs = now - created
  if (diffMs < 0) diffMs = 0

  const totalSecs = Math.floor(diffMs / 1000)
  const hours = Math.floor(totalSecs / 3600)
  const mins = Math.floor((totalSecs % 3600) / 60)
  const secs = totalSecs % 60

  if (hours > 0) {
    return `${hours}h ${mins}m ago`
  } else if (mins > 0) {
    return `${mins}m ${secs}s ago`
  } else {
    return `${secs}s ago`
  }
}

function formatDuration(startStr: string, endStr: string | null | undefined) {
  if (!endStr) return null;
  const start = parseUTC(startStr).getTime()
  const end = parseUTC(endStr).getTime()
  let diffMs = end - start
  if (diffMs < 0) diffMs = 0

  const totalSecs = Math.floor(diffMs / 1000)
  const hours = Math.floor(totalSecs / 3600)
  const mins = Math.floor((totalSecs % 3600) / 60)
  const secs = totalSecs % 60

  if (hours > 0) return `${hours}h ${mins}m ${secs}s`
  if (mins > 0) return `${mins}m ${secs}s`
  return `${secs}s`
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

  // Local state to tick every second so age increments smoothly
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
      size: 200,
    }),
    columnHelper.accessor('status', {
      header: 'Status',
      cell: info => {
        const val = info.getValue()
        const exp = info.row.original
        
        let progressElem = null
        if (val === 'IN_FLIGHT' && exp.jobs_total != null && exp.jobs_total > 0) {
          const done = exp.jobs_done ?? 0
          const total = exp.jobs_total
          const percentage = Math.round((done / total) * 100)
          progressElem = (
            <div style={{ marginTop: '4px', width: '100%', background: 'var(--bg-card)', border: '1px solid var(--border-muted)', borderRadius: '2px', height: '6px', overflow: 'hidden' }}>
              <div style={{ width: `${percentage}%`, height: '100%', background: '#3b82f6', transition: 'width 0.3s' }} />
            </div>
          )
        }

        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: '0' }}>
            <span className={`status-badge status-${val.toLowerCase()}`} style={{ alignSelf: 'flex-start' }}>
              {val === 'IN_FLIGHT' && exp.jobs_total != null && exp.jobs_total > 0
                ? `${val} (${Math.round(((exp.jobs_done ?? 0) / exp.jobs_total) * 100)}%)`
                : val}
            </span>
            {progressElem}
          </div>
        )
      },
      size: 140,
    }),
    columnHelper.accessor('submitted_at', {
      header: 'Submitted',
      cell: info => {
        const exp = info.row.original
        const d = parseUTC(info.getValue())
        const day = d.getDate().toString().padStart(2, '0')
        const month = (d.getMonth() + 1).toString().padStart(2, '0')
        const hours = d.getHours().toString().padStart(2, '0')
        const mins = d.getMinutes().toString().padStart(2, '0')
        
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <span style={{ fontSize: '13px' }}>
              {day}/{month} {hours}:{mins}
            </span>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              ({formatAge(exp)})
            </span>
          </div>
        )
      },
      size: 160,
    }),
    columnHelper.display({
      id: 'duration',
      header: 'Duration',
      cell: info => {
        const exp = info.row.original
        const duration = formatDuration(exp.submitted_at, exp.completed_at)
        return (
          <span style={{ fontSize: '12px', color: 'var(--text-main)' }}>
            {duration ? duration : (exp.status === 'IN_FLIGHT' ? 'Running...' : '-')}
          </span>
        )
      },
      size: 100,
    }),
    columnHelper.display({
      id: 'actions',
      header: 'Actions',
      cell: info => {
        const exp = info.row.original
        const disabled = isItemDisabled?.(exp) ?? false
        const canRetry = ['ERROR', 'CANCELLED'].includes(exp.status)
        const canCancel = ['IN_FLIGHT'].includes(exp.status)
        const canDownload = exp.status === 'DONE' && exp.result_path !== null
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
        
        {/* Left Panel: Table List */}
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

                  {detailQuery.data.error && (
                    <div className="tasks-error" style={{ margin: 0, padding: '10px', fontSize: '12px' }}>
                      <strong>Error:</strong> {detailQuery.data.error}
                    </div>
                  )}

                  {/* Summary grid */}
                  <div style={{
                    background: 'var(--bg-input-alt)',
                    border: '1px solid var(--border-muted)',
                    borderRadius: '6px',
                    padding: '10px 12px',
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: '12px',
                  }}>
                    <div>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>Submitted</span>
                      <span style={{ fontSize: '12px', fontWeight: '500' }}>{toLocalDateTime(detailQuery.data.submitted_at)}</span>
                    </div>
                    {detailQuery.data.completed_at && (
                      <div>
                        <span style={{ fontSize: '10px', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>Duration</span>
                        <span style={{ fontSize: '12px', fontWeight: '500' }}>{formatDuration(detailQuery.data.submitted_at, detailQuery.data.completed_at)}</span>
                      </div>
                    )}
                    <div style={{ gridColumn: detailQuery.data.completed_at ? '1 / -1' : undefined }}>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>Config Hash</span>
                      <span style={{ fontSize: '12px', fontWeight: '700', color: 'var(--accent-blue)', wordBreak: 'break-all' }}>{detailQuery.data.config_hash}</span>
                    </div>
                    {detailQuery.data.status === 'IN_FLIGHT' && detailQuery.data.jobs_total != null && detailQuery.data.jobs_total > 0 && (
                      <div style={{ gridColumn: '1 / -1' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                          <span>Execution Progress</span>
                          <span>{detailQuery.data.jobs_done ?? 0} / {detailQuery.data.jobs_total} jobs completed</span>
                        </div>
                        <div style={{ width: '100%', background: 'var(--bg-input)', borderRadius: '4px', height: '8px', overflow: 'hidden' }}>
                          <div style={{ width: `${((detailQuery.data.jobs_done ?? 0) / detailQuery.data.jobs_total) * 100}%`, height: '100%', background: '#3b82f6', transition: 'width 0.3s' }} />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Inspector Stacked Details */}
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
                        overflow: 'auto',
                        fontFamily: 'monospace',
                      }}>
                        {JSON.stringify(detailQuery.data.config, null, 2)}
                      </pre>
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
          <p>Cancel active sweep execution for experiment <strong>#{expToCancel}</strong>?</p>
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
