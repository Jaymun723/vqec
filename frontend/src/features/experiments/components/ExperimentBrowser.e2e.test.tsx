// @vitest-environment jsdom

// Redirect all frontend fetch calls destined for port 8000 to port 8089 to use the isolated test server
const originalFetch = global.fetch
global.fetch = function(url: any, init?: any) {
  if (typeof url === 'string' && url.startsWith('http://localhost:8000')) {
    url = url.replace('http://localhost:8000', 'http://localhost:8089')
  }
  return originalFetch ? originalFetch(url, init) : Promise.reject(new Error("originalFetch is not defined"))
} as any

import { beforeAll, afterAll, describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { spawn, ChildProcess, execSync } from 'child_process'
import * as path from 'path'
import * as fs from 'fs'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'

// Set the API base URL environment variable before importing client/components
process.env.VITE_API_BASE_URL = 'http://localhost:8089'
// @ts-ignore
if (import.meta.env) {
  // @ts-ignore
  import.meta.env.VITE_API_BASE_URL = 'http://localhost:8089'
}

// Mock ResizeObserver for react-resizable-panels JSDOM compatibility
global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
}

import { ExperimentBrowser } from './ExperimentBrowser'

let serverProcess: ChildProcess
const dbPath = path.resolve(__dirname, '../../../../../data/vqec_test_server.db')

function renderWithProviders(ui: React.ReactElement, queryClient: QueryClient) {
  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {ui}
      </BrowserRouter>
    </QueryClientProvider>
  )
}

