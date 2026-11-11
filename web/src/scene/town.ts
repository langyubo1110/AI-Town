/** PixiJS 小镇场景。
 *
 *  能力：玩家可控移动（WASD/方向键）+ 相机跟随 + NPC 自主游走 + 走路动画 + 靠近按 E 对话。
 *
 *  分层原则：不 import 任何 Vue 相关的东西 —— 数据进（setNpcs）、事件出（onSelect / onRequestChat）。
 */

import { Application, Container, Graphics, Sprite, Text } from 'pixi.js'
import type { Npc } from '@/types/api'
import { ROOMS, TILE, WORLD_HEIGHT, WORLD_WIDTH, placeNpcs } from './layout'
import { CHAR_H, CHAR_W, loadCharacterClip } from './assets'
import type { CharClip } from './assets'

const FONT = 'system-ui, "Microsoft YaHei", sans-serif'

const COLOR = {
  bg: 0x12151c,
  roomFill: 0x171a21,
  roomBorder: 0x262b36,
  grid: 0x1f2431,
  text: 0xe6e9ef,
  muted: 0x8b93a7,
  accent: 0x4f8cff,
  prompt: 0x9ad1ff,
  shadow: 0x000000,
}

/** 玩家移动速度（世界坐标 px/秒） */
const PLAYER_SPEED = 200
/** NPC 游走速度 */
const NPC_SPEED = 46
/** 靠近多少像素可以对话 */
const INTERACT_RADIUS = 78
/** 走路动画帧率 */
const WALK_FPS = 9
/** 世界边界内缩（防止贴边走出画面） */
const EDGE = 18
/** NPC 在自己房间内游走时的边距 */
const NPC_INSET = 46

function clamp(value: number, min: number, max: number): number {
  if (min > max) return (min + max) / 2
  return Math.min(max, Math.max(min, value))
}

export interface TownSceneOptions {
  onSelect: (npc: Npc | null) => void
  onRequestChat: (npc: Npc) => void
}

interface Bounds {
  x0: number
  y0: number
  x1: number
  y1: number
}

interface Actor {
  root: Container
  sprite: Sprite
  ring: Graphics
  prompt: Text | null
  clip: CharClip
  frame: number
  acc: number
  moving: boolean
  facing: number
  npc: Npc | null
  bounds: Bounds
  target: { x: number; y: number } | null
  waitUntil: number
}

export class TownScene {
  private app = new Application()
  private world = new Container()
  private npcLayer = new Container()
  private actorLayer = new Container()

  private npcs: Npc[] = []
  private npcActors = new Map<number, Actor>()
  private player: Actor | null = null
  private keys = new Set<string>()
  private nearbyId: number | null = null

  private destroyed = false
  private ready = false

  private readonly onSelect: (npc: Npc | null) => void
  private readonly onRequestChat: (npc: Npc) => void

  constructor(options: TownSceneOptions) {
    this.onSelect = options.onSelect
    this.onRequestChat = options.onRequestChat
  }

  // ---------------- 生命周期 ----------------

  async mount(host: HTMLElement): Promise<void> {
    await this.app.init({
      background: COLOR.bg,
      resizeTo: host,
      antialias: true,
      resolution: window.devicePixelRatio || 1,
      autoDensity: true,
    })

    if (this.destroyed) {
      this.app.destroy(true)
      return
    }

    host.appendChild(this.app.canvas)
    this.app.stage.addChild(this.world)
    this.world.addChild(this.drawFloor())
    this.world.addChild(this.npcLayer)
    this.world.addChild(this.actorLayer)

    // 键盘：挂在 window 上（画布不聚焦也能收到）；输入框聚焦时忽略
    window.addEventListener('keydown', this.onKeyDown)
    window.addEventListener('keyup', this.onKeyUp)

    const playerClip = await loadCharacterClip(0)
    if (playerClip) {
      this.player = this.buildPlayer(playerClip)
      this.actorLayer.addChild(this.player.root)
    }
    if (this.destroyed) return

    this.ready = true
    this.setNpcs(this.npcs)

    this.app.ticker.add(this.tick)
    this.updateCamera()
  }

