import { z } from 'zod'
import { apiJsonRequest, apiRequest, getApiBaseUrl } from './client'
import {
  experimentTaskReadSchema,
  experimentTaskReadListSchema,
  experimentTaskDetailSchema,
} from './schemas'
import type { ExperimentConfig } from './types'

export function submitExperiment(config: ExperimentConfig) {
  return apiJsonRequest('/tasks/experiment', config, experimentTaskReadSchema)
}

export function listExperiments() {
  return apiRequest('/tasks/experiment', experimentTaskReadListSchema)
}

export function getExperimentDetail(id: number) {
  return apiRequest(`/tasks/experiment/${id}`, experimentTaskDetailSchema)
}

export function retryExperiment(id: number) {
  return apiRequest(`/tasks/experiment/${id}/retry`, experimentTaskReadSchema, {
    method: 'POST',
  })
}

export function cancelExperiment(id: number) {
  return apiRequest(`/tasks/experiment/${id}/cancel`, experimentTaskReadSchema, {
    method: 'POST',
  })
}

export function deleteExperiment(id: number) {
  return apiRequest(`/tasks/experiment/${id}`, z.any(), {
    method: 'DELETE',
  })
}

export function buildExperimentDownloadUrl(id: number) {
  const base = getApiBaseUrl()
  return `${base}/tasks/experiment/${id}/download`
}
