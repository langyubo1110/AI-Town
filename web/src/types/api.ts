/** 后端 schemas 的 TS 镜像。
 *
 *  字段必须和 Python 侧完全一致，改后端时记得同步这里。
 *  对应关系：
 *    Npc / NpcListOut        ← app/api/schemas/npc.py
 *    ChatIn / ChatOut        ← app/api/schemas/chat.py
 *    TownEvent / EventListOut ← app/api/schemas/event.py
 */

export interface Npc {
  id: number
  name: string
  title: string
  personality: string
  expertise: string
  style: string
  location: string
  is_active: boolean
}

export interface NpcListOut {
  total: number
  items: Npc[]
}

export interface ChatIn {
  player_name: string
  npc_name: string
  message: string
}

/** 一次工具调用的摘要（对应后端 ToolUsed） */
export interface ToolUsed {
  name: string
  args: Record<string, unknown>
}

export interface ChatOut {
  player_id: number
  npc_name: string
  npc_title: string
  reply: string
  affinity_score: number
  affinity_delta: number
  affinity_level: string
  tools: ToolUsed[]
}

/** 注意：不能叫 Event —— 那是 DOM 的内置类型，会和全局撞车。
 *  加个前缀是最省事的解法。
 */
export interface TownEvent {
  id: number
  event_type: string
  npc_id: number | null
  summary: string
  payload: Record<string, unknown>
  created_at: string
}

export interface EventListOut {
  total: number
  items: TownEvent[]
  next_before_id: number | null
}