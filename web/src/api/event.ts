import { request } from './http'
import type { EventListOut } from '@/types/api'

export interface EventQuery {
  player_id: number
  limit?: number
  event_type?: string
  before_id?: number
}

/** 拉取事件流（游标分页：before_id 传上一页最后一条的 id）。 */
export function fetchEvents(query: EventQuery): Promise<EventListOut> {
  const params = new URLSearchParams({ player_id: String(query.player_id) })
  if (query.limit) params.set('limit', String(query.limit))
  if (query.event_type) params.set('event_type', query.event_type)
  if (query.before_id) params.set('before_id', String(query.before_id))
  return request<EventListOut>(`/api/events?${params.toString()}`)
}