  setNpcs(npcs: Npc[]): void {
    this.npcs = npcs
    if (!this.ready || this.destroyed) return

    this.npcLayer.removeChildren().forEach((child) => child.destroy({ children: true }))
    this.npcActors.clear()
    this.nearbyId = null

    const spawns = placeNpcs(npcs)
    npcs.forEach((npc, index) => {
      const spawn = spawns.get(npc.id)
      if (!spawn) return
      void this.createNpcActor(npc, index + 1, spawn.x, spawn.y)
    })
  }

  destroy(): void {
    if (this.destroyed) return
    this.destroyed = true
    window.removeEventListener('keydown', this.onKeyDown)
    window.removeEventListener('keyup', this.onKeyUp)
    try {
      this.app.ticker.remove(this.tick)
      this.app.destroy(true, { children: true })
    } catch {
      /* 初始化未完成时忽略 */
    }
  }

  // ---------------- 输入 ----------------

  private onKeyDown = (event: KeyboardEvent): void => {
    if (this.isTyping(event)) return
    this.keys.add(event.code)

    if (event.code === 'KeyE' || event.code === 'Space') {
      const npc = this.nearbyNpc()
      if (npc) {
        event.preventDefault()
        this.onRequestChat(npc)
      }
    }
  }

  private onKeyUp = (event: KeyboardEvent): void => {
    this.keys.delete(event.code)
  }

  /** 焦点在输入框里时不要动角色（否则打字会让人物乱跑） */
  private isTyping(event: KeyboardEvent): boolean {
    const target = event.target as HTMLElement | null
    if (!target) return false
    const tag = target.tagName
    return tag === 'INPUT' || tag === 'TEXTAREA' || target.isContentEditable
  }

  private nearbyNpc(): Npc | null {
    if (this.nearbyId === null) return null
    return this.npcActors.get(this.nearbyId)?.npc ?? null
  }

  // ---------------- 每帧 ----------------

  private tick = (): void => {
    if (this.destroyed) return
    const dt = Math.min(this.app.ticker.deltaMS / 1000, 0.05) // 切标签页回来会有一帧巨大 dt
    const now = performance.now()

    this.movePlayer(dt)
    this.updateNpcs(now, dt)
    this.updateNearby()
    this.animate(dt)
    this.updateCamera()
  }

  private movePlayer(dt: number): void {
    const player = this.player
    if (!player) return

    let vx = 0
    let vy = 0
    if (this.keys.has('KeyA') || this.keys.has('ArrowLeft')) vx -= 1
    if (this.keys.has('KeyD') || this.keys.has('ArrowRight')) vx += 1
    if (this.keys.has('KeyW') || this.keys.has('ArrowUp')) vy -= 1
    if (this.keys.has('KeyS') || this.keys.has('ArrowDown')) vy += 1

    if (vx !== 0 || vy !== 0) {
      const len = Math.hypot(vx, vy) // 斜向不加速
      player.root.position.x += (vx / len) * PLAYER_SPEED * dt
      player.root.position.y += (vy / len) * PLAYER_SPEED * dt
      player.moving = true
      if (vx !== 0) player.facing = vx > 0 ? 1 : -1
    } else {
      player.moving = false
    }

    const halfW = CHAR_W / 2
    player.root.position.x = clamp(player.root.position.x, EDGE + halfW, WORLD_WIDTH - EDGE - halfW)
    player.root.position.y = clamp(player.root.position.y, CHAR_H, WORLD_HEIGHT - EDGE)
  }

  private updateNpcs(now: number, dt: number): void {
    for (const actor of this.npcActors.values()) {
      if (now < actor.waitUntil) {
        actor.moving = false
        continue
      }

      if (!actor.target) {
        actor.target = this.randomPoint(actor.bounds)
      }

      const dx = actor.target.x - actor.root.position.x
      const dy = actor.target.y - actor.root.position.y
      const dist = Math.hypot(dx, dy)

      if (dist < 4) {
        actor.target = null
        actor.moving = false
        actor.waitUntil = now + 1200 + Math.random() * 3200
        continue
      }

      const step = Math.min(dist, NPC_SPEED * dt)
      actor.root.position.x += (dx / dist) * step
      actor.root.position.y += (dy / dist) * step
      actor.moving = true
      if (Math.abs(dx) > 1) actor.facing = dx > 0 ? 1 : -1
    }
  }

