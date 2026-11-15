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
      <span class="tip">到点自动执行</span>
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
          <!-- 目标并进首行：单独占一行会让每张卡多 20px，右栏放不下三张 -->
          <span v-if="plan.weekly_goal" class="goal" :title="plan.weekly_goal">
            {{ plan.weekly_goal }}
          </span>
          <span class="count">{{ plan.done }}/{{ plan.total }}</span>
        </div>

        <div class="bar"><i :style="{ width: `${percent(plan)}%` }" /></div>

        <p v-if="plan.total === 0" class="empty">
          计划还没生成（worker 跑起来后 1 分钟内出现）
        </p>
        <ul v-else class="steps">
          <li v-for="(step, index) in plan.steps" :key="index" :class="step.status">
            <span class="at">{{ step.at }}</span>
            <span class="goal-text">{{ step.goal }}</span>
            <span class="room">{{ step.room }}</span>
            <span v-if="step.status !== 'pending'" class="badge">
              {{ badgeOf(step) }}
            </span>
          </li>
        </ul>

        <!-- 反思默认收起：卡片要能一眼看完，想看再点开 -->
        <details v-if="plan.reflections.length" class="thoughts" @click.stop>
          <summary>最近的思考</summary>
          <p v-for="(item, index) in plan.reflections" :key="index">{{ item }}</p>
        </details>
      </article>
    </div>
  </section>
</template>

<style scoped>
.board {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 6px;
  flex: 0 0 auto;
}
.tip { font-size: 11px; color: var(--muted); }

.cards {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-width: thin;
  scrollbar-color: #2d3340 transparent;
}
.cards::-webkit-scrollbar { width: 6px; }
.cards::-webkit-scrollbar-thumb {
  background: #2d3340;
  border-radius: 999px;
}

.card {
  flex: 0 0 auto;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 8px 10px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.card:hover { border-color: #3a3f4b; }
.card.active { border-color: var(--accent); }

.row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.name { font-size: 13px; flex: 0 0 auto; }
.count { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; flex: 0 0 auto; }

/* 周目标：和名字同行，靠右省略号；悬停看全文 */
.goal {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 11px;
  color: #8fa6c4;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar {
  height: 4px;
  background: #20242e;
  border-radius: 999px;
  margin: 6px 0 7px;
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
  gap: 3px;
}
.steps li {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 11px;
  line-height: 1.45;
}
.at {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  flex: 0 0 auto;
}
.goal-text {
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
li.done .goal-text { color: var(--muted); text-decoration: line-through; }
li.done .badge { color: #4ade80; border: 1px solid #2c5137; }
li.missed .goal-text { color: #7b8496; }
li.missed .badge { color: #f87171; border: 1px solid #5a2a2a; }

/* 反思：默认收起，点开才占空间 */
.thoughts {
  margin-top: 8px;
  border-top: 1px dashed var(--border);
  padding-top: 6px;
}
.thoughts summary {
  font-size: 11px;
  color: var(--muted);
  cursor: pointer;
  list-style: none;
  user-select: none;
}
.thoughts summary::-webkit-details-marker { display: none; }
.thoughts summary:hover { color: var(--text); }
.thoughts p {
  margin-top: 5px;
  font-size: 11px;
  line-height: 1.55;
  color: #c9d4e5;
  padding-left: 8px;
  border-left: 2px solid #2c3b55;
}

.empty { font-size: 11px; color: var(--muted); line-height: 1.5; }
.muted { color: var(--muted); font-size: 13px; }

/* 矮屏（1366×768 这类）：再压一档，让三张卡一屏放完 */
@media (max-height: 820px) {
  .card { padding: 5px 8px; }
  .cards { gap: 4px; }
  .steps { gap: 2px; }
  .steps li { align-items: center; font-size: 10px; line-height: 1.3; }
  .at { font-size: 10px; }
  .room { font-size: 9px; padding: 0 4px; line-height: 1.5; }
  .bar { margin: 4px 0 5px; }
  .name { font-size: 12px; }
  .goal { font-size: 10px; }
}
</style>