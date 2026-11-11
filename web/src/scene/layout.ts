/** 小镇的虚拟坐标系与房间布局。
 *  位置【由后端数据驱动】：NPC 的 location 字段 → 房间 → 坐标。
 *  前端不硬编码"张三在哪"，只提供这张映射表。
 */

export const WORLD_WIDTH = 720
export const WORLD_HEIGHT = 520

/** 素材图集的格子尺寸。
 *  Room_Builder_48x48 / 1_Generic_48x48 / character_*.png 都是 48px 网格。
 */
export const TILE = 48

export interface Room {
  key: string
  label: string
  x: number
  y: number
  w: number
  h: number
}

export const ROOMS: Room[] = [
  { key: '工位区', label: '工位区', x: 40, y: 50, w: 340, h: 210 },
  { key: '会议室', label: '会议室', x: 420, y: 50, w: 260, h: 210 },
  { key: '休息区', label: '休息区', x: 40, y: 300, w: 640, h: 170 },
]

/** 后端出现了未知 location 时的兜底房间 */
const FALLBACK_ROOM = '休息区'

export function placeNpcs<T extends { id: number; location: string }>(
  npcs: T[],
): Map<number, { x: number; y: number }> {
  // 1) 按房间分组（未知房间 → 兜底）
  const groups = new Map<string, T[]>()
  for (const npc of npcs) {
    const key = ROOMS.some((r) => r.key === npc.location) ? npc.location : FALLBACK_ROOM
    const list = groups.get(key) ?? []
    list.push(npc)
    groups.set(key, list)
  }

  // 2) 每个房间里横向均分
  const positions = new Map<number, { x: number; y: number }>()
  for (const [key, list] of groups) {
    const room = ROOMS.find((r) => r.key === key)!
    const usable = room.w - 120
    const gap = list.length > 1 ? Math.min(140, usable / (list.length - 1)) : 0
    const startX = room.x + room.w / 2 - ((list.length - 1) * gap) / 2

    list.forEach((npc, i) => {
      positions.set(npc.id, {
        x: startX + i * gap,
        y: room.y + room.h / 2 + 16,
      })
    })
  }
  return positions
}