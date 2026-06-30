import { describe, it, expect } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'
import { parquetReadObjects } from 'hyparquet'
import { compressors } from 'hyparquet-compressors'
import { extractAxes, normalizeSweepToLayers } from './normalization'

describe('Parquet Ingestion & Layer Normalization', () => {
  it('correctly extracts exactly 2 layers with good data from experiment2.parquet', async () => {
    // 1. Load the experiment2.parquet file
    const filePath = path.join(__dirname, 'experiment2.parquet')
    const buffer = fs.readFileSync(filePath)
    
    // 2. Parse using hyparquet
    const file = {
      byteLength: buffer.byteLength,
      slice: (start: number, end?: number) => {
        const arrayBuffer = new Uint8Array(buffer).buffer
        return arrayBuffer.slice(start, end)
      }
    }
    
    const rows = await parquetReadObjects({ file, compressors })
    
    expect(rows.length).toBeGreaterThan(0)
    
    // 3. Extract axes and verify noise columns are identified
    const { names } = extractAxes(rows)
    
    // The noise columns in the parquet are 'noise_loss_reset', 'noise_loss_2_qubit_gate', 'noise_after_clifford_depolarization', 'noise_spam_flip_probability'
    expect(names).toContain('loss_reset')
    expect(names).toContain('loss_2_qubit_gate')
    expect(names).toContain('after_clifford_depolarization')
    expect(names).toContain('spam_flip_probability')
    expect(names).not.toContain('type')
    
    // 4. Normalize rows into layers
    const layers = normalizeSweepToLayers(
      2,
      'sweep',
      'Experiment 2',
      rows,
      names
    )
    
    // We expect EXACTLY 2 layers because the cartesian product of circuit_ and decoder_ params:
    // (distance=3, rounds=3) and (distance=5, rounds=5)
    expect(layers.length).toBe(2)
    
    // Verify each layer contains valid data points with non-zero or correct shots & errors
    layers.forEach(layer => {
      expect(layer.data.length).toBeGreaterThan(0)
      
      // Each data point should have coordinates, error rates, shots, etc.
      layer.data.forEach(point => {
        expect(point.shots).toBe(1000)
        expect(point.params['loss_reset']).toBeDefined()
        expect(point.params['loss_2_qubit_gate']).toBeDefined()
        expect(typeof point.lepr).toBe('number')
        expect(typeof point.errorRate).toBe('number')
      })
    })

    // Assert that we have good data (some points have non-zero logical error rates)
    const allLeprValues = layers.flatMap(l => l.data.map(d => d.lepr))
    const maxLepr = Math.max(...allLeprValues)
    expect(maxLepr).toBeGreaterThan(0)
  })

  it('handles empty datasets gracefully', () => {
    const emptyRows: any[] = []
    const { names, values } = extractAxes(emptyRows)
    expect(names).toEqual([])
    expect(values).toEqual({})

    const layers = normalizeSweepToLayers(1, 'sweep', 'Empty', emptyRows, [])
    expect(layers).toEqual([])
  })

  it('handles missing or partial metrics with robust fallbacks', () => {
    const mockRows = [
      {
        circuit_distance: 3,
        circuit_rounds: 3,
        noise_p: 0.01,
        // n_errors and shots are completely missing
      }
    ]
    const { names } = extractAxes(mockRows)
    const layers = normalizeSweepToLayers(1, 'sweep', 'Fallback Test', mockRows, names)

    expect(layers.length).toBe(1)
    const point = layers[0].data[0]
    expect(point.errors).toBe(0)
    expect(point.shots).toBe(1)
    expect(point.errorRate).toBe(0)
    expect(point.lepr).toBe(0)
  })

  it('correctly maps single-layer sweeps to exactly one layer', () => {
    const mockRows = [
      { circuit_distance: 3, circuit_rounds: 3, noise_p: 0.01, n_errors: 2, shots: 100 },
      { circuit_distance: 3, circuit_rounds: 3, noise_p: 0.02, n_errors: 10, shots: 100 }
    ]
    const { names } = extractAxes(mockRows)
    const layers = normalizeSweepToLayers(1, 'sweep', 'Single Layer Test', mockRows, names)

    expect(layers.length).toBe(1)
    expect(layers[0].data.length).toBe(2)
  })
})
