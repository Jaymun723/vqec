import type { DataPoint, ExperimentLayer } from '../types'

export interface GridData {
  x: number[]
  y: number[]
  z: number[][]
}

/**
 * Filters data points based on sliceValues for all axes except X and Y.
 */
export function filterLayerData(
  data: DataPoint[],
  sliceValues: Record<string, number>,
  xAxisName: string,
  yAxisName: string | null
): DataPoint[] {
  return data.filter((d) => {
    for (const [key, value] of Object.entries(sliceValues)) {
      if (key === xAxisName || key === yAxisName) continue
      if (d.params[key] !== value) return false
    }
    return true
  })
}

/**
 * Normalizes a list of data points into a 2D grid based on specified X and Y axis names.
 */
export function layerToGrid(
  layer: ExperimentLayer,
  xAxisName: string,
  yAxisName: string,
  metric: 'lepr' | 'errorRate' = 'lepr'
): GridData {
  const xValues = Array.from(new Set(layer.data.map((d) => d.params[xAxisName]))).sort((a, b) => a - b)
  const yValues = Array.from(new Set(layer.data.map((d) => d.params[yAxisName]))).sort((a, b) => a - b)

  // Pre-index data points for O(1) lookup
  const index = new Map<string, number>()
  layer.data.forEach((d) => {
    const key = `${d.params[xAxisName]}|${d.params[yAxisName]}`
    index.set(key, metric === 'lepr' ? d.lepr : d.errorRate)
  })

  const z: number[][] = yValues.map((y) => {
    return xValues.map((x) => {
      const val = index.get(`${x}|${y}`)
      return val !== undefined ? val : NaN
    })
  })

  return { x: xValues, y: yValues, z }
}

/**
 * Computes the ratio of metrics between two grids.
 */
export function computeRatioGrid(gridA: GridData, gridB: GridData, log: boolean): GridData {
  const z: number[][] = gridA.z.map((row, i) => {
    return row.map((valA, j) => {
      const valB = gridB.z[i][j]
      if (isNaN(valA) || isNaN(valB) || valB === 0) return NaN

      if (log) {
        if (valA == 0) {
          return -Infinity
        }
        return Math.log10(valA / valB)
      }
      return valA / valB
    })
  })

  return { x: gridA.x, y: gridA.y, z }
}

export const nanMin = (values: number[]) => {
  let min = NaN
  for (let i = 0; i < values.length; i++) {
    if (!Number.isFinite(values[i])) {
      continue
    }
    if (
      !Number.isNaN(values[i]) &&
      (Number.isNaN(min) || (!Number.isNaN(min) && min > values[i]))) {
        min = values[i]
    }
  }
  return min
}

export const nanMax = (values: number[]) => {
  let max = values[0]
  for (let i = 1; i < values.length; i++) {
    if (
      !Number.isNaN(values[i]) &&
      (Number.isNaN(max) || (!Number.isNaN(max) && max < values[i]))) {
        max = values[i]
    }
  }
  return max
}

