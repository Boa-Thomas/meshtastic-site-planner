/**
 * Routes a compose request to the OffscreenCanvas worker when supported,
 * or runs the equivalent composition on the main thread as a fallback.
 *
 * The worker version keeps the UI responsive for large outputs (>4k px),
 * where toBlob/PNG encoding alone can occupy the main thread for seconds.
 */

import type {
  ComposeRequest,
  ComposeResponse,
} from '../workers/composeWorker'

export type {
  ComposeRequest,
  ComposeMarkers,
  MarkerPosition,
  ComposeColorbar,
  ComposeOverlay,
  ComposeTile,
} from '../workers/composeWorker'

let workerInstance: Worker | null = null
let workerFailed = false

function supportsOffscreen(): boolean {
  return (
    typeof OffscreenCanvas !== 'undefined' &&
    typeof Worker !== 'undefined' &&
    typeof createImageBitmap !== 'undefined'
  )
}

function getOrCreateWorker(): Worker | null {
  if (workerFailed) return null
  if (workerInstance) return workerInstance
  try {
    workerInstance = new Worker(
      new URL('../workers/composeWorker.ts', import.meta.url),
      { type: 'module' },
    )
    return workerInstance
  } catch (err) {
    console.warn('[composeRunner] Failed to spawn worker:', err)
    workerFailed = true
    return null
  }
}

function collectTransferables(req: ComposeRequest): Transferable[] {
  const xs: Transferable[] = []
  for (const t of req.tiles) if (t.bitmap) xs.push(t.bitmap)
  for (const o of req.overlays) if (o.bitmap) xs.push(o.bitmap)
  if (req.markers?.bitmap) xs.push(req.markers.bitmap)
  if (req.colorbar?.bitmap) xs.push(req.colorbar.bitmap)
  return xs
}

/**
 * Compose a chunk by routing through the OffscreenCanvas worker when
 * available. Falls back to main-thread rendering otherwise.
 */
export async function composeOffscreen(
  req: ComposeRequest,
  signal?: AbortSignal,
): Promise<Blob> {
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')

  if (supportsOffscreen()) {
    const worker = getOrCreateWorker()
    if (worker) {
      try {
        return await runInWorker(worker, req, signal)
      } catch (err) {
        console.warn('[composeRunner] Worker run failed; falling back to main thread:', err)
        workerFailed = true
      }
    }
  }
  return composeOnMainThread(req, signal)
}

function runInWorker(worker: Worker, req: ComposeRequest, signal?: AbortSignal): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const onMessage = (event: MessageEvent<ComposeResponse>) => {
      cleanup()
      if (event.data.ok) {
        resolve(event.data.blob)
      } else {
        reject(new Error(event.data.error))
      }
    }
    const onError = (e: ErrorEvent) => {
      cleanup()
      reject(new Error(e.message || 'Worker error'))
    }
    const onAbort = () => {
      cleanup()
      reject(new DOMException('Aborted', 'AbortError'))
    }
    function cleanup() {
      worker.removeEventListener('message', onMessage)
      worker.removeEventListener('error', onError)
      signal?.removeEventListener('abort', onAbort)
    }

    worker.addEventListener('message', onMessage)
    worker.addEventListener('error', onError)
    signal?.addEventListener('abort', onAbort)

    const transferables = collectTransferables(req)
    worker.postMessage(req, transferables)
  })
}

async function composeOnMainThread(req: ComposeRequest, signal?: AbortSignal): Promise<Blob> {
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')

  const canvas = document.createElement('canvas')
  canvas.width = req.width
  canvas.height = req.height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Failed to acquire 2D context.')

  ctx.fillStyle = req.background || '#ffffff'
  ctx.fillRect(0, 0, req.width, req.height)

  for (const t of req.tiles) {
    try {
      ctx.drawImage(t.bitmap, t.dx, t.dy, t.size, t.size)
    } catch {
      ctx.fillStyle = '#eaeaea'
      ctx.fillRect(t.dx, t.dy, t.size, t.size)
    }
    try { t.bitmap.close?.() } catch { /* ignore */ }
  }

  for (const o of req.overlays) {
    ctx.drawImage(o.bitmap, o.dx, o.dy, o.w, o.h)
    try { o.bitmap.close?.() } catch { /* ignore */ }
  }

  if (req.markers && req.markers.positions.length > 0) {
    const mk = req.markers
    const fontPx = Math.max(11, Math.round(mk.size * 0.65))
    ctx.font = `${fontPx}px system-ui, -apple-system, sans-serif`
    ctx.textBaseline = 'top'
    for (const p of mk.positions) {
      ctx.drawImage(mk.bitmap, p.cx - mk.size / 2, p.cy - mk.size / 2, mk.size, mk.size)
      if (p.label) {
        const padding = 4
        const tw = ctx.measureText(p.label).width
        const labelX = p.cx + mk.size / 2 + padding
        const labelY = p.cy - fontPx / 2
        ctx.fillStyle = 'rgba(255,255,255,0.85)'
        ctx.fillRect(labelX - 2, labelY - 1, tw + 4, fontPx + 2)
        ctx.fillStyle = '#222'
        ctx.fillText(p.label, labelX, labelY)
      }
    }
    try { mk.bitmap.close?.() } catch { /* ignore */ }
  }

  if (req.colorbar) {
    const cb = req.colorbar
    ctx.fillStyle = 'rgba(255,255,255,0.85)'
    ctx.fillRect(cb.x - 8, cb.y - 4, cb.w + 16, cb.h + cb.fontPx + 12)
    if (cb.bitmap) {
      ctx.drawImage(cb.bitmap, cb.x, cb.y, cb.w, cb.h)
      try { cb.bitmap.close?.() } catch { /* ignore */ }
    } else {
      ctx.fillStyle = '#999'
      ctx.fillRect(cb.x, cb.y, cb.w, cb.h)
    }
    ctx.fillStyle = '#222'
    ctx.font = `${cb.fontPx}px system-ui, -apple-system, sans-serif`
    ctx.textBaseline = 'top'
    const labelY = cb.y + cb.h + 4
    for (const t of cb.ticks) {
      ctx.textAlign = t.align
      ctx.fillText(t.text, t.x, labelY)
    }
    ctx.textAlign = 'left'
  }

  if (req.attribution) {
    const a = req.attribution
    ctx.font = `${a.fontPx}px system-ui, -apple-system, sans-serif`
    const textWidth = ctx.measureText(a.text).width
    const x = req.width - textWidth - a.padding * 2 - 8
    const y = req.height - a.fontPx - a.padding - 8
    ctx.fillStyle = 'rgba(255,255,255,0.85)'
    ctx.fillRect(x, y, textWidth + a.padding * 2, a.fontPx + a.padding)
    ctx.fillStyle = '#333'
    ctx.textBaseline = 'top'
    ctx.fillText(a.text, x + a.padding, y + a.padding / 2)
  }

  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error('toBlob returned null'))),
      req.mime ?? 'image/png',
      req.quality,
    )
  })
  canvas.width = 0
  canvas.height = 0
  return blob
}

/** Terminate the persistent worker (e.g. on app teardown). */
export function disposeWorker(): void {
  if (workerInstance) {
    workerInstance.terminate()
    workerInstance = null
  }
}
