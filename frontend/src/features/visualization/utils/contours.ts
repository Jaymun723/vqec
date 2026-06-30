import { contours } from 'd3-contour'
import type { GridData } from './math'

export interface ContourPath {
  x: number[]
  y: number[]
}

/**
 * Extracts line segments for a specific threshold value using Marching Squares.
 * Maps grid indices back to actual axis values using linear interpolation.
 */
export function extractContourLines(
  grid: GridData,
  threshold: number
): ContourPath[] {
  const n = grid.x.length
  const m = grid.y.length
  
  if (n < 2 || m < 2) return []

  const flatData = new Float64Array(n * m)
  const isValid = new Uint8Array(n * m)
  let hasValidData = false

  for (let j = 0; j < m; j++) {
    for (let i = 0; i < n; i++) {
      const val = grid.z[j][i]
      if (!isNaN(val) && isFinite(val)) {
        flatData[i + j * n] = val
        isValid[i + j * n] = 1
        hasValidData = true
      } else {
        // Use a value below threshold to avoid fake crossings in empty zones
        flatData[i + j * n] = threshold - 1.0
        isValid[i + j * n] = 0
      }
    }
  }

  if (!hasValidData) return []

  const generator = contours().size([n, m])
  const multiPolygon = generator.contour(flatData as any, threshold)

  const segments: ContourPath[] = []

  multiPolygon.coordinates.forEach((polygon) => {
    polygon.forEach((ring) => {
      let currentX: number[] = []
      let currentY: number[] = []

      ring.forEach(([i, j]) => {
        // A point is fully supported if all 4 corners of its grid cell have data
        const gi = Math.floor(i)
        const gj = Math.floor(j)
        
        let fullySupported = true
        for (let di = 0; di <= 1; di++) {
          for (let dj = 0; dj <= 1; dj++) {
            const ni = gi + di
            const nj = gj + dj
            if (ni < 0 || ni >= n || nj < 0 || nj >= m || !isValid[ni + nj * n]) {
              fullySupported = false
              break
            }
          }
          if (!fullySupported) break
        }

        if (fullySupported) {
          // Additional check: prevent lines from hugging the very edge of the plot
          // d3-contour coordinates range from 0.5 (first point) to n-0.5 (last point)
          const isAtEdge = i < 0.6 || i > n - 0.6 || j < 0.6 || j > m - 0.6
          
          if (!isAtEdge) {
            currentX.push(interpolate(grid.x, i - 0.5))
            currentY.push(interpolate(grid.y, j - 0.5))
          } else {
            fullySupported = false // Treat as a break
          }
        }

        if (!fullySupported) {
          // Break segment and save if long enough
          if (currentX.length >= 10) {
            segments.push({ x: currentX, y: currentY })
          }
          currentX = []
          currentY = []
        }
      })

      // Handle last segment
      if (currentX.length >= 10) {
        segments.push({ x: currentX, y: currentY })
      }
    })
  })

  return segments
}

function interpolate(values: number[], index: number): number {
  const i0 = Math.max(0, Math.min(values.length - 2, Math.floor(index)))
  const i1 = i0 + 1
  const t = Math.max(0, Math.min(1, index - i0))
  
  const v0 = Math.log10(values[i0])
  const v1 = Math.log10(values[i1])
  return Math.pow(10, v0 + t * (v1 - v0))
}