  private updateNearby(): void {
    const player = this.player
    if (!player) return

    let bestId: number | null = null
    let bestDist = INTERACT_RADIUS

    for (const [id, actor] of this.npcActors) {
      const dist = Math.hypot(
        actor.root.position.x - player.root.position.x,
        actor.root.position.y - player.root.position.y,
      )
      if (dist < bestDist) {
        bestDist = dist
        bestId = id
      }
    }

    if (bestId === this.nearbyId) return

    if (this.nearbyId !== null) {
      const prev = this.npcActors.get(this.nearbyId)
      if (prev) {
        if (prev.prompt) prev.prompt.visible = false
        prev.ring.visible = false
      }
    }

    this.nearbyId = bestId

    if (bestId !== null) {
      const current = this.npcActors.get(bestId)
      if (current) {
        if (current.prompt) current.prompt.visible = true
        current.ring.visible = true
      }
    }
  }

  private animate(dt: number): void {
    const actors: Actor[] = [...this.npcActors.values()]
    if (this.player) actors.push(this.player)

    const frameTime = 1 / WALK_FPS

    for (const actor of actors) {
      const walk = actor.clip.walk

      if (actor.moving && walk.length > 1) {
        actor.acc += dt
        while (actor.acc >= frameTime) {
          actor.acc -= frameTime
          actor.frame = (actor.frame + 1) % walk.length
        }
        actor.sprite.texture = walk[actor.frame]
      } else {
        actor.acc = 0
        actor.frame = 0
        actor.sprite.texture = actor.clip.idle
      }

      // 水平翻转（anchor 在中心，镜像不会位移）
      actor.sprite.scale.x = actor.facing
    }
  }

  // ---------------- 相机 ----------------

  private updateCamera(): void {
    const { width, height } = this.app.screen
    if (width <= 0 || height <= 0) return

    // 视口越小，放大越多；这样窄屏也能看清人物
    const zoom = clamp(Math.min(width, height) / 380, 1.15, 2.2)
    this.world.scale.set(zoom)

    const viewW = width / zoom
    const viewH = height / zoom
    const focusX = this.player?.root.position.x ?? WORLD_WIDTH / 2
    const focusY = this.player?.root.position.y ?? WORLD_HEIGHT / 2

    const camX = viewW >= WORLD_WIDTH ? WORLD_WIDTH / 2 : clamp(focusX, viewW / 2, WORLD_WIDTH - viewW / 2)
    const camY = viewH >= WORLD_HEIGHT ? WORLD_HEIGHT / 2 : clamp(focusY, viewH / 2, WORLD_HEIGHT - viewH / 2)

    this.world.position.set(width / 2 - camX * zoom, height / 2 - camY * zoom)
  }

  // ---------------- 构建 ----------------

  private drawFloor(): Container {
    const layer = new Container()

    layer.addChild(new Graphics().rect(0, 0, WORLD_WIDTH, WORLD_HEIGHT).fill(COLOR.bg))

    for (const room of ROOMS) {
      layer.addChild(
        new Graphics()
          .rect(room.x, room.y, room.w, room.h)
          .fill(COLOR.roomFill)
          .stroke({ width: 2, color: COLOR.roomBorder }),
      )

      const grid = new Graphics()
      for (let x = room.x + TILE; x < room.x + room.w; x += TILE) {
        grid.moveTo(x, room.y + 4).lineTo(x, room.y + room.h - 4)
      }
      for (let y = room.y + TILE; y < room.y + room.h; y += TILE) {
        grid.moveTo(room.x + 4, y).lineTo(room.x + room.w - 4, y)
      }
      grid.stroke({ width: 1, color: COLOR.grid })
      layer.addChild(grid)

      const label = new Text({
        text: room.label,
        style: { fill: COLOR.muted, fontSize: 13, fontFamily: FONT },
      })
      label.position.set(room.x + 12, room.y + 8)
      layer.addChild(label)
    }

    return layer
  }

