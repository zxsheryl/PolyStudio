import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react'

import { Excalidraw } from '@excalidraw/excalidraw'
import '@excalidraw/excalidraw/index.css'

type ExcalidrawFile = {
  id: string
  dataURL: string
  mimeType: string
  created: number
}

export type ExcalidrawCanvasData = {
  // Keep loose typing to avoid coupling to Excalidraw internals across versions.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  elements: readonly any[]
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  appState: any
  files: Record<string, ExcalidrawFile>
}

export type ExcalidrawCanvasHandle = {
  addImage: (args: { url: string }) => Promise<void>
}

type Props = {
  canvasId: string
  initialData?: ExcalidrawCanvasData
  onDataChange: (data: ExcalidrawCanvasData) => void
}

function sanitizeAppState(appState: any) {
  if (!appState || typeof appState !== 'object') return {}

  // Excalidraw expects collaborators to be a Map. Once JSON-serialized, it often becomes `{}`,
  // which crashes inside Excalidraw (collaborators.forEach is not a function).
  // So we strip it on both load and save.
  const next = { ...appState }
  if ('collaborators' in next) {
    // Always remove to keep persisted data stable.
    // Excalidraw will re-initialize it internally.
    next.collaborators = undefined
  }

  // 全局强制深色主题（避免用户切换/持久化为浅色导致刷新后变浅）
  next.theme = 'dark'
  return next
}

function sanitizeCanvasData(data: ExcalidrawCanvasData): ExcalidrawCanvasData {
  return {
    ...data,
    appState: sanitizeAppState(data.appState),
  }
}

function randomInt() {
  return Math.floor(Math.random() * 1_000_000)
}

