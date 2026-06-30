import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'

import { ApiError } from '../api/client'
import { getCategoryComponents, validateExperiment } from '../api/registry'
import { submitExperiment } from '../api/experiments'
import type { ExperimentConfig } from '../api/types'
import { useExperimentCreationStore } from '../features/experiments/store'

interface ExperimentCreationTabProps {
  onOpenExperimentsTab: () => void
}

function parseInputValue(val: string) {
  const trimmed = val.trim()
  if (trimmed === '') return undefined

  // Match formula references or d shorthand
  if (trimmed.toLowerCase() === 'distance' || trimmed.toLowerCase() === 'd') {
    return trimmed.toLowerCase() === 'd' ? 'd' : 'distance'
  }
  
  // Match linspace/geomspace/logspace shorthands
  if (/^(lin|geom|log)space\(.+\)$/i.test(trimmed)) {
    return trimmed
  }

  // Comma-separated list
  if (trimmed.includes(',')) {
    const parts = trimmed.split(',').map(p => p.trim()).filter(Boolean)
    const nums = parts.map(p => Number(p))
    if (nums.every(n => !isNaN(n))) {
      return nums
    }
    return parts
  }

  // Boolean literals
  if (trimmed.toLowerCase() === 'true') return true
  if (trimmed.toLowerCase() === 'false') return false

  // Number literal
  const num = Number(trimmed)
  if (!isNaN(num) && trimmed !== '') {
    return num
  }

  return trimmed
}

