import { z } from 'zod'

export const taskStatusSchema = z.enum([
  'PENDING',
  'RUNNING',
  'COMPLETED',
  'FAILED',
  'CANCELLED',
])

// Legacy Zod schema for backward compatibility
export const taskTypeSchema = z.enum(['sweep', 'dataset'])

export const registryResponseSchema = z.object({
  circuit_constructors: z.array(z.string()),
  noise_models: z.array(z.string()),
  runners: z.array(z.string()),
  decoders: z.array(z.string()),
})

export const registryComponentSchema = z.object({
  name: z.string(),
  description: z.string(),
  schema: z.record(z.string(), z.unknown()),
  compatibility: z.object({
    circuit_constructors: z.array(z.string()).optional(),
    noise_models: z.array(z.string()).optional(),
    runners: z.array(z.string()).optional(),
  }).default({}),
})

export const registryComponentListSchema = z.array(registryComponentSchema)

export const experimentTaskReadSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  config_hash: z.string(),
  status: taskStatusSchema,
  completed_jobs: z.number().int(),
  total_jobs: z.number().int(),
  error_message: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
})

export const experimentTaskReadListSchema = z.array(experimentTaskReadSchema)

export const jobTaskReadSchema = z.object({
  id: z.number().int(),
  status: taskStatusSchema,
  logical_error_rate: z.number().nullable(),
  time_total_s: z.number().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
})

export const experimentTaskDetailSchema = experimentTaskReadSchema.extend({
  config: z.record(z.string(), z.unknown()),
  jobs: z.array(jobTaskReadSchema),
})

export const validationResponseSchema = z.object({
  valid: z.boolean(),
  jobs_count: z.number().int(),
  error: z.string().nullable(),
})

// --- Legacy Compatibility Aliases ---
export const unifiedTaskSummarySchema = experimentTaskReadSchema
export const taskDetailSchema = experimentTaskDetailSchema
export const unifiedTaskSummaryListSchema = experimentTaskReadListSchema
