<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { sendChat, sendChatStream } from '@/api/chat'
import { ApiError } from '@/api/http'
import type { ChatOut, Npc, NpcPlan, ToolUsed } from '@/types/api'

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

const props = defineProps<{
  npc: Npc | null
  playerName: string
  /** 选中 NPC 的今日计划：没有就不显示计划块 */
  plan?: NpcPlan | null
}>()
const emit = defineEmits<{ chatted: [result: ChatOut] }>()

/** 计划默认收起，只露"下一步做什么"；点「全部」才展开 4 步 */
const showPlan = ref(false)

/** 下一个还没做的步骤 */
const nextStep = computed(() => {
  const steps = props.plan?.steps ?? []
  return steps.find((step) => step.status === 'pending') ?? null
})

/** 每个 NPC 各自保留一份对话，切换对象不串台 */
const histories = ref<Record<number, Turn[]>>({})
const input = ref('')
const sending = ref(false)
/** 流式过程中的中间状态（"正在查内部知识库…"），空串表示没在等 */
const statusText = ref('')
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

/** 往最后一条（正在流式输出的 NPC 气泡）追加文字 */
function appendToLast(npcId: number, chunk: string) {
  const list = histories.value[npcId] ?? []
  if (!list.length) return
  const last = list[list.length - 1]
  histories.value = {
    ...histories.value,
    [npcId]: [...list.slice(0, -1), { ...last, text: last.text + chunk }],
  }
}

/** 用最终结果替换最后一条：流式可能漏字，以 done 帧的 reply 为准 */
function replaceLast(npcId: number, turn: Turn) {
  const list = histories.value[npcId] ?? []
  if (!list.length) return
  histories.value = {
    ...histories.value,
    [npcId]: [...list.slice(0, -1), turn],
  }
}

