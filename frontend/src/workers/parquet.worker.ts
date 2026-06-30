import { parquetReadObjects } from 'hyparquet'
import { compressors } from 'hyparquet-compressors'

self.onmessage = async (e: MessageEvent<{ buffer: ArrayBuffer; requestId: string }>) => {
  const { buffer, requestId } = e.data
  try {
    const file = {
      byteLength: buffer.byteLength,
      slice: (start: number, end?: number) => buffer.slice(start, end)
    }
    const rows = await parquetReadObjects({ file, compressors })
    self.postMessage({ rows, requestId })
  } catch (error) {
    self.postMessage({ error: error instanceof Error ? error.message : String(error), requestId })
  }
}
