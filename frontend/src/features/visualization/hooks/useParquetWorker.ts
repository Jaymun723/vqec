import { useCallback, useRef } from 'react'

export function useParquetWorker() {
  const workerRef = useRef<Worker | null>(null)

  const parseParquet = useCallback((buffer: ArrayBuffer): Promise<any[]> => {
    const requestId = Math.random().toString(36).slice(2)
    return new Promise((resolve, reject) => {
      if (!workerRef.current) {
        // Use Vite's worker constructor
        workerRef.current = new Worker(
          new URL('../../../workers/parquet.worker.ts', import.meta.url),
          { type: 'module' }
        )
      }

      const worker = workerRef.current

      const handleMessage = (e: MessageEvent) => {
        if (e.data.requestId !== requestId) return

        worker.removeEventListener('message', handleMessage)
        worker.removeEventListener('error', handleError)
        if (e.data.error) {
          reject(new Error(e.data.error))
        } else {
          resolve(e.data.rows)
        }
      }

      const handleError = (e: ErrorEvent) => {
        // Error events don't have requestId, but they usually mean worker crashed.
        // We'll reject the current promise.
        worker.removeEventListener('message', handleMessage)
        worker.removeEventListener('error', handleError)
        reject(new Error(e.message))
      }

      worker.addEventListener('message', handleMessage)
      worker.addEventListener('error', handleError)

      worker.postMessage({ buffer, requestId }, [buffer])
    })
  }, [])

  return { parseParquet }
}
