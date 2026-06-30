import type { DataPoint, ExperimentLayer, SweepAxisSignature } from '../types'
import type { TaskType } from '../../../api/types'

function ensureNumber(val: any): number {
  if (typeof val === 'bigint') {
    return Number(val)
  }
  return Number(val)
}

export function computeLepr(errors: number, shots: number, rounds: number): number {
  if (shots === 0) return 0
  const errorRate = errors / shots
  const clampedRate = Math.min(Math.max(errorRate, 0), 0.5)
  // LEPR formula: 0.5 * (1 - (1 - 2*p_L)^(1/rounds))
  return 0.5 * (1 - Math.pow(1 - 2 * clampedRate, 1 / rounds))
}

export function extractAxes(rows: any[]): { names: string[]; values: Record<string, number[]> } {
  const allColumns = Object.keys(rows[0] || {})
  
  // Find all columns representing noise parameters (starting with noise_) and exclude non-numeric metadata
  const noiseColumns = allColumns.filter(c => c.startsWith('noise_') && c !== 'noise_type').sort()
  
  // Strip the 'noise_' prefix to expose clean axis names in the UI
  const cleanAxisNames = noiseColumns.map(c => c.replace(/^noise_/, ''))

  const values: Record<string, Set<number>> = {}
  cleanAxisNames.forEach((name) => {
    values[name] = new Set()
  })

  rows.forEach((row) => {
    cleanAxisNames.forEach((name) => {
      // Look up using the full prefixed column name
      values[name].add(ensureNumber(row['noise_' + name]))
    })
  })

  const sortedValues: Record<string, number[]> = {}
  cleanAxisNames.forEach((name) => {
    sortedValues[name] = Array.from(values[name]).sort((a, b) => a - b)
  })

  return { names: cleanAxisNames, values: sortedValues }
}

export function getAxisSignature(
  names: string[],
  values: Record<string, number[]>
): SweepAxisSignature {
  return {
    axisNames: names,
    axisValues: values,
    axisValueHashes: names.map((n) => values[n].join(',')),
  }
}

export function isCompatible(sig1: SweepAxisSignature, sig2: SweepAxisSignature): boolean {
  if (sig1.axisNames.length !== sig2.axisNames.length) return false
  for (let i = 0; i < sig1.axisNames.length; i++) {
    if (sig1.axisNames[i] !== sig2.axisNames[i]) return false
    if (sig1.axisValueHashes[i] !== sig2.axisValueHashes[i]) return false
  }
  return true
}

const COLORS = [
  '#3b82f6',
  '#ef4444',
  '#10b981',
  '#f59e0b',
  '#8b5cf6',
  '#ec4899',
  '#06b6d4',
  '#f97316',
]

export function normalizeSweepToLayers(
  taskId: number,
  taskType: TaskType,
  taskLabel: string,
  rows: any[],
  axisNames: string[],
  colorOffset: number = 0
): ExperimentLayer[] {
  const allColumns = Object.keys(rows[0] || {})
  
  // Find all non-noise parameter columns (circuit_, decoder_)
  const layerColumns = allColumns.filter(c => 
    (c.startsWith('circuit_') || c.startsWith('decoder_')) &&
    !['circuit_type', 'decoder_type'].includes(c)
  )

  // Sort so circuit_ columns appear first, then decoder_
  const circuitCols = layerColumns.filter(c => c.startsWith('circuit_')).sort()
  const decoderCols = layerColumns.filter(c => c.startsWith('decoder_')).sort()
  const sortedLayerCols = [...circuitCols, ...decoderCols]

  const groups: Record<string, any[]> = {}

  rows.forEach((row) => {
    // build a composite key joining the values of all sortedLayerCols
    const key = sortedLayerCols.map(col => String(row[col])).join('_')
    if (!groups[key]) groups[key] = []
    groups[key].push(row)
  })

  return Object.keys(groups).map((key, index) => {
    const groupRows = groups[key]
    const firstRow = groupRows[0]
    
    // Extract distance and rounds for structural metadata fallback checks
    const d = ensureNumber(firstRow.circuit_distance !== undefined ? firstRow.circuit_distance : 3)
    const r = ensureNumber(firstRow.circuit_rounds !== undefined ? firstRow.circuit_rounds : 3)
    const code = firstRow.circuit_type || 'unknown'
    const decoder = firstRow.decoder_type || 'unknown'

    // Format each parameter name and value into legend labels, stripping prefixes
    const labelParts = sortedLayerCols.map(col => {
      const cleanName = col.replace(/^(circuit_|decoder_|runner_)/, '')
      const value = firstRow[col]
      return `${cleanName}=${value}`
    })
    const experimentLabel = `${code}, ${labelParts.join(', ')}, ${decoder}`

    const data: DataPoint[] = groupRows.map((row) => {
      const params: Record<string, number> = {}
      axisNames.forEach((name) => {
        // Look up utilizing the full prefixed name, e.g. noise_p
        params[name] = ensureNumber(row['noise_' + name])
      })
      const errors = ensureNumber(row.n_errors !== undefined ? row.n_errors : 0)
      const shots = ensureNumber(row.shots || 1)
      return {
        params,
        lepr: computeLepr(errors, shots, r),
        errorRate: errors / shots,
        shots,
        errors,
      }
    })

    return {
      id: `task-${taskId}-${key}`,
      sourceTaskId: taskId,
      sourceTaskType: taskType,
      sourceLabel: taskLabel,
      experimentLabel,
      visible: true,
      color: COLORS[(colorOffset + index) % COLORS.length],
      distance: d,
      rounds: r,
      data,
    }
  })
}
