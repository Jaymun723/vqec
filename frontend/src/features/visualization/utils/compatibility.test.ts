import { describe, it, expect } from 'vitest'
import { getAxisSignature, isCompatible } from './normalization'

describe('Sweep Axis Signature & Compatibility Checks', () => {
  it('correctly creates an axis signature', () => {
    const names = ['loss_reset', 'loss_2_qubit_gate']
    const values = {
      loss_reset: [0.01, 0.05],
      loss_2_qubit_gate: [0.001, 0.005],
    }

    const signature = getAxisSignature(names, values)

    expect(signature.axisNames).toEqual(names)
    expect(signature.axisValues).toEqual(values)
    expect(signature.axisValueHashes).toEqual(['0.01,0.05', '0.001,0.005'])
  })

  it('declares identical sweep signatures as compatible', () => {
    const sig1 = {
      axisNames: ['loss_reset', 'loss_2_qubit_gate'],
      axisValues: {
        loss_reset: [0.01, 0.05],
        loss_2_qubit_gate: [0.001, 0.005],
      },
      axisValueHashes: ['0.01,0.05', '0.001,0.005'],
    }

    const sig2 = {
      axisNames: ['loss_reset', 'loss_2_qubit_gate'],
      axisValues: {
        loss_reset: [0.01, 0.05],
        loss_2_qubit_gate: [0.001, 0.005],
      },
      axisValueHashes: ['0.01,0.05', '0.001,0.005'],
    }

    expect(isCompatible(sig1, sig2)).toBe(true)
  })

  it('declares signatures with different axis names as incompatible', () => {
    const sig1 = {
      axisNames: ['loss_reset'],
      axisValueHashes: ['0.01,0.05'],
    } as any

    const sig2 = {
      axisNames: ['spam_flip_probability'],
      axisValueHashes: ['0.01,0.05'],
    } as any

    expect(isCompatible(sig1, sig2)).toBe(false)
  })

  it('declares signatures with different value ranges as incompatible', () => {
    const sig1 = {
      axisNames: ['loss_reset'],
      axisValueHashes: ['0.01,0.05'],
    } as any

    const sig2 = {
      axisNames: ['loss_reset'],
      axisValueHashes: ['0.01,0.1'], // Mismatched parameter range
    } as any

    expect(isCompatible(sig1, sig2)).toBe(false)
  })
})