describe('ExperimentBrowser UI & API E2E Integration', () => {
  beforeAll(async () => {
    // Kill any lingering processes on port 8089
    try {
      execSync('fuser -k 8089/tcp || true')
    } catch (err) {
      // Ignore
    }

    // Clean any residual test DB from a crashed test run
    if (fs.existsSync(dbPath)) {
      fs.unlinkSync(dbPath)
    }

    // Spawn the isolated backend server process on port 8089 using uv
    serverProcess = spawn(
      'uv',
      ['run', 'uvicorn', 'vqec.server.main:app', '--host', '127.0.0.1', '--port', '8089'],
      {
        cwd: path.resolve(__dirname, '../../../../../'),
        env: {
          ...process.env,
          VQEC_DATABASE_URL: `sqlite+aiosqlite:///${dbPath}`
        }
      }
    )

    serverProcess.on('error', (err) => {
      console.error('Failed to start test server process:', err)
    })
    serverProcess.stderr?.on('data', (data) => {
      console.error(`Server stderr: ${data}`)
    })

    // Wait for the test server to become online
    let alive = false
    for (let i = 0; i < 60; i++) {
      try {
        const res = await fetch('http://localhost:8089/tasks/experiment')
        if (res.ok) {
          alive = true
          break
        }
      } catch (err) {
        await new Promise(resolve => setTimeout(resolve, 200))
      }
    }

    if (!alive) {
      throw new Error('Isolated uvicorn test server failed to start on port 8089')
    }
  }, 20000)

  afterAll(async () => {
    // Kill the test server process cleanly
    if (serverProcess) {
      serverProcess.kill('SIGTERM')
    }

    // Clean up the isolated test SQLite DB
    await new Promise(resolve => setTimeout(resolve, 300))
    if (fs.existsSync(dbPath)) {
      try {
        fs.unlinkSync(dbPath)
      } catch (err) {
        // Safe to ignore if locked
      }
    }
  })

  it('interacts with the real server database to Cancel, Retry, and Delete a task, and asserts zero DOM errors occur', async () => {
    // 1. Programmatically seed an experiment task on the test server
    const seedConfig = {
      name: "UI_E2E_Test_Task",
      circuit: {
        type: "stim_circuit_constructor",
        params: {
          name: "surface_code:rotated_memory_z",
          distance: [3],
          rounds: "distance"
        }
      },
      noise: {
        type: "depolarizing_noise",
        params: {
          p: [0.01]
        }
      },
      runner: {
        type: "stim_runner",
        params: {
          shots: 10
        }
      },
      decoder: {
        type: "pymatching",
        params: {}
      },
      output: "results.parquet"
    }

    const postRes = await fetch('http://localhost:8089/tasks/experiment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(seedConfig)
    })
    expect(postRes.ok).toBe(true)
    const taskData = await postRes.json()
    expect(taskData.name).toBe("UI_E2E_Test_Task")
    expect(taskData.status).toBe("PENDING")

    // 2. Render the React UI Component targeting our test port
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          refetchInterval: 1000, // Speed up updates for tests
        }
      }
    })

    renderWithProviders(<ExperimentBrowser showActions={true} />, queryClient)

    // Wait for the seeded task row to be loaded and rendered in the table (specifically target the span in the row to avoid name filter dropdown matches)
    const taskRowName = await screen.findByText("UI_E2E_Test_Task", { selector: 'span' }, { timeout: 3000 })
    expect(taskRowName).toBeDefined()

    // Assert that absolutely no error banners are displayed in the DOM
    expect(document.getElementsByClassName('tasks-error').length).toBe(0)
    expect(document.body.textContent).not.toContain('Connection Refused')
    expect(document.body.textContent).not.toContain('refused')

    // 3. E2E Cancel Button Clicks
    const cancelBtn = screen.getByRole('button', { name: /Cancel/i })
    expect(cancelBtn).toBeDefined()
    await userEvent.click(cancelBtn)

    // Verify Cancel Confirmation Modal displays
    const confirmCancelBtn = await screen.findByRole('button', { name: /Confirm Cancel/i })
    expect(confirmCancelBtn).toBeDefined()
    await userEvent.click(confirmCancelBtn)

    // Assert task status updates to CANCELLED in real-time in the UI table
    await waitFor(() => {
      const statusBadge = screen.getByText('CANCELLED', { selector: '.status-badge' })
      expect(statusBadge).toBeDefined()
    }, { timeout: 3000 })

    // Assert no error banners in the DOM after cancellation
    expect(document.getElementsByClassName('tasks-error').length).toBe(0)

    // 4. E2E Retry Button Clicks
    const retryBtn = screen.getByRole('button', { name: /Retry/i })
    expect(retryBtn).toBeDefined()
    await userEvent.click(retryBtn)

    // Assert task status successfully transitions back to PENDING in the UI table
    await waitFor(() => {
      const statusBadge = screen.getByText('PENDING', { selector: '.status-badge' })
      expect(statusBadge).toBeDefined()
    }, { timeout: 3000 })

    // Assert no error banners in the DOM after retry
    expect(document.getElementsByClassName('tasks-error').length).toBe(0)

    // 5. E2E Delete Button Clicks
    // Cancel the task once again to expose the Delete button in the UI
    const cancelBtn2 = screen.getByRole('button', { name: /Cancel/i })
    await userEvent.click(cancelBtn2)
    const confirmCancelBtn2 = await screen.findByRole('button', { name: /Confirm Cancel/i })
    await userEvent.click(confirmCancelBtn2)

    await waitFor(() => {
      expect(screen.getByText('CANCELLED', { selector: '.status-badge' })).toBeDefined()
    }, { timeout: 3000 })

    // Now click the Delete button
    const deleteBtn = screen.getByRole('button', { name: /Delete/i })
    expect(deleteBtn).toBeDefined()
    await userEvent.click(deleteBtn)

    // Confirm Delete inside confirmation modal
    const confirmDeleteBtn = await screen.findByRole('button', { name: /Confirm Delete/i })
    expect(confirmDeleteBtn).toBeDefined()
    await userEvent.click(confirmDeleteBtn)

    // Assert that the task row is completely deleted and removed from the UI table
    await waitFor(() => {
      expect(screen.queryByText("UI_E2E_Test_Task", { selector: 'span' })).toBeNull()
    }, { timeout: 3000 })

    // Assert no error banners in the DOM after deletion
    expect(document.getElementsByClassName('tasks-error').length).toBe(0)

    // 6. Direct Database Validation
    const getRes = await fetch('http://localhost:8089/tasks/experiment')
    const listData = await getRes.json()
    expect(listData.length).toBe(0) // Confirmed completely empty DB!
  })
})
