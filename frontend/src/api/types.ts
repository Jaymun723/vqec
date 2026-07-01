export type TaskStatus =
  | 'IN_FLIGHT'
  | 'DONE'
  | 'ERROR'
  | 'CANCELLED'

// Deprecated task type kept for backward compatibility with the visualization tab
export type TaskType = 'sweep' | 'dataset'

export interface RegistryResponse {
  circuit_constructors: string[]
  noise_models: string[]
  runners: string[]
  decoders: string[]
}

export interface RegistryComponent {
  name: string
  description: string
  schema: Record<string, any>
  compatibility: {
    circuit_constructors?: string[]
    noise_models?: string[]
    runners?: string[]
  }
}

export interface ExperimentTaskRead {
  id: number
  name: string
  config_hash: string
  status: TaskStatus
  error: string | null
  result_path: string | null
  submitted_at: string
}

export interface ExperimentTaskDetail extends ExperimentTaskRead {
  config: Record<string, any>
}

export interface ExperimentConfig {
  name: string
  circuit: {
    type: string
    params: Record<string, any>
  }
  noise: {
    type: string
    params: Record<string, any>
  }
  runner: {
    type: string
    params: Record<string, any>
  }
  decoder: {
    type: string
    params: Record<string, any>
  }
}

export interface ValidationResponse {
  valid: boolean
  jobs_count: number
  error: string | null
}

// --- Legacy Compatibility Aliases ---
export type UnifiedTaskSummary = ExperimentTaskRead
export type TaskDetail = ExperimentTaskDetail
export interface ListTasksParams {
  task_type?: TaskType
  status?: TaskStatus
  limit?: number
  offset?: number
}