function dropLast(npcId: number) {
  const list = histories.value[npcId] ?? []
  if (!list.length) return
  histories.value = { ...histories.value, [npcId]: list.slice(0, -1) }
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
  // 先占一个空的 NPC 气泡，流式内容就往后追加
  pushTurn(npc.id, { role: 'npc', text: '' })
  scrollToBottom()

  const npcId = npc.id
  const outbound = {
    player_name: props.playerName.trim() || '小明',
    npc_name: npc.name,
    message: text,
  }

  function settle(result: ChatOut) {
    replaceLast(npcId, {
      role: 'npc',
      text: result.reply,
      delta: result.affinity_delta,
      tools: result.tools ?? [],
    })
    affinity.value = { score: result.affinity_score, level: result.affinity_level }
    emit('chatted', result)
    scrollToBottom()
  }

  try {
    // 流式：首字大约 0.8 秒出现，而不是等 3 秒整段蹦出来
    const result = await sendChatStream(outbound, {
      onStatus: (text) => {
        // 检索/调工具期间的状态：替代"空白 + 对方正在想…"
        statusText.value = text
      },
      onDelta: (chunk) => {
        // 第一个字到了，状态就可以撤了
        statusText.value = ''
        appendToLast(npcId, chunk)
        scrollToBottom()
      },
    })
    settle(result)
  } catch {
    // 降级：浏览器不支持流、代理把 SSE 缓冲了、或者连接中途断了 ——
    // 都能退回一次性接口，用户最多多等两秒，功能不受影响
    dropLast(npcId)
    statusText.value = '正在重新尝试…'
    try {
      settle(await sendChat(outbound))
    } catch (err) {
      dropLast(npcId)
      error.value =
        err instanceof ApiError
          ? `发送失败（${err.status}）：${err.message}`
          : '发送失败：未知错误'
    }
  } finally {
    sending.value = false
    statusText.value = ''
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

    <!-- 这个 NPC 的今日计划：只有选中他时才出现，平时不占地方 -->
    <div v-if="npc && plan" class="planbox">
      <div class="ph">
        <span class="tag">今日计划</span>
        <span class="cnt">{{ plan.done }}/{{ plan.total }}</span>
        <button type="button" class="toggle" @click="showPlan = !showPlan">
          {{ showPlan ? '收起' : '全部' }}
        </button>
      </div>
      <p v-if="plan.weekly_goal" class="goal" :title="plan.weekly_goal">
        目标 · {{ plan.weekly_goal }}
      </p>
      <p v-if="nextStep" class="nowstep">
        <time>{{ nextStep.at }}</time>
        <span class="g">{{ nextStep.goal }}</span>
        <span class="rm">{{ nextStep.room }}</span>
      </p>
      <p v-else class="nowstep muted">今天的安排都完成了</p>

      <ul v-if="showPlan" class="steps">
        <li v-for="(step, i) in plan.steps" :key="i" :class="step.status">
          <time>{{ step.at }}</time>
          <span class="g">{{ step.goal }}</span>
          <span class="rm">{{ step.room }}</span>
        </li>
      </ul>

      <details v-if="plan.reflections.length" class="thoughts">
        <summary>最近的思考</summary>
        <p v-for="(text, i) in plan.reflections" :key="i">{{ text }}</p>
      </details>
    </div>

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

      <p v-if="sending" class="muted thinking">
        <span class="dots"><i /><i /><i /></span>
        {{ statusText || '对方正在想…' }}
      </p>
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
  /* 在分栏布局里要撑满右侧格子；min-height:0 允许它被压缩，否则会顶破容器 */
  height: 100%;
  min-height: 0;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}

.head {
  display: flex;
  align-items: center;
  /* 允许换行：三列布局里这一栏只有 ~344px，名字+职位+房间+好感度挤不下 */
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 6px 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
}
.who {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px 8px;
  min-width: 0;
}
.who strong { font-size: 15px; white-space: nowrap; }
.badge {
  font-size: 11px;
  color: var(--accent);
  border: 1px solid var(--accent);
  border-radius: 999px;
  padding: 0 7px;
  white-space: nowrap;
}
.loc { font-size: 12px; color: var(--muted); white-space: nowrap; }

/* 好感度独占一行，进度条自动伸缩，不再把名字挤成竖排 */
.affinity {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1 0 100%;
}
.bar {
  flex: 1 1 auto;
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

/* ---- 选中 NPC 的今日计划（默认只露下一步） ---- */
.planbox {
  flex: 0 0 auto;
  padding: 8px 14px 9px;
  border-bottom: 1px solid var(--border);
  background: #14171e;
}
.ph { display: flex; align-items: baseline; gap: 8px; }
.tag { font-size: 11px; color: var(--muted); }
.cnt {
  font-size: 11px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.toggle {
  margin-left: auto;
  background: none;
  border: 1px solid var(--border);
  color: var(--muted);
  border-radius: 6px;
  padding: 1px 8px;
  font-size: 11px;
  cursor: pointer;
}
.toggle:hover { color: var(--text); }

.goal {
  margin-top: 4px;
  font-size: 11px;
  color: #8fa6c4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nowstep {
  margin-top: 5px;
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
}
.nowstep time {
  flex: 0 0 auto;
  color: #8fb3ff;
  font-variant-numeric: tabular-nums;
}
.nowstep .g {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nowstep .rm,
.steps .rm {
  flex: 0 0 auto;
  font-size: 10px;
  color: #8fb3ff;
  border: 1px solid #2c3b55;
  border-radius: 999px;
  padding: 0 6px;
}

.steps {
  list-style: none;
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.steps li {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 11px;
  color: #c9d4e5;
}
.steps li time {
  flex: 0 0 auto;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.steps li .g {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.steps li.done .g { color: #6b7280; text-decoration: line-through; }

.thoughts { margin-top: 7px; }
.thoughts summary {
  font-size: 11px;
  color: var(--muted);
  cursor: pointer;
  list-style: none;
}
.thoughts summary::-webkit-details-marker { display: none; }
.thoughts p {
  margin-top: 4px;
  font-size: 11px;
  line-height: 1.5;
  color: #c9d4e5;
  padding-left: 8px;
  border-left: 2px solid #2c3b55;
}

/* 等待中的状态行：三个跳动的点让"在等"这件事看起来是活的 */
.thinking {
  display: flex;
  align-items: center;
  gap: 8px;
}
.thinking .dots {
  display: inline-flex;
  gap: 3px;
}
.thinking .dots i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent);
  opacity: 0.35;
  animation: think 1.1s infinite ease-in-out;
}
.thinking .dots i:nth-child(2) { animation-delay: 0.15s; }
.thinking .dots i:nth-child(3) { animation-delay: 0.3s; }

@keyframes think {
  0%, 80%, 100% { opacity: 0.25; transform: translateY(0); }
  40% { opacity: 1; transform: translateY(-2px); }
}

.log {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
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