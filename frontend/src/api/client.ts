import { z } from 'zod'

const DEFAULT_API_BASE_URL = 'http://localhost:8000'
const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL
).replace(/\/$/, '')

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function getApiBaseUrl() {
  return API_BASE_URL
}

function buildQueryString(params: Record<string, string | number | undefined>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined) {
      return
    }
    query.set(key, String(value))
  })
  const serialized = query.toString()
  return serialized ? `?${serialized}` : ''
}

async function parseResponse(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return null
  }

  const isJson = response.headers.get('content-type')?.includes('application/json')
  if (!isJson) {
    return response.text()
  }

  return response.json()
}

export async function apiRequest<T>(
  path: string,
  schema: z.ZodType<T>,
  init?: RequestInit,
) {
  const response = await fetch(`${API_BASE_URL}${path}`, init)
  const payload = await parseResponse(response)

  if (!response.ok) {
    const detail =
      typeof payload === 'object' &&
        payload !== null &&
        'detail' in payload &&
        typeof payload.detail === 'string'
        ? payload.detail
        : `Request failed with status ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return schema.parse(payload)
}

export async function apiJsonRequest<TRequest, TResponse>(
  path: string,
  body: TRequest,
  responseSchema: z.ZodType<TResponse>,
  init?: Omit<RequestInit, 'body'>,
) {
  return apiRequest(path, responseSchema, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    body: JSON.stringify(body),
    ...init,
  })
}

export { buildQueryString }
