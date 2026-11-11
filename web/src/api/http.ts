/** 统一请求封装：负责 baseURL、JSON、错误规范化。 */

// 开发期 base 为空 → 走 Vite 代理（/api/xxx）
// 生产期可通过 .env 设置 VITE_API_BASE=https://api.example.com
const BASE = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** 从 FastAPI 的 {detail: ...} 里提取可读消息。 */
async function extractDetail(res: Response): Promise<string> {
  try {
    const body = await res.json()
    const detail = body?.detail
    if (typeof detail === 'string') return detail
    if (detail) return JSON.stringify(detail)
  } catch {
    /* 响应不是 JSON，忽略 */
  }
  return res.statusText || `HTTP ${res.status}`
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...init?.headers,
      },
    })
  } catch (err) {
    // 网络层失败（后端没起、DNS 错、断网）
    throw new ApiError(0, `网络请求失败：${(err as Error).message}`)
  }

  if (!res.ok) {
    throw new ApiError(res.status, await extractDetail(res))
  }

  // 204 之类没有 body 的情况
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}