function formatValueForInput(val: any): string {
  if (val === undefined || val === null) return ''
  if (Array.isArray(val)) return val.join(', ')
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function getZodSchemaForProperty(prop: any): z.ZodType<any> {
  let schema: z.ZodType<any> = z.any()
  
  if (prop.enum) {
    schema = z.union(prop.enum.map((val: any) => z.literal(val)) as any)
  } else if (prop.type === 'string') {
    schema = z.string()
  } else if (prop.type === 'integer') {
    schema = z.number().int({ message: 'Must be an integer.' })
  } else if (prop.type === 'number') {
    schema = z.number()
  } else if (prop.type === 'boolean') {
    schema = z.boolean()
  } else if (prop.type === 'array') {
    schema = z.array(z.any())
  }
  
  const sweepStringSchema = z.string().regex(/^(lin|geom|log)space\(.+\)$/i)
  const formulaSchema = z.string().regex(/^(distance|d)$/i)
  
  return z.union([
    schema,
    sweepStringSchema,
    formulaSchema,
    z.array(schema),
  ])
}

function validateParam(prop: any, rawValue: string | undefined | null): string | null {
  if (rawValue === undefined || rawValue === null) {
    return null
  }
  const trimmed = rawValue.trim()
  if (trimmed === '') {
    return null
  }

  const parsed = parseInputValue(trimmed)
  if (parsed === undefined) return 'Invalid value format'

  try {
    const schema = getZodSchemaForProperty(prop)
    schema.parse(parsed)
    return null
  } catch (err: any) {
    if (err instanceof z.ZodError) {
      if (prop.enum) {
        return `Must be one of: ${prop.enum.join(', ')}`
      }
      return `Must be a ${prop.type || 'valid parameter'}, list, or sweep shorthand.`
    }
    return 'Invalid parameter value.'
  }
}

export function ExperimentCreationTab({ onOpenExperimentsTab }: ExperimentCreationTabProps) {
  const queryClient = useQueryClient()
  const {
    form,
    setForm,
    resetForm,
    activeStep,
    setActiveStep,
    advancedJsonEnabled,
    setAdvancedJsonEnabled,
    advancedJsonText,
    setAdvancedJsonText,
  } = useExperimentCreationStore()

  const [localError, setLocalError] = useState<string | null>(null)

  // Fetch constructors
  const circuitQuery = useQuery({
    queryKey: ['registry', 'circuit-constructors'],
    queryFn: () => getCategoryComponents('circuit-constructors'),
  })

  const isOffline = circuitQuery.isError

  // Fetch noise models (filtered)
  const noiseQuery = useQuery({
    queryKey: ['registry', 'noise-models', form.selectedCircuit],
    queryFn: () => getCategoryComponents('noise-models', { circuit_constructor: form.selectedCircuit }),
    enabled: !!form.selectedCircuit,
  })

  // Fetch runners (filtered)
  const runnerQuery = useQuery({
    queryKey: ['registry', 'runners', form.selectedCircuit, form.selectedNoise],
    queryFn: () => getCategoryComponents('runners', { 
      circuit_constructor: form.selectedCircuit,
      noise_model: form.selectedNoise
    }),
    enabled: !!form.selectedCircuit && !!form.selectedNoise,
  })

  // Fetch decoders (filtered)
  const decoderQuery = useQuery({
    queryKey: ['registry', 'decoders', form.selectedCircuit, form.selectedNoise, form.selectedRunner],
    queryFn: () => getCategoryComponents('decoders', {
      circuit_constructor: form.selectedCircuit,
      noise_model: form.selectedNoise,
      runner: form.selectedRunner,
    }),
    enabled: !!form.selectedCircuit && !!form.selectedNoise && !!form.selectedRunner,
  })

  // Current active descriptors
  const selectedCircuitDesc = useMemo(() => {
    return circuitQuery.data?.find(c => c.name === form.selectedCircuit) || null
  }, [circuitQuery.data, form.selectedCircuit])

  const selectedNoiseDesc = useMemo(() => {
    return noiseQuery.data?.find(c => c.name === form.selectedNoise) || null
  }, [noiseQuery.data, form.selectedNoise])

  const selectedRunnerDesc = useMemo(() => {
    return runnerQuery.data?.find(c => c.name === form.selectedRunner) || null
  }, [runnerQuery.data, form.selectedRunner])

  const selectedDecoderDesc = useMemo(() => {
    return decoderQuery.data?.find(c => c.name === form.selectedDecoder) || null
  }, [decoderQuery.data, form.selectedDecoder])

  // Parse raw text string parameter mappings back into dynamic structured arrays or formulas
  const parseRawParams = (schema: any, rawParams: Record<string, string> | undefined | null): Record<string, any> => {
    const parsed: Record<string, any> = {}
    
    if (!schema || !schema.properties) {
      return parsed
    }

    const allowedKeys = Object.keys(schema.properties)

    // First, set default parameters from the component schema properties
    Object.entries(schema.properties).forEach(([k, v]: [string, any]) => {
      if (v.default !== undefined) {
        parsed[k] = v.default
      }
    })

    const params = rawParams || {}
    // Overwrite with actual user entries that are not blank, but ONLY if they exist in the schema properties
    Object.entries(params).forEach(([k, v]) => {
      if (allowedKeys.includes(k) && v && typeof v === 'string' && v.trim() !== '') {
        const parsedVal = parseInputValue(v)
        if (parsedVal !== undefined) {
          parsed[k] = parsedVal
        }
      }
    })

    return parsed
  }

  // Build structured config matching ExperimentConfig
  const experimentConfig = useMemo<ExperimentConfig>(() => {
    return {
      name: form.name,
      circuit: {
        type: form.selectedCircuit,
        params: parseRawParams(selectedCircuitDesc?.schema, form.circuitParamsRaw),
      },
      noise: {
        type: form.selectedNoise,
        params: parseRawParams(selectedNoiseDesc?.schema, form.noiseParamsRaw),
      },
      runner: {
        type: form.selectedRunner,
        params: parseRawParams(selectedRunnerDesc?.schema, form.runnerParamsRaw),
      },
      decoder: {
        type: form.selectedDecoder,
        params: parseRawParams(selectedDecoderDesc?.schema, form.decoderParamsRaw),
      },
      job_backend: form.jobBackend,
      output: form.outputPath,
    }
  }, [form, selectedCircuitDesc, selectedNoiseDesc, selectedRunnerDesc, selectedDecoderDesc])

  // Sync advanced JSON textarea
  useEffect(() => {
    if (!advancedJsonEnabled) {
      setAdvancedJsonText(JSON.stringify(experimentConfig, null, 2))
    }
  }, [experimentConfig, advancedJsonEnabled, setAdvancedJsonText])

  // Sandbox Live Validation
  const validationQuery = useQuery({
    queryKey: ['validate-experiment', advancedJsonEnabled ? advancedJsonText : JSON.stringify(experimentConfig)],
    queryFn: () => {
      let cfg = experimentConfig
      if (advancedJsonEnabled) {
        try {
          cfg = JSON.parse(advancedJsonText)
        } catch {
          return { valid: false, jobs_count: 0, error: 'JSON Syntax Error: Invalid JSON text' }
        }
      }
      return validateExperiment(cfg)
    },
    enabled: activeStep === 5,
    refetchInterval: false,
  })

  // Submit Mutation
  const submitMutation = useMutation({
    mutationFn: async () => {
      let cfg = experimentConfig
      if (advancedJsonEnabled) {
        cfg = JSON.parse(advancedJsonText)
      }
      return submitExperiment(cfg)
    },
    onError: (err) => {
      setLocalError(err instanceof ApiError ? err.message : 'Submission failed.')
    },
    onSuccess: async () => {
      setLocalError(null)
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
      resetForm()
      onOpenExperimentsTab()
    },
  })

  // Form value handlers
  const updateFormVal = (key: keyof typeof form, val: any) => {
    setForm(prev => ({ ...prev, [key]: val }))
  }

  const handleParamChange = (step: 'circuit' | 'noise' | 'runner' | 'decoder', key: string, val: string) => {
    setForm(prev => {
      const updated = { ...prev[`${step}ParamsRaw` as const] }
      updated[key] = val
      return {
        ...prev,
        [`${step}ParamsRaw` as const]: updated
      }
    })
  }

  const stepsList = [
    { title: 'General', desc: 'Experiment specs' },
    { title: 'Circuit', desc: 'Select circuit constructor' },
    { title: 'Noise', desc: 'Add error models' },
    { title: 'Runner', desc: 'Define execution runner' },
    { title: 'Decoder', desc: 'Choose decoders' },
    { title: 'Review', desc: 'Interactive sandbox' },
  ]

  // Render Pydantic dynamic properties
  const renderDynamicProperties = (
    step: 'circuit' | 'noise' | 'runner' | 'decoder',
    properties: Record<string, any>,
    currentParamsRaw: Record<string, string>
  ) => {
    if (!properties || Object.keys(properties).length === 0) {
      return <p className="text-muted" style={{ padding: '8px' }}>No configurable parameters for this component.</p>
    }

    return (
      <div className="dynamic-properties-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', padding: '10px 0' }}>
        {Object.entries(properties).map(([key, prop]: [string, any]) => {
          // Resolve current raw string value or fall back to displaying its default
          const rawVal = currentParamsRaw[key] !== undefined ? currentParamsRaw[key] : formatValueForInput(prop.default)
          const errorMsg = validateParam(prop, rawVal)
          
          const isBool = prop.type === 'boolean'
          const isEnum = Array.isArray(prop.enum)
          
          return (
            <div key={key} className="form-group" style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontWeight: '600', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <code>{key}</code>
                {prop.default !== undefined && (
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: '400' }}>
                    (default: {String(prop.default)})
                  </span>
                )}
              </label>
              
              {isEnum ? (
                /* Select Dropdown constraints */
                <select
                  value={rawVal}
                  onChange={(e) => handleParamChange(step, key, e.target.value)}
                  style={{
                    padding: '8px 12px',
                    borderRadius: '6px',
                    border: '1px solid var(--border-muted)',
                    background: 'var(--bg-input)',
                    color: 'var(--text-main)',
                  }}
                >
                  {prop.enum.map((opt: string) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              ) : isBool ? (
                /* Boolean toggle checkbox */
                <label className="checkbox-wrap" style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', marginTop: '4px' }}>
                  <input
                    type="checkbox"
                    checked={rawVal === 'true'}
                    onChange={(e) => handleParamChange(step, key, String(e.target.checked))}
                  />
                  <span>Enabled</span>
                </label>
              ) : (
                /* Normal parameter text input (supports decimal dot & comma entries) */
                <input
                  type="text"
                  placeholder={prop.default !== undefined ? String(prop.default) : `Enter ${prop.type}`}
                  value={rawVal}
                  onChange={(e) => handleParamChange(step, key, e.target.value)}
                  style={{
                    padding: '8px 12px',
                    borderRadius: '6px',
                    border: errorMsg ? '1px solid #ef4444' : '1px solid var(--border-muted)',
                    background: 'var(--bg-input)',
                    color: 'var(--text-main)',
                  }}
                />
              )}

              {/* Client-side Programmatic Inline Zod Errors */}
              {errorMsg && (
                <span style={{ fontSize: '11px', color: '#ef4444', fontWeight: '500' }}>
                  ⚠ {errorMsg}
                </span>
              )}
              
              {prop.description && (
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', lineHeight: '1.3' }}>
                  {prop.description}
                </span>
              )}
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <section className="panel generation-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <header className="generation-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1>Guided Experiment Creation</h1>
            <p>Design multi-dimensional parameters sweeps with unified Cartesian expansions.</p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <label className="advanced-toggle" style={{ margin: 0 }}>
              <input
                type="checkbox"
                checked={advancedJsonEnabled}
                onChange={(e) => setAdvancedJsonEnabled(e.target.checked)}
              />
              Advanced JSON Editor
            </label>
            {activeStep === 5 && (
              <button
                type="button"
                className="btn submit-btn"
                style={{
                  width: 'auto',
                  minWidth: '150px',
                  background: 'linear-gradient(135deg, #3b82f6, #4f46e5)',
                  color: 'white',
                  fontWeight: 700,
                  border: 'none',
                  boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)',
                }}
                disabled={submitMutation.isPending || validationQuery.data?.valid === false}
                onClick={() => submitMutation.mutate()}
              >
                {submitMutation.isPending ? 'Launching sweep...' : 'Launch Experiment'}
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Errors Alerts */}
      {localError && (
        <div className="tasks-error" style={{ margin: '10px 0', padding: '12px' }}>
          <strong>Launch Error:</strong> {localError}
        </div>
      )}

      {/* Step Indicator Bar */}
      {!advancedJsonEnabled && (
        <div className="wizard-stepper" style={{
          display: 'flex',
          justifyContent: 'space-between',
          background: 'var(--bg-card)',
          borderBottom: '1px solid var(--border-muted)',
          padding: '12px 24px',
          margin: '0 -24px 20px -24px',
        }}>
          {stepsList.map((step, idx) => {
            const isActive = activeStep === idx
            const isCompleted = activeStep > idx
            return (
              <div
                key={step.title}
                onClick={() => setActiveStep(idx)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  cursor: 'pointer',
                  opacity: isActive ? 1 : isCompleted ? 0.8 : 0.4,
                  borderBottom: isActive ? '2px solid #3b82f6' : '2px solid transparent',
                  paddingBottom: '8px',
                  transition: 'all 0.2s',
                  flex: 1,
                  justifyContent: 'center',
                }}
              >
                <div style={{
                  width: '28px',
                  height: '28px',
                  borderRadius: '50%',
                  background: isActive ? '#3b82f6' : isCompleted ? '#10b981' : 'var(--bg-input-alt)',
                  color: isActive || isCompleted ? 'white' : 'var(--text-muted)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 'bold',
                  fontSize: '13px',
                }}>
                  {isCompleted ? '✓' : idx + 1}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', textAlign: 'left' }}>
                  <span style={{ fontWeight: '600', fontSize: '13px', color: isActive ? '#3b82f6' : 'var(--text-main)' }}>
                    {step.title}
                  </span>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {step.desc}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Advanced Text Area mode */}
      {advancedJsonEnabled ? (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="text-muted">Direct JSON payload editing:</span>
            <button
              type="button"
              className="btn btn-row"
              onClick={() => {
                setAdvancedJsonText(JSON.stringify(experimentConfig, null, 2))
              }}
            >
              Reset to Guided Values
            </button>
          </div>
          <textarea
            className="json-editor"
            value={advancedJsonText}
            onChange={(e) => setAdvancedJsonText(e.target.value)}
            style={{
              flex: 1,
              fontFamily: 'monospace',
              fontSize: '13px',
              padding: '16px',
              borderRadius: '8px',
              background: 'var(--bg-input-alt)',
              border: '1px solid var(--border-muted)',
              color: 'var(--text-main)',
              resize: 'none',
            }}
          />
        </div>
      ) : isOffline ? (
        <div style={{
          padding: '32px',
          background: 'rgba(239, 68, 68, 0.05)',
          border: '1px solid rgba(239, 68, 68, 0.2)',
          borderRadius: '8px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
          maxWidth: '600px',
          margin: '40px auto',
          boxShadow: '0 4px 20px rgba(0, 0, 0, 0.2)',
        }}>
          <h3 style={{ margin: 0, color: '#ef4444', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>⚠</span> VQEC Server Connection Failed
          </h3>
          <p style={{ margin: 0, fontSize: '13.5px', lineHeight: '1.5', color: 'var(--text-main)' }}>
            The desktop web client cannot establish a network connection to the simulation server at <code>http://localhost:8000</code>.
          </p>
          <div style={{
            fontSize: '12px',
            color: 'var(--text-muted)',
            background: 'var(--bg-input-alt)',
            padding: '12px',
            borderRadius: '6px',
            border: '1px solid var(--border-muted)',
            fontFamily: 'monospace',
            lineHeight: '1.4',
          }}>
            # Please verify your Python backend API server is running:<br/>
            python -m uvicorn vqec.server.api:app --reload
          </div>
          <button
            type="button"
            className="btn"
            style={{ width: 'fit-content', background: '#3b82f6', color: 'white', border: 'none', fontWeight: '600' }}
            onClick={() => {
              circuitQuery.refetch()
              noiseQuery.refetch()
              runnerQuery.refetch()
              decoderQuery.refetch()
            }}
          >
            Retry Connection
          </button>
        </div>
      ) : (
        /* Guided Wizard Panels */
        <div className="wizard-panels-container" style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
          
          {/* Step 0: General Specs */}
          {activeStep === 0 && (
            <div className="wizard-panel" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <h2>General Experiment Settings</h2>
              <p className="text-muted">Define the base sweep metadata and file naming parameters.</p>
              
              <div className="form-group" style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxWidth: '500px' }}>
                <label style={{ fontWeight: '600' }}>Experiment Name</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => updateFormVal('name', e.target.value)}
                  style={{ padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-muted)', background: 'var(--bg-input)', color: 'var(--text-main)' }}
                />
              </div>

              <div className="form-group" style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxWidth: '500px' }}>
                <label style={{ fontWeight: '600' }}>Parquet Output Path</label>
                <input
                  type="text"
                  value={form.outputPath}
                  onChange={(e) => updateFormVal('outputPath', e.target.value)}
                  style={{ padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-muted)', background: 'var(--bg-input)', color: 'var(--text-main)' }}
                />
              </div>

              <div className="form-group" style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxWidth: '500px' }}>
                <label style={{ fontWeight: '600' }}>Job Backend</label>
                <select
                  value={form.jobBackend}
                  onChange={(e) => updateFormVal('jobBackend', e.target.value)}
                  style={{ padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-muted)', background: 'var(--bg-input)', color: 'var(--text-main)' }}
                >
                  <option value="local">local (Parallel multiprocessing)</option>
                  <option value="celery">celery (Distributed queue)</option>
                </select>
              </div>
            </div>
          )}

          {/* Step 1: Circuit Constructor */}
          {activeStep === 1 && (
            <div className="wizard-panel" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <h2>1. Choose Circuit Constructor</h2>
              <p className="text-muted">The constructor generates topological or physical layouts for stabilizers sweep.</p>
              
              <div className="component-selector-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '16px' }}>
                {circuitQuery.isLoading ? <p>Loading constructors...</p> : circuitQuery.data?.map(c => {
                  const isSelected = form.selectedCircuit === c.name
                  return (
                    <div
                      key={c.name}
                      onClick={() => {
                        updateFormVal('selectedCircuit', c.name)
                      }}
                      style={{
                        padding: '16px',
                        borderRadius: '8px',
                        border: isSelected ? '2px solid #3b82f6' : '1px solid var(--border-muted)',
                        background: isSelected ? 'rgba(59, 130, 246, 0.08)' : 'var(--bg-card)',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                      }}
                    >
                      <h4 style={{ margin: '0 0 6px 0', color: isSelected ? '#3b82f6' : 'var(--text-main)' }}>
                        <code>{c.name}</code>
                      </h4>
                      <p style={{ fontSize: '11px', margin: 0, color: 'var(--text-muted)', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                        {c.description}
                      </p>
                    </div>
                  )
                })}
              </div>

              {selectedCircuitDesc && (
                <div style={{ marginTop: '20px', padding: '16px', border: '1px solid var(--border-muted)', borderRadius: '8px', background: 'var(--bg-card)' }}>
                  <h3 style={{ marginTop: 0 }}>Configure <code>{selectedCircuitDesc.name}</code> Parameters</h3>
                  <div style={{ background: 'var(--bg-input-alt)', padding: '10px 14px', borderRadius: '6px', fontSize: '12px', color: 'var(--text-muted)', marginBottom: '16px' }}>
                    💡 <strong>Tip:</strong> Sweep variables support comma lists (e.g. <code>3,5,7</code>) and <code>linspace(3,7,3)</code>. Rounds support <code>distance</code> reference.
                  </div>
                  {renderDynamicProperties('circuit', selectedCircuitDesc.schema.properties || {}, form.circuitParamsRaw)}
                </div>
              )}
            </div>
          )}

          {/* Step 2: Noise Model */}
          {activeStep === 2 && (
            <div className="wizard-panel" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <h2>2. Choose Noise Model</h2>
              <p className="text-muted">Error channels and probabilities applied on top of the built circuit.</p>
              
              <div className="component-selector-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '16px' }}>
                {noiseQuery.isLoading ? <p>Loading noise models...</p> : noiseQuery.data?.map(c => {
                  const isSelected = form.selectedNoise === c.name
                  return (
                    <div
                      key={c.name}
                      onClick={() => {
                        updateFormVal('selectedNoise', c.name)
                      }}
                      style={{
                        padding: '16px',
                        borderRadius: '8px',
                        border: isSelected ? '2px solid #3b82f6' : '1px solid var(--border-muted)',
                        background: isSelected ? 'rgba(59, 130, 246, 0.08)' : 'var(--bg-card)',
                        cursor: 'pointer',
                      }}
                    >
                      <h4 style={{ margin: '0 0 6px 0', color: isSelected ? '#3b82f6' : 'var(--text-main)' }}>
                        <code>{c.name}</code>
                      </h4>
                      <p style={{ fontSize: '11px', margin: 0, color: 'var(--text-muted)', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                        {c.description}
                      </p>
                    </div>
                  )
                })}
              </div>

              {selectedNoiseDesc && (
                <div style={{ marginTop: '20px', padding: '16px', border: '1px solid var(--border-muted)', borderRadius: '8px', background: 'var(--bg-card)' }}>
                  <h3 style={{ marginTop: 0 }}>Configure <code>{selectedNoiseDesc.name}</code> Parameters</h3>
                  <div style={{ background: 'var(--bg-input-alt)', padding: '10px 14px', borderRadius: '6px', fontSize: '12px', color: 'var(--text-muted)', marginBottom: '16px' }}>
                    💡 <strong>Tip:</strong> Channel probability can sweep via <code>0.001,0.01,0.05</code> or <code>geomspace(1e-4,1e-2,5)</code>.
                  </div>
                  {renderDynamicProperties('noise', selectedNoiseDesc.schema.properties || {}, form.noiseParamsRaw)}
                </div>
              )}
            </div>
          )}

          {/* Step 3: Runner */}
          {activeStep === 3 && (
            <div className="wizard-panel" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <h2>3. Choose Simulation Runner</h2>
              <p className="text-muted">The engine executing stabilizer sampling runs.</p>
              
              <div className="component-selector-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '16px' }}>
                {runnerQuery.isLoading ? <p>Loading runners...</p> : runnerQuery.data?.map(c => {
                  const isSelected = form.selectedRunner === c.name
                  return (
                    <div
                      key={c.name}
                      onClick={() => {
                        updateFormVal('selectedRunner', c.name)
                      }}
                      style={{
                        padding: '16px',
                        borderRadius: '8px',
                        border: isSelected ? '2px solid #3b82f6' : '1px solid var(--border-muted)',
                        background: isSelected ? 'rgba(59, 130, 246, 0.08)' : 'var(--bg-card)',
                        cursor: 'pointer',
                      }}
                    >
                      <h4 style={{ margin: '0 0 6px 0', color: isSelected ? '#3b82f6' : 'var(--text-main)' }}>
                        <code>{c.name}</code>
                      </h4>
                      <p style={{ fontSize: '11px', margin: 0, color: 'var(--text-muted)' }}>
                        {c.description}
                      </p>
                    </div>
                  )
                })}
              </div>

              {selectedRunnerDesc && (
                <div style={{ marginTop: '20px', padding: '16px', border: '1px solid var(--border-muted)', borderRadius: '8px', background: 'var(--bg-card)' }}>
                  <h3 style={{ marginTop: 0 }}>Configure <code>{selectedRunnerDesc.name}</code> Parameters</h3>
                  {renderDynamicProperties('runner', selectedRunnerDesc.schema.properties || {}, form.runnerParamsRaw)}
                </div>
              )}
            </div>
          )}

          {/* Step 4: Decoder */}
          {activeStep === 4 && (
            <div className="wizard-panel" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <h2>4. Choose Decoder</h2>
              <p className="text-muted">The error matching algorithm that resolves logical syndromes.</p>
              
              <div className="component-selector-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '16px' }}>
                {decoderQuery.isLoading ? <p>Loading decoders...</p> : decoderQuery.data?.map(c => {
                  const isSelected = form.selectedDecoder === c.name
                  return (
                    <div
                      key={c.name}
                      onClick={() => {
                        updateFormVal('selectedDecoder', c.name)
                      }}
                      style={{
                        padding: '16px',
                        borderRadius: '8px',
                        border: isSelected ? '2px solid #3b82f6' : '1px solid var(--border-muted)',
                        background: isSelected ? 'rgba(59, 130, 246, 0.08)' : 'var(--bg-card)',
                        cursor: 'pointer',
                      }}
                    >
                      <h4 style={{ margin: '0 0 6px 0', color: isSelected ? '#3b82f6' : 'var(--text-main)' }}>
                        <code>{c.name}</code>
                      </h4>
                      <p style={{ fontSize: '11px', margin: 0, color: 'var(--text-muted)' }}>
                        {c.description}
                      </p>
                    </div>
                  )
                })}
              </div>

              {selectedDecoderDesc && (
                <div style={{ marginTop: '20px', padding: '16px', border: '1px solid var(--border-muted)', borderRadius: '8px', background: 'var(--bg-card)' }}>
                  <h3 style={{ marginTop: 0 }}>Configure <code>{selectedDecoderDesc.name}</code> Parameters</h3>
                  {renderDynamicProperties('decoder', selectedDecoderDesc.schema.properties || {}, form.decoderParamsRaw)}
                </div>
              )}
            </div>
          )}

          {/* Step 5: Sandbox Review & Submissions */}
          {activeStep === 5 && (
            <div className="wizard-panel" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              <h2>5. Interactive Validation Sandbox</h2>
              <p className="text-muted">Inspect the raw configuration and review the real-time Cartesians expanded sub-jobs.</p>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
                {/* JSON Preview */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <label style={{ fontWeight: '600' }}>Raw Configuration JSON</label>
                  <pre style={{
                    margin: 0,
                    background: 'var(--bg-input-alt)',
                    border: '1px solid var(--border-muted)',
                    borderRadius: '8px',
                    padding: '16px',
                    fontSize: '12px',
                    lineHeight: '1.4',
                    maxHeight: '380px',
                    overflowY: 'auto',
                    fontFamily: 'monospace',
                    color: 'var(--text-main)',
                  }}>
                    {JSON.stringify(experimentConfig, null, 2)}
                  </pre>
                </div>

                {/* Validation Sandbox Status Dashboard */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <label style={{ fontWeight: '600' }}>Validation Sandbox Report</label>
                  
                  {validationQuery.isLoading ? (
                    <div style={{
                      padding: '24px',
                      background: 'rgba(59, 130, 246, 0.05)',
                      border: '1px dashed #3b82f6',
                      borderRadius: '8px',
                      textAlign: 'center',
                    }}>
                      <span className="text-muted">Executing live validation sandbox expansions...</span>
                    </div>
                  ) : validationQuery.data?.valid ? (
                    <div style={{
                      padding: '24px',
                      background: 'rgba(16, 185, 129, 0.08)',
                      border: '1px solid #10b981',
                      borderRadius: '8px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '12px',
                    }}>
                      <h3 style={{ margin: 0, color: '#10b981', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span>✓</span> Validation Successful
                      </h3>
                      <p style={{ margin: 0, fontSize: '13px' }}>
                        This experiment config passes all topological parameter matching and adapter tag checks.
                      </p>
                      <div style={{
                        marginTop: '8px',
                        padding: '12px',
                        borderRadius: '6px',
                        background: 'var(--bg-input-alt)',
                        border: '1px solid var(--border-muted)',
                        fontSize: '14px',
                        fontWeight: '600',
                      }}>
                        Total Sweep Points (Jobs): <span style={{ color: '#3b82f6' }}>{validationQuery.data.jobs_count}</span>
                      </div>
                    </div>
                  ) : (
                    <div style={{
                      padding: '24px',
                      background: 'rgba(239, 68, 68, 0.08)',
                      border: '1px solid #ef4444',
                      borderRadius: '8px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '12px',
                    }}>
                      <h3 style={{ margin: 0, color: '#ef4444', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span>✗</span> Validation Sandbox Failed
                      </h3>
                      <p style={{ margin: 0, fontSize: '13px', lineHeight: '1.4' }}>
                        The backend validator caught compatibility or parsing mismatches:
                      </p>
                      <pre style={{
                        margin: 0,
                        padding: '12px',
                        background: 'var(--bg-input-alt)',
                        borderRadius: '6px',
                        color: '#f87171',
                        fontSize: '12px',
                        whiteSpace: 'pre-wrap',
                        border: '1px solid rgba(239, 68, 68, 0.2)',
                      }}>
                        {validationQuery.data?.error}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Navigation Buttons */}
      {!advancedJsonEnabled && !isOffline && (
        <footer style={{
          display: 'flex',
          justifyContent: 'space-between',
          marginTop: '20px',
          borderTop: '1px solid var(--border-muted)',
          paddingTop: '16px',
        }}>
          <button
            type="button"
            className="btn"
            disabled={activeStep === 0}
            onClick={() => setActiveStep(activeStep - 1)}
          >
            ← Back
          </button>
          
          {activeStep < 5 ? (
            <button
              type="button"
              className="btn"
              style={{ background: '#3b82f6', color: 'white', border: 'none' }}
              onClick={() => setActiveStep(activeStep + 1)}
            >
              Continue →
            </button>
          ) : (
            <button
              type="button"
              className="btn submit-btn"
              style={{
                width: 'auto',
                minWidth: '150px',
                background: 'linear-gradient(135deg, #3b82f6, #4f46e5)',
                color: 'white',
                fontWeight: 700,
                border: 'none',
                boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)',
              }}
              disabled={submitMutation.isPending || validationQuery.data?.valid === false}
              onClick={() => submitMutation.mutate()}
            >
              {submitMutation.isPending ? 'Launching...' : 'Launch Experiment'}
            </button>
          )}
        </footer>
      )}
    </section>
  )
}
