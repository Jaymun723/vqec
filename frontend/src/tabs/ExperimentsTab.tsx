import { ExperimentBrowser } from '../features/experiments/components/ExperimentBrowser'

export function ExperimentsTab() {
  return (
    <section className="panel tasks-panel">
      <header className="tasks-header">
        <div>
          <h1>Experiments</h1>
          <p>Global experiment sweep monitoring and management.</p>
        </div>
      </header>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ExperimentBrowser />
      </div>
    </section>
  )
}
