<script setup lang="ts">
/** 今日计划面板。
 *
 *  只负责展示 + 抛事件，不认识 PixiJS、也不自己取数：
 *  数据由 TownView 统一拉，WebSocket 收到 plan_step 时由 TownView 触发重拉。
 */
import { computed } from 'vue'
import type { NpcPlan, PlanStep } from '@/types/api'

const props = defineProps<{
  plans: NpcPlan[]
  loading: boolean
  selectedId: number | null
}>()

const emit = defineEmits<{ select: [npcId: number] }>()

const STATUS_TEXT: Record<string, string> = {
  done: '完成',
  missed: '错过',
}

/** 有计划多的排前面（3 个 NPC 时更直观），同分按名字 */
const sorted = computed(() =>
  [...props.plans].sort(
    (a, b) => b.total - a.total || a.npc_name.localeCompare(b.npc_name, 'zh-CN'),
  ),
)

function percent(plan: NpcPlan): number {
  return plan.total > 0 ? Math.round((plan.done / plan.total) * 100) : 0
}

function badgeOf(step: PlanStep): string {
  return STATUS_TEXT[step.status] ?? step.status
}
</script>

<template>
  <section class="board">
    <header class="head">
      <strong>今日计划</strong>
      <span class="tip">到点自动执行：换房间 → 写事件 → 推到这个页面</span>
    </header>

    <p v-if="loading && sorted.length === 0" class="muted">加载中…</p>
    <p v-else-if="sorted.length === 0" class="muted">还没有 NPC</p>

    <div v-else class="cards">
      <article
        v-for="plan in sorted"
        :key="plan.npc_id"
        :class="['card', { active: plan.npc_id === selectedId }]"
        title="点一下找他聊天"
        @click="emit('select', plan.npc_id)"
      >
        <div class="row">
          <strong class="name">{{ plan.npc_name }}</strong>
          <span class="count">{{ plan.done }}/{{ plan.total }}</span>
        </div>

        <div class="bar"><i :style="{ width: `${percent(plan)}%` }" /></div>

        <p v-if="plan.total === 0" class="empty">
          计划还没生成（worker 跑起来后 1 分钟内出现）
        </p>
        <ul v-else class="steps">
          <li v-for="(step, index) in plan.steps" :key="index" :class="step.status">
            <span class="at">{{ step.at }}</span>
            <span class="goal">{{ step.goal }}</span>
            <span class="room">{{ step.room }}</span>
            <span v-if="step.status !== 'pending'" class="badge">
              {{ badgeOf(step) }}
            </span>
          </li>
        </ul>
      </article>
    </div>
  </section>
</template>

<style scoped>
.board { margin-top: 16px; }

.head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 8px;
}
.tip { font-size: 11px; color: var(--muted); }

.cards {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 6px;
  scrollbar-width: thin;
}

.card {
  flex: 0 0 262px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px 12px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.card:hover { border-color: #3a3f4b; }
.card.active { border-color: var(--accent); }

.row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.name { font-size: 13px; }
.count { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; }

.bar {
  height: 4px;
  background: #20242e;
  border-radius: 999px;
  margin: 7px 0 9px;
  overflow: hidden;
}
.bar i {
  display: block;
  height: 100%;
  background: var(--accent);
  border-radius: 999px;
  transition: width 0.3s ease;
}

.steps {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.steps li {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
  line-height: 1.5;
}
.at {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  flex: 0 0 auto;
}
.goal {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.room {
  flex: 0 0 auto;
  font-size: 10px;
  color: #8fb3ff;
  border: 1px solid #2c3b55;
  border-radius: 999px;
  padding: 0 6px;
}
.badge {
  flex: 0 0 auto;
  font-size: 10px;
  border-radius: 999px;
  padding: 0 6px;
}
li.done .goal { color: var(--muted); text-decoration: line-through; }
li.done .badge { color: #4ade80; border: 1px solid #2c5137; }
li.missed .goal { color: #7b8496; }
li.missed .badge { color: #f87171; border: 1px solid #5a2a2a; }

.empty { font-size: 11px; color: var(--muted); line-height: 1.5; }
.muted { color: var(--muted); font-size: 13px; }
</style>