  private buildPlayer(clip: CharClip): Actor {
    const root = new Container()
    root.position.set(WORLD_WIDTH / 2, WORLD_HEIGHT - 120)

    // 脚下阴影：一眼能认出"这是我"
    const shadow = new Graphics().ellipse(0, 0, 18, 7).fill({ color: COLOR.shadow, alpha: 0.35 })
    root.addChild(shadow)

    const sprite = new Sprite(clip.idle)
    sprite.anchor.set(0.5, 1)
    root.addChild(sprite)

    const me = new Text({
      text: '我',
      style: { fill: COLOR.prompt, fontSize: 11, fontFamily: FONT },
    })
    me.anchor.set(0.5, 0)
    me.position.set(0, 4)
    root.addChild(me)

    return {
      root,
      sprite,
      ring: new Graphics(),
      prompt: null,
      clip,
      frame: 0,
      acc: 0,
      moving: false,
      facing: 1,
      npc: null,
      bounds: { x0: EDGE, y0: CHAR_H, x1: WORLD_WIDTH - EDGE, y1: WORLD_HEIGHT - EDGE },
      target: null,
      waitUntil: 0,
    }
  }

  private async createNpcActor(npc: Npc, sheetIndex: number, x: number, y: number): Promise<void> {
    const clip = await loadCharacterClip(sheetIndex)
    if (!clip || this.destroyed) return

    const room = ROOMS.find((r) => r.key === npc.location) ?? ROOMS[ROOMS.length - 1]
    const bounds: Bounds = {
      x0: room.x + NPC_INSET,
      y0: room.y + NPC_INSET + 24,
      x1: room.x + room.w - NPC_INSET,
      y1: room.y + room.h - NPC_INSET,
    }

    const root = new Container()
    root.position.set(x, y)

    const ring = new Graphics()
      .ellipse(0, 0, 26, 11)
      .fill({ color: COLOR.accent, alpha: 0.16 })
      .stroke({ width: 2, color: COLOR.accent })
    ring.visible = false
    root.addChild(ring)

    const sprite = new Sprite(clip.idle)
    sprite.anchor.set(0.5, 1)
    sprite.eventMode = 'static'
    sprite.cursor = 'pointer'
    sprite.on('pointerdown', (event) => {
      event.stopPropagation()
      this.onSelect(npc)
    })
    root.addChild(sprite)

    const prompt = new Text({
      text: '按 E 对话',
      style: { fill: COLOR.prompt, fontSize: 11, fontFamily: FONT },
    })
    prompt.anchor.set(0.5, 1)
    prompt.position.set(0, -CHAR_H - 4)
    prompt.visible = false
    root.addChild(prompt)

    const name = new Text({
      text: npc.name,
      style: { fill: COLOR.text, fontSize: 13, fontFamily: FONT },
    })
    name.anchor.set(0.5, 0)
    name.position.set(0, 3)
    root.addChild(name)

    const title = new Text({
      text: npc.title,
      style: { fill: COLOR.muted, fontSize: 10, fontFamily: FONT },
    })
    title.anchor.set(0.5, 0)
    title.position.set(0, 20)
    root.addChild(title)

    this.npcLayer.addChild(root)

    this.npcActors.set(npc.id, {
      root,
      sprite,
      ring,
      prompt,
      clip,
      frame: 0,
      acc: 0,
      moving: false,
      facing: 1,
      npc,
      bounds,
      target: null,
      waitUntil: performance.now() + Math.random() * 2000,
    })
  }

  private randomPoint(bounds: Bounds): { x: number; y: number } {
    return {
      x: bounds.x0 + Math.random() * Math.max(1, bounds.x1 - bounds.x0),
      y: bounds.y0 + Math.random() * Math.max(1, bounds.y1 - bounds.y0),
    }
  }
}