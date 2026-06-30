import { describe, it, expect } from 'vitest'
import { filterLayerData, layerToGrid } from './math'
import type { DataPoint, ExperimentLayer } from '../types'

describe('Visualization Mathematical & Filtering Helpers', () => {
  describe('filterLayerData', () => {
    it('correctly filters data points matching hyperslice coordinates', () => {
      const data: DataPoint[] = [
        { params: { p: 0.01, rate: 0.05, temp: 10 }, lepr: 0.1, errorRate: 0.1, shots: 100, errors: 10 },
        { params: { p: 0.01, rate: 0.10, temp: 10 }, lepr: 0.2, errorRate: 0.2, shots: 100, errors: 20 },
        { params: { p: 0.02, rate: 0.05, temp: 10 }, lepr: 0.3, errorRate: 0.3, shots: 100, errors: 30 },
        { params: { p: 0.02, rate: 0.05, temp: 20 }, lepr: 0.4, errorRate: 0.4, shots: 100, errors: 40 },
      ]

      const sliceValues = { temp: 10 }
      const xAxisName = 'p'
      const yAxisName = 'rate'

      const filtered = filterLayerData(data, sliceValues, xAxisName, yAxisName)

      // Point with temp=20 should be filtered out
      expect(filtered.length).toBe(3)
      expect(filtered.every(d => d.params.temp === 10)).toBe(true)
    })

    it('ignores active X and Y axes when applying hyperslice filtering', () => {
      const data: DataPoint[] = [
        { params: { p: 0.01, rate: 0.05 }, lepr: 0.1, errorRate: 0.1, shots: 100, errors: 10 },
        { params: { p: 0.02, rate: 0.05 }, lepr: 0.2, errorRate: 0.2, shots: 100, errors: 20 },
      ]

      // Even if sliceValues somehow specifies active axes, filterLayerData should ignore them
      const sliceValues = { p: 0.01, rate: 0.05 }
      const xAxisName = 'p'
      const yAxisName = 'rate'

      const filtered = filterLayerData(data, sliceValues, xAxisName, yAxisName)

      expect(filtered.length).toBe(2)
    })
  })

  describe('layerToGrid', () => {
    it('successfully constructs a 2D grid from coordinate data points', () => {
      const layer: ExperimentLayer = {
        id: 'test-layer',
        sourceTaskId: 1,
        sourceTaskType: 'sweep',
        sourceLabel: 'Test',
        experimentLabel: 'Test Layer',
        visible: true,
        color: '#ff0000',
        distance: 3,
        rounds: 3,
        data: [
          { params: { p: 0.01, q: 0.1 }, lepr: 0.15, errorRate: 0.15, shots: 100, errors: 15 },
          { params: { p: 0.01, q: 0.2 }, lepr: 0.25, errorRate: 0.25, shots: 100, errors: 25 },
          { params: { p: 0.02, q: 0.1 }, lepr: 0.35, errorRate: 0.35, shots: 100, errors: 35 },
          { params: { p: 0.02, q: 0.2 }, lepr: 0.45, errorRate: 0.45, shots: 100, errors: 45 },
        ]
      }

      const grid = layerToGrid(layer, 'p', 'q')

      expect(grid.x).toEqual([0.01, 0.02])
      expect(grid.y).toEqual([0.1, 0.2])
      expect(grid.z).toEqual([
        [0.15, 0.35], // q = 0.1 row (for p = 0.01, 0.02)
        [0.25, 0.45], // q = 0.2 row (for p = 0.01, 0.02)
      ])
    })

    it('pads missing coordinates with NaN', () => {
      const layer: ExperimentLayer = {
        id: 'test-layer',
        sourceTaskId: 1,
        sourceTaskType: 'sweep',
        sourceLabel: 'Test',
        experimentLabel: 'Test Layer',
        visible: true,
        color: '#ff0000',
        distance: 3,
        rounds: 3,
        data: [
          { params: { p: 0.01, q: 0.1 }, lepr: 0.15, errorRate: 0.15, shots: 100, errors: 15 },
          // (0.01, 0.2) is missing
          { params: { p: 0.02, q: 0.1 }, lepr: 0.35, errorRate: 0.35, shots: 100, errors: 35 },
          { params: { p: 0.02, q: 0.2 }, lepr: 0.45, errorRate: 0.45, shots: 100, errors: 45 },
        ]
      }

      const grid = layerToGrid(layer, 'p', 'q')

      expect(grid.z[1][0]).toBeNaN() // index corresponding to p=0.01, q=0.2
      expect(grid.z[1][1]).toBe(0.45) // index corresponding to p=0.02, q=0.2
    })
  })
})
