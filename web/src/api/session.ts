/** 会话：把玩家身份换成服务端签名的 Cookie。
 *
 *  为什么需要：以前 player_id 由前端自己传（`?player_id=1`），谁都能冒充别人。
 *  现在身份以服务端下发的 HttpOnly Cookie 为准，前端只负责"第一次握手"。
 *
 *  注意：fetch 在同源请求下默认带 Cookie（credentials: 'same-origin'），
 *  所以这里不需要额外配置；跨域部署（VITE_API_BASE 指向别的域名）才需要
 *  `credentials: 'include'`。
 */

import { request } from './http'

export interface Session {
  player_id: number
  name: string
}

/** 建立（或找回）会话，服务端会 Set-Cookie。 */
export function createSession(name: string): Promise<Session> {
  return request<Session>('/api/session', {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

/** 当前身份；没有会话时抛 ApiError(401)。 */
export function fetchSession(): Promise<Session> {
  return request<Session>('/api/me')
}