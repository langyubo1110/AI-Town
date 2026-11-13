import { request } from './http'
import type { ChatIn, ChatOut } from '@/types/api'

const BASE = import.meta.env.VITE_API_BASE ?? ''

/** 和 NPC 说一句话。
 *  这是同步接口：后端会跑完整个 LangGraph 才返回（约 2~4 秒）。
 *  流式用例见 sendChatStream。
 */
export function sendChat(payload: ChatIn): Promise<ChatOut> {
  return request<ChatOut>('/api/chat', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** 流式对话：边收边渲染，最后返回完整结果。
 *
 *  为什么用 fetch + ReadableStream，而不是 EventSource：
 *    EventSource 只能发 GET，带不了 JSON body。POST + SSE 必须自己读流。
 *
 *  为什么最后还返回 ChatOut：
 *    文字是流式的，但好感度/工具列表要等整轮结束才算得出来。
 *    前端先逐字渲染，收到 done 再补这些元数据。
 */
export async function sendChatStream(
  payload: ChatIn,
  handlers: { onDelta?: (text: string) => void } = {},
): Promise<ChatOut> {
  const res = await fetch(`${BASE}/api/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok || !res.body) {
    throw new Error(`流式请求失败：HTTP ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: ChatOut | null = null
  let failure = ''

  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE 用空行分帧；一次可能读到半帧，所以按 \n\n 切、剩下的留在 buffer
    let cut = buffer.indexOf('\n\n')
    while (cut >= 0) {
      const frame = buffer.slice(0, cut)
      buffer = buffer.slice(cut + 2)
      cut = buffer.indexOf('\n\n')

      const line = frame.split('\n').find((item) => item.startsWith('data:'))
      if (!line) continue

      const event = JSON.parse(line.slice(5).trim()) as
        | { type: 'delta'; text: string }
        | { type: 'error'; message: string }
        | ({ type: 'done' } & ChatOut)

      if (event.type === 'delta') {
        handlers.onDelta?.(event.text)
      } else if (event.type === 'error') {
        failure = event.message
      } else {
        // done 帧除了 type 之外就是 ChatOut 的全部字段
        result = event as unknown as ChatOut
      }
    }
  }

  if (failure) throw new Error(failure)
  if (!result) throw new Error('流式响应没有正常结束')
  return result
}