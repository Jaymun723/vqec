import type { ReactNode } from 'react'

export type TabId = `pinned:${string}` | `viz:${string}`

export interface TabDefinition {
  id: TabId
  title: string
  pinned: boolean
  path: string
  content: ReactNode
}
