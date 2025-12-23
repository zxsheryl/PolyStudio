import { useEffect, useMemo, useState } from 'react'
import './HomePage.css'
import { ArrowRight, Clock, LayoutGrid, Plus, Search } from 'lucide-react'

type CanvasSummary = {
  id: string
  name?: string
  createdAt?: number
  images?: unknown[]
  messages?: unknown[]
  data?: {
    elements?: any[]
    files?: Record<string, { dataURL?: string; mimeType?: string }>
  }
}

function getCanvasIdFromUrl() {
  try {
    const url = new URL(window.location.href)
    return url.searchParams.get('canvasId') || ''
  } catch {
    return ''
  }
}

function setCanvasIdToUrl(canvasId: string) {
  const url = new URL(window.location.href)
  url.searchParams.set('canvasId', canvasId)
  window.history.pushState({}, '', url.toString())
  window.dispatchEvent(new PopStateEvent('popstate'))
}

function clearCanvasIdFromUrl() {
  const url = new URL(window.location.href)
  url.searchParams.delete('canvasId')
  window.history.pushState({}, '', url.toString())
  window.dispatchEvent(new PopStateEvent('popstate'))
}

function pickThumbnails(canvas: CanvasSummary, max = 4): string[] {
  const files = canvas.data?.files || {}
  const urls = Object.values(files)
    .map((f) => (typeof f?.dataURL === 'string' ? f.dataURL : null))
    .filter((u): u is string => Boolean(u))
  // 去重 & 截断（最多展示 3 张拼贴预览）
  const uniq = Array.from(new Set(urls))
  return uniq.slice(0, max)
}

function countImages(canvas: CanvasSummary): number {
  const els = canvas.data?.elements || []
  const fromElements = els.filter((e) => e && !e.isDeleted && e.type === 'image').length
  if (fromElements) return fromElements
  return Array.isArray(canvas.images) ? canvas.images.length : 0
}

export default function HomePage() {
  const [projects, setProjects] = useState<CanvasSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [prompt, setPrompt] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    // If already has canvasId (e.g. user pasted link), redirect to board
    const existing = getCanvasIdFromUrl()
    if (existing) return
    clearCanvasIdFromUrl()
  }, [])

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)
        const res = await fetch('/api/canvases')
        if (!res.ok) throw new Error('Failed to load projects')
        const data = (await res.json()) as CanvasSummary[]
        setProjects(Array.isArray(data) ? data : [])
      } catch (e) {
        console.error(e)
        setProjects([])
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return projects
    return projects.filter((p) => (p.name || '').toLowerCase().includes(q) || p.id.toLowerCase().includes(q))
  }, [projects, query])

  const createProjectAndEnter = async (firstPrompt?: string) => {
    if (creating) return
    setCreating(true)
    try {
      const id = `canvas-${Date.now()}`
      const nameFromPrompt = (firstPrompt || '').trim().slice(0, 18)
      const payload: CanvasSummary = {
        id,
        name: nameFromPrompt ? `项目：${nameFromPrompt}` : `项目 ${projects.length + 1}`,
        createdAt: Date.now(),
        images: [],
        data: { elements: [], files: {}, },
        messages: [],
      }
      await fetch('/api/canvases', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (firstPrompt && firstPrompt.trim()) {
        sessionStorage.setItem(`pending_prompt:${id}`, firstPrompt.trim())
      }
      setCanvasIdToUrl(id)
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="home">
      <div className="home__bg" />
      <header className="home__header">
        <div className="home__brand">
          <div className="home__logo">生</div>
          <div>
            <div className="home__title">生图Agent</div>
            <div className="home__subtitle">把一句话变成画布上的作品</div>
          </div>
        </div>
      </header>

      <main className="home__main">
        <section className="home__hero">
          <h1 className="home__heroTitle">从问题开始，进入画板创作</h1>
          <p className="home__heroDesc">
            输入你的想法，我们会为你创建一个项目并自动进入画板。生成的图片会按顺序落到画布里。
          </p>

          <div className="home__promptCard">
            <textarea
              className="home__promptInput"
              placeholder="例如：生成一套 12 生肖毛绒吉祥物，每个生肖一张图，统一风格…"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={3}
            />
            <div className="home__promptFooter">
              <div className="home__hint">回车不会提交，点击右侧按钮创建项目并进入画板</div>
              <button
                className="home__btn home__btn--primary"
                onClick={() => createProjectAndEnter(prompt)}
                disabled={creating || !prompt.trim()}
              >
                进入画板
                <ArrowRight size={16} />
              </button>
            </div>
          </div>
        </section>

        <section className="home__list">
          <div className="home__listHeader">
            <div className="home__listTitle">
              <LayoutGrid size={18} />
              历史项目
            </div>
            <div className="home__search">
              <Search size={16} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索项目名 / ID"
              />
            </div>
          </div>

          {loading ? (
            <div className="home__grid">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="home__card home__card--skeleton" />
              ))}
            </div>
          ) : (
            <div className="home__grid">
              {filtered.map((p) => {
                const thumbs = pickThumbnails(p)
                const created = p.createdAt ? new Date(p.createdAt).toLocaleString() : ''
                const n = countImages(p)
                return (
                  <button
                    key={p.id}
                    className="home__card"
                    onClick={() => setCanvasIdToUrl(p.id)}
                    title={p.id}
                  >
                    <div className="home__thumb">
                      {thumbs.length > 0 ? (
                        <div
                          className={`home__thumbGrid home__thumbGrid--${Math.min(thumbs.length, 4)}`}
                          aria-hidden="true"
                        >
                          {thumbs.slice(0, 4).map((src, idx) => (
                            <img key={`${p.id}:${idx}`} className="home__thumbImg" src={src} alt="" />
                          ))}
                        </div>
                      ) : (
                        <div className="home__thumbEmpty">No Preview</div>
                      )}
                    </div>
                    <div className="home__meta">
                      <div className="home__name">{p.name || '未命名项目'}</div>
                      <div className="home__sub">
                        <span className="home__chip">
                          <Clock size={14} />
                          {created || p.id}
                        </span>
                        <span className="home__chip">{n} 张</span>
                      </div>
                    </div>
                  </button>
                )
              })}
              {filtered.length === 0 && (
                <div className="home__empty">
                  没有匹配的项目。试试换个关键词，或者新建一个项目开始创作。
                </div>
              )}
            </div>
          )}
        </section>
      </main>
    </div>
  )
}


