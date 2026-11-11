import { request } from './http'
import type { ChatIn, ChatOut } from '@/types/api'

/** 和 NPC 说一句话。
 *  这是同步接口：后端会跑完整个 LangGraph 才返回（约 2~4 秒）。
 */
export function sendChat(payload: ChatIn): Promise<ChatOut> {
  return request<ChatOut>('/api/chat', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}