function generateId(prefix: string) {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(16).slice(2, 8)}`
}

function guessMimeType(url: string) {
  const u = (url || '').toLowerCase()
  if (u.endsWith('.jpg') || u.endsWith('.jpeg')) return 'image/jpeg'
  if (u.endsWith('.webp')) return 'image/webp'
  if (u.endsWith('.gif')) return 'image/gif'
  return 'image/png'
}

function isMediaElement(el: any) {
  return (
    el &&
    !el.isDeleted &&
    (el.type === 'image' || el.type === 'embeddable' || el.type === 'video')
  )
}

function computeNextPosition(elements: any[], maxNumPerRow = 4, spacing = 20) {
  // 给左上角控制栏预留空间，避免第一张图与按钮挤在一起
  const baseX = 40
  const baseY = 120

  const media = (elements || []).filter(isMediaElement)
  if (media.length === 0) return { x: baseX, y: baseY }

  // Sort by top-left corner
  media.sort((a, b) => (a.y ?? 0) - (b.y ?? 0) || (a.x ?? 0) - (b.x ?? 0))

  // Group into rows by vertical overlap
  const rows: any[][] = []
  for (const el of media) {
    const y = el.y ?? 0
    const h = el.height ?? 0
    let placed = false
    for (const row of rows) {
      const overlaps = row.some((r) => {
        const ry = r.y ?? 0
        const rh = r.height ?? 0
        return Math.max(y, ry) < Math.min(y + h, ry + rh)
      })
      if (overlaps) {
        row.push(el)
        placed = true
        break
      }
    }
    if (!placed) rows.push([el])
  }

  rows.sort((ra, rb) => {
    const ay = ra.reduce((s, e) => s + (e.y ?? 0), 0) / ra.length
    const by = rb.reduce((s, e) => s + (e.y ?? 0), 0) / rb.length
    return ay - by
  })

  const lastRow = rows[rows.length - 1]
  lastRow.sort((a, b) => (a.x ?? 0) - (b.x ?? 0))

  if (lastRow.length < maxNumPerRow) {
    const right = lastRow[lastRow.length - 1]
    return {
      x: Math.max(baseX, (right.x ?? 0) + (right.width ?? 0) + spacing),
      y: Math.max(baseY, Math.min(...lastRow.map((e) => e.y ?? 0))),
    }
  }

  const bottom = Math.max(...lastRow.map((e) => (e.y ?? 0) + (e.height ?? 0)))
  return { x: baseX, y: Math.max(baseY, bottom + spacing) }
}

export const ExcalidrawCanvas = forwardRef<ExcalidrawCanvasHandle, Props>(
  ({ canvasId, initialData, onDataChange }, ref) => {
    const [api, setApi] = useState<any>(null)
    const saveTimer = useRef<number | null>(null)

    const flushSave = useCallback(
      (data: ExcalidrawCanvasData) => {
        if (saveTimer.current) {
          window.clearTimeout(saveTimer.current)
          saveTimer.current = null
        }
        onDataChange(sanitizeCanvasData(data))
      },
      [onDataChange]
    )

    const debouncedSave = useCallback(
      (data: ExcalidrawCanvasData) => {
        if (saveTimer.current) {
          window.clearTimeout(saveTimer.current)
        }
        saveTimer.current = window.setTimeout(() => {
          onDataChange(sanitizeCanvasData(data))
        }, 800)
      },
      [onDataChange]
    )

    useEffect(() => {
      return () => {
        if (saveTimer.current) window.clearTimeout(saveTimer.current)
      }
    }, [])

    const initial = useMemo(() => {
      // Excalidraw expects initialData to be plain object; we keep it as-is.
      if (!initialData) return null
      return sanitizeCanvasData(initialData)
    }, [initialData])

    useImperativeHandle(
      ref,
      () => ({
        addImage: async ({ url }) => {
          if (!api) return

          const img = new Image()
          img.crossOrigin = 'anonymous'

          const { width, height } = await new Promise<{ width: number; height: number }>(
            (resolve) => {
              img.onload = () => resolve({ width: img.naturalWidth || 1024, height: img.naturalHeight || 1024 })
              img.onerror = () => resolve({ width: 1024, height: 1024 })
              img.src = url
            }
          )

          const maxW = 300
          const scale = width > 0 ? Math.min(1, maxW / width) : 1
          const finalW = Math.max(32, Math.round(width * scale))
          const finalH = Math.max(32, Math.round(height * scale))

          const fileId = generateId('im')
          const created = Date.now()

          const file: ExcalidrawFile = {
            id: fileId,
            dataURL: url,
            mimeType: guessMimeType(url),
            created,
          }

          const elements = api.getSceneElements() || []
          const { x, y } = computeNextPosition(elements)

          // 在图片背后加一层白底板，避免深色画布背景导致“同图不同观感”（聊天里通常像白底卡片）
          const bgId = generateId('bg')
          const bgElement = {
            type: 'rectangle',
            id: bgId,
            x,
            y,
            width: finalW,
            height: finalH,
            angle: 0,
            strokeColor: 'transparent',
            backgroundColor: '#ffffff',
            fillStyle: 'solid',
            strokeStyle: 'solid',
            strokeWidth: 1,
            roughness: 0,
            opacity: 100,
            groupIds: [],
            seed: randomInt(),
            version: 1,
            versionNonce: randomInt(),
            isDeleted: false,
            boundElements: null,
            roundness: null,
            frameId: null,
            updated: created,
            link: null,
            locked: false,
          }

          const newElement = {
            type: 'image',
            id: fileId,
            x,
            y,
            width: finalW,
            height: finalH,
            angle: 0,
            fileId,
            strokeColor: '#000000',
            fillStyle: 'solid',
            strokeStyle: 'solid',
            boundElements: null,
            roundness: null,
            frameId: null,
            backgroundColor: 'transparent',
            strokeWidth: 1,
            roughness: 0,
            opacity: 100,
            groupIds: [],
            seed: randomInt(),
            version: 1,
            versionNonce: randomInt(),
            isDeleted: false,
            index: null,
            updated: created,
            link: null,
            locked: false,
            status: 'saved',
            scale: [1, 1],
            crop: null,
          }

          api.addFiles([file])
          // 顺序很重要：先底板再图片，保证底板在下方
          const nextElements = [...elements, bgElement, newElement]
          api.updateScene({ elements: nextElements })

          // 关键：插入图片后立即强制保存一次（不等待 debounce）
          // 否则刷新/关闭页面时可能只落盘了“空画布”的初始 onChange。
          const nextFiles = { ...(api.getFiles?.() || {}), [fileId]: file }
          const nextAppState = api.getAppState ? api.getAppState() : {}
          flushSave({
            elements: nextElements,
            appState: nextAppState,
            files: nextFiles,
          })
        },
      }),
      [api, flushSave]
    )

    return (
      <div className="excalidraw-host" data-canvas-id={canvasId}>
        <Excalidraw
          langCode="zh-CN"
          theme="dark"
          excalidrawAPI={(instance) => setApi(instance)}
          initialData={initial as any}
          onChange={(elements: readonly any[], appState: any, files: any) => {
            const data: ExcalidrawCanvasData = sanitizeCanvasData({
              elements,
              appState: appState,
              files,
            })
            debouncedSave(data)
          }}
        />
      </div>
    )
  }
)

ExcalidrawCanvas.displayName = 'ExcalidrawCanvas'

export default ExcalidrawCanvas


