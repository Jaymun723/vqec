import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export interface ExperimentFormState {
  name: string
  outputPath: string
  jobBackend: string
  
  selectedCircuit: string
  circuitParamsRaw: Record<string, string>
  
  selectedNoise: string
  noiseParamsRaw: Record<string, string>
  
  selectedRunner: string
  runnerParamsRaw: Record<string, string>
  
  selectedDecoder: string
  decoderParamsRaw: Record<string, string>
}

const initialExperimentForm: ExperimentFormState = {
  name: 'my_experiment',
  outputPath: 'results/experiment.parquet',
  jobBackend: 'local',
  
  selectedCircuit: 'stim_circuit_constructor',
  circuitParamsRaw: {
    distance: '3, 5',
    rounds: 'distance',
  },
  
  selectedNoise: 'depolarizing_noise',
  noiseParamsRaw: {
    p: '0.001, 0.01',
  },
  
  selectedRunner: 'stim_runner',
  runnerParamsRaw: {
    shots: '100000',
  },
  
  selectedDecoder: 'pymatching',
  decoderParamsRaw: {
    num_neighbours: '10',
  },
}

interface ExperimentCreationStore {
  advancedJsonEnabled: boolean
  setAdvancedJsonEnabled: (enabled: boolean) => void
  
  advancedJsonText: string
  setAdvancedJsonText: (text: string) => void
  
  form: ExperimentFormState
  setForm: (form: ExperimentFormState | ((prev: ExperimentFormState) => ExperimentFormState)) => void
  resetForm: () => void
  
  activeStep: number
  setActiveStep: (step: number) => void
}

export const useExperimentCreationStore = create<ExperimentCreationStore>()(
  persist(
    (set) => ({
      advancedJsonEnabled: false,
      setAdvancedJsonEnabled: (advancedJsonEnabled) => set({ advancedJsonEnabled }),
      
      advancedJsonText: '',
      setAdvancedJsonText: (advancedJsonText) => set({ advancedJsonText }),
      
      form: initialExperimentForm,
      setForm: (form) => set((state) => ({
        form: typeof form === 'function' ? form(state.form) : form
      })),
      resetForm: () => set({ form: initialExperimentForm, activeStep: 0 }),
      
      activeStep: 0,
      setActiveStep: (activeStep) => set({ activeStep }),
    }),
    {
      name: 'vqec-experiment-creation-storage',
      storage: createJSONStorage(() => localStorage),
    }
  )
)
