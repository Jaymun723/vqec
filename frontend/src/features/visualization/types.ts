import type { TaskType } from '../../api/types'

export interface SweepAxisSignature {
  axisNames: string[]
  axisValues: Record<string, number[]>
  axisValueHashes: string[]
}

export interface DataPoint {
  params: Record<string, number>
  lepr: number
  errorRate: number
  shots: number
  errors: number
}

export interface ExperimentLayer {
  id: string
  sourceTaskId: number
  sourceTaskType: TaskType
  sourceLabel: string
  experimentLabel: string
  visible: boolean
  color: string
  distance: number
  rounds: number
  data: DataPoint[]
}

export interface ComparisonConfig {
  id: string
  layerAId: string
  layerBId: string
  thresholds: number[]
  visible: boolean
  color: string
}

export interface VisualizationTabState {
  tabId: string
  title: string
  importedSweepTaskIds: number[]
  axisSignature: SweepAxisSignature | null
  xAxisName: string | null
  yAxisName: string | null
  sliceValues: Record<string, number>
  layers: ExperimentLayer[]
  comparisons: ComparisonConfig[]
  includePhysicalBaseline: boolean
  physicalBaseline: {
    t1Us: number
    t2StarUs: number
    roundTimeUs: number
    comparisonRounds: number
  }
  sidebarWidth: number
}
