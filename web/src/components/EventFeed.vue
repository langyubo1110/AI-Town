<script setup lang="ts">
import { computed, onBeforeUnmount, ref, toRef, watch } from 'vue'
import { fetchEvents } from '@/api/event'
import { ApiError } from '@/api/http'
import { useEventStream } from '@/composables/useEventStream'
import type { TownEvent } from '@/types/api'

const props = defineProps<{ playerId: number | null }>()

const events = ref<TownEvent[]>([])
const loading = ref(false)
const error = ref('')

/** WebSocket 连不上时退回轮询（推拉结合：推送负责实时，拉取负责补偿） */
const POLL_MS = 10_000
let timer: ReturnType<typeof setInterval> | undefined

const { status } = useEventStream(toRef(props, 'playerId'), (raw) => {
  const incoming = raw as TownEvent
  if (typeof incoming?.id !== 'number') return
  if (events.value.some((item) => item.id === incoming.id)) return // 去重：推送和轮询可能同时到达
  events.value = [incoming, ...events.value].slice(0, 50)
})

const dotClass = computed(() => status.value)
const statusText = computed(() => {
  switch (status.value) {
    case 'open':
      return '实时推送中'
    case 'connecting':
      return '连接中…'
    case 'closed':
      return '连接断开，已降级为轮询'
    default:
      return '未连接'
  }
})

function stopPolling() {
  if (timer) {
    clearInterval(timer)
    timer = undefined
  }
}

async function load() {
  if (!props.playerId) return
  loading.value = true
  try {
    const data = await fetchEvents({ player_id: props.playerId, limit: 30 })
    events.value = data.items
    error.value = ''
  } catch (err) {
    error.value =
      err instanceof ApiError ? `事件加载失败（${err.status}）` : '事件加载失败'
  } finally {
    loading.value = false
  }
}

// 实时通道打开 → 只在切换时回填一次；否则每 10 秒轮询
watch(
  [() => props.playerId, status],
  ([id, current]) => {
    stopPolling()
    if (!id) {
      events.value = []
      return
    }
    load()
    if (current !== 'open') {
      timer = setInterval(load, POLL_MS)
    }
  },
  { immediate: true },
)

onBeforeUnmount(stopPolling)

function timeOf(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString('zh-CN', { hour12: false })
}

/** 从 payload.lines 取出 NPC 互聊的对话行（结构不合法就返回空数组） */
function linesOf(event: TownEvent): { speaker: string; text: string }[] {
  const raw = event.payload?.lines
  if (!Array.isArray(raw)) return []
  return raw
    .map((item) => item as { speaker?: unknown; text?: unknown })
    .filter((item) => typeof item.speaker === 'string' && typeof item.text === 'string')
    .map((item) => ({ speaker: item.speaker as string, text: item.text as string }))
}
</script>

<template>
  <aside class="feed">
    <header class="head">
      <div class="title">
        <strong>小镇动态</strong>
        <span v-if="playerId" :class="['dot', dotClass]" :title="statusText" />
      </div>
      <button :disabled="!playerId || loading" @click="load">刷新</button>
    </header>

    <p v-if="!playerId" class="muted">
      和一个 NPC 聊一句之后，这里会开始出现事件
    </p>
    <p v-else-if="error" class="err">{{ error }}</p>
    <p v-else-if="events.length === 0" class="muted">
      {{ loading ? '加载中…' : '还没有事件' }}
    </p>

    <ul v-else class="list">
      <li v-for="event in events" :key="event.id" class="item">
        <div class="row">
          <span :class="['type', event.event_type]">{{ event.event_type }}</span>
          <time>{{ timeOf(event.created_at) }}</time>
        </div>
        <p class="summary">{{ event.summary }}</p>
        <div v-if="linesOf(event).length" class="lines">
          <p v-for="(line, index) in linesOf(event)" :key="index">
            <b>{{ line.speaker }}</b>：{{ line.text }}
          </p>
        </div>
      </li>
    </ul>
  </aside>
</template>

<style scoped>
.feed {
  display: flex;
  flex-direction: column;
  min-height: 380px;
  max-height: 620px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
}
.title { display: flex; align-items: center; gap: 8px; }
.head button {
  background: none;
  border: 1px solid var(--border);
  color: var(--muted);
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
}
.head button:disabled { opacity: 0.5; cursor: not-allowed; }

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #6b7280;
}
.dot.open {
  background: #4ade80;
  box-shadow: 0 0 6px #4ade80;
}
.dot.connecting { background: #fbbf24; }
.dot.closed { background: #6b7280; }

.list {
  list-style: none;
  overflow-y: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.item {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  background: #14171e;
}
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.type {
  font-size: 11px;
  color: var(--accent);
  border: 1px solid var(--accent);
  border-radius: 999px;
  padding: 0 8px;
}
.type.npc_dialogue { color: #c792ea; border-color: #c792ea; }
time { font-size: 11px; color: var(--muted); }
.summary { margin-top: 6px; font-size: 13px; line-height: 1.55; }

.lines {
  margin-top: 8px;
  padding-left: 10px;
  border-left: 2px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.lines p { font-size: 12px; color: #b9c0d0; }
.lines b { color: var(--text); font-weight: 500; }

.muted { color: var(--muted); font-size: 13px; padding: 14px; }
.err { color: #ffb4b4; font-size: 12px; padding: 14px; }
</style>