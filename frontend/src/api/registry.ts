import { apiJsonRequest, apiRequest, buildQueryString } from './client'
import {
  registryResponseSchema,
  registryComponentSchema,
  registryComponentListSchema,
  validationResponseSchema,
} from './schemas'
import type { ExperimentConfig } from './types'

export function getRegistry() {
  return apiRequest('/registry', registryResponseSchema)
}

export interface ComponentFilterParams {
  circuit_constructor?: string
  noise_model?: string
  runner?: string
  limit?: number
  offset?: number
}

export function getCategoryComponents(category: string, params: ComponentFilterParams = {}) {
  // Normalize category names (accept hyphenated or snake_case, but path must be hyphenated)
  const normalizedCategory = category.replace(/_/g, '-')
  const query = buildQueryString({
    circuit_constructor: params.circuit_constructor,
    noise_model: params.noise_model,
    runner: params.runner,
    limit: params.limit,
    offset: params.offset,
  })
  return apiRequest(`/registry/${normalizedCategory}${query}`, registryComponentListSchema)
}

export function getComponentDetail(category: string, componentName: string) {
  const normalizedCategory = category.replace(/_/g, '-')
  return apiRequest(`/registry/${normalizedCategory}/${componentName}`, registryComponentSchema)
}

export function validateExperiment(config: ExperimentConfig) {
  return apiJsonRequest('/registry/validate-experiment', { config }, validationResponseSchema)
}
