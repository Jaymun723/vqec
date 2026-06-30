import { describe, it, expect } from 'vitest'
import { extractContourLines } from './contours'
import type { GridData } from './math'

describe('extractContourLines', () => {
  it('returns empty array when grid is too small', () => {
    const grid: GridData = {
      x: [1],
      y: [1],
      z: [[1]]
    }
    const lines = extractContourLines(grid, 0.5)
    expect(lines).toEqual([])
  })

  it('extracts contour lines successfully when supported by valid data', () => {
    // We need a large enough grid because current logic filters out lines < 10 points
    // Let's create an 20x20 grid, with z forming a peak in the center so the contour forms a circle
    const n = 20
    const x = Array.from({ length: n }, (_, i) => i + 1)
    const y = Array.from({ length: n }, (_, i) => i + 1)
    const z: number[][] = []

    for (let j = 0; j < n; j++) {
      const row = []
      for (let i = 0; i < n; i++) {
        // peak at (10, 10)
        const dx = i - 9.5
        const dy = j - 9.5
        const distSq = dx * dx + dy * dy
        // Value decreases with distance, peak is 10
        row.push(10 - distSq)
      }
      z.push(row)
    }

    const grid: GridData = { x, y, z }
    
    // Threshold 5 should form a contour around radius sqrt(5) ~ 2.2
    const lines = extractContourLines(grid, 5)
    
    expect(lines.length).toBeGreaterThan(0)
    expect(lines[0].x.length).toBeGreaterThanOrEqual(10)
  })

  it('returns empty when there is no valid data', () => {
    const grid: GridData = {
      x: [1, 2, 3],
      y: [1, 2, 3],
      z: [
        [NaN, NaN, NaN],
        [NaN, NaN, NaN],
        [NaN, NaN, NaN]
      ]
    }
    const lines = extractContourLines(grid, 0.5)
    expect(lines).toEqual([])
  })
})
