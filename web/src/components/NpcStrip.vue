<script setup lang="ts">
/** 画布下方的「居民进度条」。
 *
 *  为什么不再用一整列放大计划卡片：
 *  三个 NPC × 4 步 = 12 行文字，占掉整整一列，下面还空一大片；
 *  而玩家真正关心的是"谁现在在干什么、进度到哪"。所以这里只留
 *  名字 + 进度点 + 当前这一步，点一下就把完整计划展开在对话面板里。
 */

import type { NpcPlan, PlanStep } from '@/types/api'

const props = defineProps<{
  plans: NpcPlan[]
  selectedId: number | null
}>()

const emit = defineEmits<{ select: [npcId: number] }>()

/** 当前这一步：第一个还没完成/没跳过的 */
function current(plan: NpcPlan): PlanStep | null {
  return plan.steps.find((step) => step.status === 'pending') ?? null
}

function nowText(plan: NpcPlan): string {
  const step = current(plan)
  if (!step) return plan.total > 0 ? '今天的安排都完成了' : '今天还没有计划'
  return `${step.at} ${step.goal}`
}
</script>

<template>
  <div v-if="props.plans.length" class="strip">
    <button
      v-for="plan in props.plans"
      :key="plan.npc_id"
      type="button"
      :class="['npc', { active: plan.npc_id === props.selectedId }]"
      :title="nowText(plan)"
      @click="emit('select', plan.npc_id)"
    >
      <div class="top">
        <strong>{{ plan.npc_name }}</strong>
        <span class="count">{{ plan.done }}/{{ plan.total }}</span>
      </div>
      <div class="dots" :aria-label="`进度 ${plan.done}/${plan.total}`">
        <i v-for="(step, i) in plan.steps" :key="i" :class="step.status" />
      </div>
      <span class="now">{{ nowText(plan) }}</span>
    </button>
  </div>
</template>

<style scoped>
.strip {
  flex: 0 0 auto;
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 2px;
  scrollbar-width: thin;
  scrollbar-color: #2d3340 transparent;
}
.strip::-webkit-scrollbar { height: 5px; }
.strip::-webkit-scrollbar-thumb {
  background: #2d3340;
  border-radius: 999px;
}

.npc {
  flex: 1 1 0;
  min-width: 150px;
  max-width: 260px;
  text-align: left;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 7px 10px 8px;
  cursor: pointer;
  color: inherit;
  font: inherit;
  transition: border-color 0.15s, background 0.15s;
}
.npc:hover { border-color: #3a4050; background: #191d26; }
.npc.active { border-color: var(--accent); }

.top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.top strong { font-size: 13px; }
.count {
  font-size: 11px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.dots {
  display: flex;
  gap: 4px;
  margin: 6px 0 5px;
}
.dots i {
  flex: 1 1 auto;
  height: 4px;
  border-radius: 999px;
  background: #232833;
}
.dots i.done { background: #4ade80; }
.dots i.skipped { background: #6b7280; }
.dots i.pending { background: #3a4152; }

.now {
  display: block;
  font-size: 11px;
  color: #8fa6c4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>