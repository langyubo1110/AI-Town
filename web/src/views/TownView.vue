<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import TownCanvas from '@/components/TownCanvas.vue'
import ChatPanel from '@/components/ChatPanel.vue'
import EventFeed from '@/components/EventFeed.vue'
import PlanBoard from '@/components/PlanBoard.vue'
import { fetchNpcs } from '@/api/npc'
import { fetchPlans } from '@/api/town'
import { ApiError } from '@/api/http'
import type { ChatOut, Npc, NpcPlan, TownEvent } from '@/types/api'

const STORAGE_KEY = 'aitown.playerName'

/** WebSocket 没连上时的兜底刷新间隔。
 *  为什么需要：playerId 只有聊过一次天才拿得到，在那之前 WS 连不上，
 *  而"打开页面就能看到小镇自己动"是演示的第一印象。
 */
const POLL_MS = 30_000

const npcs = ref<Npc[]>([])
const plans = ref<NpcPlan[]>([])
const loading = ref(true)
const error = ref('')
const plansLoading = ref(false)
const selected = ref<Npc | null>(null)
const playerName = ref(localStorage.getItem(STORAGE_KEY) || '小明')
const playerId = ref<number | null>(null)

watch(playerName, (name) => {
  localStorage.setItem(STORAGE_KEY, name)
  // 换名字等于换玩家：旧的事件流不再属于他
  playerId.value = null
})

/** 位置没变就不替换数组：TownCanvas 的 watch 会重建全部精灵，
 *  每 30 秒重建一次画面会闪。
 */
function sameLocations(a: Npc[], b: Npc[]): boolean {
  if (a.length !== b.length) return false
  return a.every((npc, i) => npc.id === b[i].id && npc.location === b[i].location)
}

/** silent=true：后台刷新，不闪 loading、不覆盖已有报错 */
async function loadNpcs(silent = false) {
  if (!silent) {
    loading.value = true
    error.value = ''
  }
  try {
    const data = await fetchNpcs()
    if (silent && sameLocations(npcs.value, data.items)) return
    npcs.value = data.items
  } catch (err) {
    if (!silent) {
      error.value =
        err instanceof ApiError
          ? `加载失败（${err.status}）：${err.message}`
          : '加载失败：未知错误'
    }
  } finally {
    if (!silent) loading.value = false
  }
}

async function loadPlans() {
  plansLoading.value = true
  try {
    const data = await fetchPlans()
    plans.value = data.items
  } catch {
    // 计划面板失败不该影响主流程：静默，等下一次轮询
  } finally {
    plansLoading.value = false
  }
}

/** 实时事件 → 按需刷新。plan_step 意味着有人换了房间、计划状态也变了 */
function onTownEvent(event: TownEvent) {
  if (event.event_type === 'plan_step') {
    loadPlans()
    loadNpcs(true)
  }
}

function onChatted(result: ChatOut) {
  // 第一次聊天后才知道自己在数据库里的 id（后端 get_or_create 出来的）
  playerId.value = result.player_id
  loadPlans()
}

/** 点计划卡片 → 选中这个 NPC，右侧面板就变成和他的对话 */
function onPlanSelect(npcId: number) {
  const npc = npcs.value.find((item) => item.id === npcId)
  if (npc) selected.value = npc
}

let pollTimer: ReturnType<typeof setInterval> | undefined

onMounted(async () => {
  await loadNpcs()
  loadPlans()
  pollTimer = setInterval(() => {
    loadPlans()
    loadNpcs(true)
  }, POLL_MS)
})

onBeforeUnmount(() => clearInterval(pollTimer))
</script>

<template>
  <main class="town">
    <header class="bar">
      <div>
        <h1>AI Town</h1>
        <p class="sub">在镇子上走走，遇到人就聊两句</p>
      </div>
      <label class="who">
        我是
        <input v-model="playerName" maxlength="16" spellcheck="false" />
      </label>
    </header>

    <p v-if="loading" class="hint">加载中…</p>
    <div v-else-if="error" class="error">
      <p>{{ error }}</p>
      <button @click="loadNpcs()">重试</button>
    </div>

    <template v-else>
      <TownCanvas
        :npcs="npcs"
        @select="(npc) => (selected = npc)"
        @request-chat="(npc) => (selected = npc)"
      />

      <PlanBoard
        :plans="plans"
        :loading="plansLoading"
        :selected-id="selected?.id ?? null"
        @select="onPlanSelect"
      />

      <div class="panels">
        <ChatPanel :npc="selected" :player-name="playerName" @chatted="onChatted" />
        <EventFeed :player-id="playerId" @event="onTownEvent" />
      </div>
    </template>
  </main>
</template>

<style scoped>
.town {
  max-width: 1180px;
  margin: 0 auto;
  padding: 24px 20px 60px;
}

.bar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}
h1 { font-size: 22px; }
.sub { color: var(--muted); font-size: 13px; margin-top: 2px; }

.who {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--muted);
}
.who input {
  width: 110px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  padding: 5px 9px;
  font-family: inherit;
  font-size: 13px;
  outline: none;
}
.who input:focus { border-color: var(--accent); }

.panels {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(0, 1fr);
  gap: 16px;
  margin-top: 16px;
  align-items: start;
}

@media (max-width: 900px) {
  .panels { grid-template-columns: 1fr; }
}

.hint { color: var(--muted); margin-top: 16px; }

.error {
  border: 1px solid #5a2a2a;
  background: #1e1416;
  color: #ffb4b4;
  border-radius: 10px;
  padding: 16px;
}
.error button {
  margin-top: 10px;
  background: none;
  border: 1px solid #5a2a2a;
  color: #ffb4b4;
  border-radius: 6px;
  padding: 4px 12px;
  cursor: pointer;
}
</style>