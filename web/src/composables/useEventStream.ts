/** 事件流 WebSocket 客户端。
 *
 *  三条必备能力（少一条就是"能演示、不能上线"）：
 *  1. 断线自动重连，且【指数退避】—— 否则服务器一挂，所有标签页每秒轰一次；
 *  2. 卸载时清理定时器和连接，否则 HMR 会泄漏一堆 socket；
 *  3. 对外暴露 status，让 UI 能显示"现在是实时还是降级"。
 */

import { onBeforeUnmount, ref, watch } from 'vue'
import type { Ref } from 'vue'

export type StreamStatus = 'idle' | 'connecting' | 'open' | 'closed'

const MAX_BACKOFF_MS = 30_000

export function useEventStream(
  playerId: Ref<number | null>,
  onEvent: (payload: unknown) => void,
) {
  const status = ref<StreamStatus>('idle')

  let socket: WebSocket | null = null
  let retry = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  let stopped = false

  function dropSocket() {
    if (!socket) return
    socket.onopen = null
    socket.onmessage = null
    socket.onclose = null
    socket.onerror = null
    socket.close()
    socket = null
  }

  function scheduleReconnect() {
    if (stopped || !playerId.value) return
    const backoff = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** retry)
    const delay = backoff + Math.random() * 500 // 抖动，避免同时重连
    retry += 1
    status.value = 'closed'
    timer = setTimeout(connect, delay)
  }

  function connect() {
    const id = playerId.value
    if (!id) return

    dropSocket()
    status.value = 'connecting'

    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/events?player_id=${id}`)
    socket = ws

    ws.onopen = () => {
      retry = 0
      status.value = 'open'
    }

    ws.onmessage = (event) => {
      try {
        onEvent(JSON.parse(event.data))
      } catch {
        /* 非 JSON 帧（比如心跳）忽略 */
      }
    }

    ws.onerror = () => {
      // 统一交给 onclose 处理重连
      ws.close()
    }

    ws.onclose = () => {
      if (socket === ws) socket = null
      scheduleReconnect()
    }
  }

  watch(
    playerId,
    (id) => {
      clearTimeout(timer)
      stopped = !id
      retry = 0
      if (!id) {
        dropSocket()
        status.value = 'idle'
        return
      }
      connect()
    },
    { immediate: true },
  )

  onBeforeUnmount(() => {
    stopped = true
    clearTimeout(timer)
    dropSocket()
  })

  return { status }
}