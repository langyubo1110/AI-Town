import { request } from './http'
import type { PlanListOut } from '@/types/api'

/** 今日计划（只读）。
 *
 *  计划由 worker 的 ticker 懒生成：第一次 tick 时调 LLM 排程并写进 Redis，
 *  所以这个接口不触发任何写入 —— 页面刷新多少次都不会多花一次模型调用。
 */
export function fetchPlans(): Promise<PlanListOut> {
  return request<PlanListOut>('/api/town/plans')
}