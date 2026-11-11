import { request } from './http'
import type { NpcListOut } from '@/types/api'

export function fetchNpcs(): Promise<NpcListOut> {
  return request<NpcListOut>('/api/npcs')
}