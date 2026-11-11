<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { sendChat } from '@/api/chat'
import { ApiError } from '@/api/http'
import type { ChatOut, Npc, ToolUsed } from '@/types/api'

interface Turn {
  role: 'user' | 'npc'
  text: string
  delta?: number
  /** 这一轮 NPC 调用过的工具（后端返回的摘要，不含结果） */
  tools?: ToolUsed[]
}

/** 工具名 → 人话：别把 get_town_status 直接怼到用户脸上 */
const TOOL_LABELS: Record<string, string> = {
  get_time: '查时间',
  get_town_status: '查小镇',
  search_memories: '翻记忆',
}

function toolLabel(tool: ToolUsed): string {
  const label = TOOL_LABELS[tool.name] ?? tool.name
  const values = Object.values(tool.args ?? {}).filter(
    (value) => value !== '' && value !== null && value !== undefined,
  )
  return values.length ? `${label}(${values.join('、')})` : label
}

const props = defineProps<{ npc: Npc | null; playerName: string }>()
const emit = defineEmits<{ chatted: [result: ChatOut] }>()

/** 每个 NPC 各自保留一份对话，切换对象不串台 */
const histories = ref<Record<number, Turn[]>>({})
const input = ref('')
const sending = ref(false)
const error = ref('')
const affinity = ref<{ score: number; level: string } | null>(null)
const scrollBox = ref<HTMLDivElement | null>(null)
const composer = ref<HTMLTextAreaElement | null>(null)

const turns = computed<Turn[]>(() =>
  props.npc ? histories.value[props.npc.id] ?? [] : [],
)
const canSend = computed(
  () => !!props.npc && input.value.trim().length > 0 && !sending.value,
)

function pushTurn(npcId: number, turn: Turn) {
  histories.value = {
    ...histories.value,
    [npcId]: [...(histories.value[npcId] ?? []), turn],
  }
}

async function scrollToBottom() {
  await nextTick()
  const box = scrollBox.value
  if (box) box.scrollTop = box.scrollHeight
}

watch(
  () => props.npc?.id,
  () => {
    error.value = ''
    input.value = ''
    affinity.value = null
    scrollToBottom()
    // 按 E 打开面板后直接进入打字状态，否则后续按键会跑去控制角色
    nextTick(() => composer.value?.focus())
  },
)

async function send() {
  const npc = props.npc
  if (!npc || !canSend.value) return

  const text = input.value.trim()
  sending.value = true
  error.value = ''

  pushTurn(npc.id, { role: 'user', text })
  input.value = ''
  scrollToBottom()

  try {
    const result = await sendChat({
      player_name: props.playerName.trim() || '小明',
      npc_name: npc.name,
      message: text,
    })
    pushTurn(npc.id, {
      role: 'npc',
      text: result.reply,
      delta: result.affinity_delta,
      tools: result.tools ?? [],
    })
    affinity.value = { score: result.affinity_score, level: result.affinity_level }
    emit('chatted', result)
    scrollToBottom()
  } catch (err) {
    error.value =
      err instanceof ApiError
        ? `发送失败（${err.status}）：${err.message}`
        : '发送失败：未知错误'
  } finally {
    sending.value = false
  }
}

function onKeydown(event: KeyboardEvent) {
  // Enter 发送，Shift+Enter 换行
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    send()
  }
}
</script>

<template>
  <section class="chat">
    <header class="head">
      <div class="who">
        <template v-if="npc">
          <strong>{{ npc.name }}</strong>
          <span class="badge">{{ npc.title }}</span>
          <span class="loc">📍{{ npc.location }}</span>
        </template>
        <span v-else class="muted">点地图上的小人，开始聊天</span>
      </div>

      <div v-if="affinity" class="affinity">
        <div class="bar"><i :style="{ width: affinity.score + '%' }" /></div>
        <span class="lv">{{ affinity.level }} · {{ affinity.score.toFixed(0) }}/100</span>
      </div>
    </header>

    <div ref="scrollBox" class="log">
      <p v-if="!npc" class="muted">还没选中任何人</p>
      <p v-else-if="turns.length === 0" class="muted">跟 {{ npc.name }} 打个招呼吧</p>

      <div v-for="(turn, index) in turns" :key="index" :class="['bubble', turn.role]">
        <span class="name">{{ turn.role === 'user' ? '我' : npc?.name }}</span>
        <span class="text">{{ turn.text }}</span>
        <div v-if="turn.tools?.length" class="tools">
          <span v-for="(tool, i) in turn.tools" :key="i" class="tool">
            🔧 {{ toolLabel(tool) }}
          </span>
        </div>
        <span v-if="turn.delta" class="delta">
          {{ turn.delta > 0 ? '+' : '' }}{{ turn.delta }}
        </span>
      </div>

      <p v-if="sending" class="muted">对方正在想…</p>
    </div>

    <p v-if="error" class="err">{{ error }}</p>

    <div class="compose">
      <textarea
        ref="composer"
        v-model="input"
        rows="2"
        :disabled="!npc || sending"
        :placeholder="
          npc ? `对 ${npc.name} 说点什么（Enter 发送，Shift+Enter 换行）` : '先选一个小人'
        "
        @keydown="onKeydown"
      />
      <button :disabled="!canSend" @click="send">发送</button>
    </div>
  </section>
</template>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  min-height: 380px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
}
.who { display: flex; align-items: baseline; gap: 8px; }
.who strong { font-size: 15px; }
.badge {
  font-size: 11px;
  color: var(--accent);
  border: 1px solid var(--accent);
  border-radius: 999px;
  padding: 0 7px;
}
.loc { font-size: 12px; color: var(--muted); }

.affinity { display: flex; align-items: center; gap: 8px; }
.bar {
  width: 110px;
  height: 6px;
  border-radius: 999px;
  background: #22262f;
  overflow: hidden;
}
.bar i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #4f8cff, #7ad1ff);
  transition: width 0.35s ease;
}
.lv { font-size: 12px; color: var(--muted); white-space: nowrap; }

.log {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 320px;
}

.bubble {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-width: 78%;
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.55;
}
.bubble .name { font-size: 11px; color: var(--muted); }
.bubble.user {
  align-self: flex-end;
  background: #1d2a44;
  border: 1px solid #2b3d5e;
}
.bubble.npc {
  align-self: flex-start;
  background: #1a1e27;
  border: 1px solid var(--border);
}
.delta {
  align-self: flex-end;
  font-size: 11px;
  color: #6fcf97;
}

/* 工具调用痕迹：小、淡、不抢戏，但让"NPC 查了东西"可见 */
.tools {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 2px;
}
.tool {
  font-size: 10.5px;
  line-height: 1.6;
  color: #8fb6ff;
  background: rgba(79, 140, 255, 0.12);
  border: 1px solid rgba(79, 140, 255, 0.35);
  border-radius: 999px;
  padding: 0 7px;
  white-space: nowrap;
}

.err {
  margin: 0 14px 8px;
  font-size: 12px;
  color: #ffb4b4;
}

.compose {
  display: flex;
  gap: 8px;
  padding: 12px 14px;
  border-top: 1px solid var(--border);
}
.compose textarea {
  flex: 1;
  resize: none;
  background: #12151c;
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  font-family: inherit;
  font-size: 13px;
  outline: none;
}
.compose textarea:focus { border-color: var(--accent); }
.compose button {
  align-self: stretch;
  padding: 0 18px;
  border: none;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}
.compose button:disabled { opacity: 0.45; cursor: not-allowed; }

.muted { color: var(--muted); font-size: 13px; }
</style>