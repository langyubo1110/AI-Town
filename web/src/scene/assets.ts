/** 素材加载与切图工具。
 *
 *  两条铁律：
 *  1. 像素图放大必须用「最近邻」采样，否则会糊成一片毛玻璃。
 *  2. 图集（atlas）的本质 = 一张大图 + 一张格子坐标表。
 *
 *  网格是【用 alpha 通道实测出来的】，不是猜的：
 *  - character_*.png：2688×1968，格子 48 宽 × 96 高，人物画在每格下半部分，脚贴格子底边
 *  - 第 0 行第 3 格 = 正面站立
 *  - 第 1 行前 6 格 = 侧向行走循环
 */

import { Assets, Rectangle, Texture, TextureStyle } from 'pixi.js'
import { TILE } from './layout'

// 全局默认：像素图放大不插值。必须放在加载任何贴图之前。
try {
  TextureStyle.defaultOptions.scaleMode = 'nearest'
} catch {
  /* 不同小版本 API 位置可能不同，失败不影响运行 */
}

const CHARACTER_SHEETS = [
  '/assets/characters/character_1.png',
  '/assets/characters/character_2.png',
  '/assets/characters/character_3.png',
  '/assets/characters/character_4.png',
]

/** 角色格子尺寸（高度是 96，不是 48） */
export const CHAR_W = 48
export const CHAR_H = 96

/** 站立帧 */
const IDLE_FRAME = { row: 0, col: 3 }
/** 行走循环：第 1 行，前 6 格 */
const WALK_FRAME = { row: 1, startCol: 0, frames: 6 }

export interface CharClip {
  idle: Texture
  walk: Texture[]
}

/** 从图集里切出一格（col / row 从 0 开始）。 */
export function tileOf(
  sheet: Texture,
  col: number,
  row: number,
  w: number = TILE,
  h: number = TILE,
): Texture {
  return new Texture({
    source: sheet.source,
    frame: new Rectangle(col * w, row * h, w, h),
  })
}

/**
 * 加载某个角色的「站立 + 行走」帧组。
 * @param sheetIndex 0~3，对应 4 张图集（不同穿搭）
 * @returns 失败返回 null（调用方退回几何体，不崩）
 */
export async function loadCharacterClip(sheetIndex: number): Promise<CharClip | null> {
  const url = CHARACTER_SHEETS[sheetIndex % CHARACTER_SHEETS.length]
  try {
    const sheet = await Assets.load<Texture>(url)
    sheet.source.scaleMode = 'nearest'

    const walk = Array.from({ length: WALK_FRAME.frames }, (_, i) =>
      tileOf(sheet, WALK_FRAME.startCol + i, WALK_FRAME.row, CHAR_W, CHAR_H),
    )

    return {
      idle: tileOf(sheet, IDLE_FRAME.col, IDLE_FRAME.row, CHAR_W, CHAR_H),
      walk,
    }
  } catch (err) {
    console.warn('[assets] 角色图集加载失败：', url, err)
    return null
  }
}