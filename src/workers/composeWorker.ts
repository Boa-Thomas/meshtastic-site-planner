/// <reference lib="webworker" />
/**
 * Offscreen composition worker.
 *
 * Receives prepared ImageBitmaps for basemap tiles, coverage overlay(s),
 * markers, and colorbar; composes them on an OffscreenCanvas and returns
 * an encoded image Blob via `convertToBlob()`. Running the composition
 * off the main thread keeps the UI responsive during heavy exports
 * (e.g. 8k x 8k canvases where toBlob() can take 1-3 seconds).
 *
 * Sends ImageBitmaps as transferable objects to avoid copies.
 */

export interface ComposeTile {
  bitmap: ImageBitmap
  dx: number
  dy: number
  size: number
}

export interface ComposeOverlay {
  bitmap: ImageBitmap
  dx: number
  dy: number
  w: number
  h: number
}

export interface MarkerPosition {
  cx: number
  cy: number
  label?: string
}

export interface ComposeMarkers {
  /** Shared bitmap reused for every position. */
  bitmap: ImageBitmap
  size: number
  positions: MarkerPosition[]
}

export interface ComposeColorbar {
  bitmap: ImageBitmap | null
  x: number
  y: number
  w: number
  h: number
  fontPx: number
  ticks: Array<{ text: string; x: number; align: 'left' | 'center' | 'right' }>
}

export interface ComposeAttribution {
  text: string
  fontPx: number
  padding: number
  /** Anchor: bottom-right corner of the canvas. */
}

export interface ComposeRequest {
  type: 'compose'
  width: number
  height: number
  background: string
  tiles: ComposeTile[]
  overlays: ComposeOverlay[]
  markers?: ComposeMarkers
  colorbar?: ComposeColorbar
  attribution?: ComposeAttribution
  mime?: string
  quality?: number
}

export interface ComposeResponseSuccess {
  ok: true
  blob: Blob
}

export interface ComposeResponseError {
  ok: false
  error: string
}

export type ComposeResponse = ComposeResponseSuccess | ComposeResponseError

self.addEventListener('message', async (event: MessageEvent<ComposeRequest>) => {
  const msg = event.data
  if (!msg || msg.type !== 'compose') return

  try {
    const canvas = new OffscreenCanvas(msg.width, msg.height)
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('Failed to acquire OffscreenCanvas 2D context.')

    ctx.fillStyle = msg.background || '#ffffff'
    ctx.fillRect(0, 0, msg.width, msg.height)

    // Basemap tiles
    for (const t of msg.tiles) {
      try {
        ctx.drawImage(t.bitmap, t.dx, t.dy, t.size, t.size)
      } catch {
        ctx.fillStyle = '#eaeaea'
        ctx.fillRect(t.dx, t.dy, t.size, t.size)
      }
      try { t.bitmap.close() } catch { /* ignore */ }
    }

    // Coverage overlays
    for (const o of msg.overlays) {
      ctx.drawImage(o.bitmap, o.dx, o.dy, o.w, o.h)
      try { o.bitmap.close() } catch { /* ignore */ }
    }

    // Markers + labels
    if (msg.markers && msg.markers.positions.length > 0) {
      const mk = msg.markers
      const fontPx = Math.max(11, Math.round(mk.size * 0.65))
      ctx.font = `${fontPx}px system-ui, -apple-system, sans-serif`
      ctx.textBaseline = 'top'
      for (const p of mk.positions) {
        ctx.drawImage(mk.bitmap, p.cx - mk.size / 2, p.cy - mk.size / 2, mk.size, mk.size)
        if (p.label) {
          const padding = 4
          const textWidth = ctx.measureText(p.label).width
          const labelX = p.cx + mk.size / 2 + padding
          const labelY = p.cy - fontPx / 2
          ctx.fillStyle = 'rgba(255,255,255,0.85)'
          ctx.fillRect(labelX - 2, labelY - 1, textWidth + 4, fontPx + 2)
          ctx.fillStyle = '#222'
          ctx.fillText(p.label, labelX, labelY)
        }
      }
      try { mk.bitmap.close() } catch { /* ignore */ }
    }

    // Colorbar
    if (msg.colorbar) {
      const cb = msg.colorbar
      ctx.fillStyle = 'rgba(255,255,255,0.85)'
      ctx.fillRect(cb.x - 8, cb.y - 4, cb.w + 16, cb.h + cb.fontPx + 12)
      if (cb.bitmap) {
        ctx.drawImage(cb.bitmap, cb.x, cb.y, cb.w, cb.h)
        try { cb.bitmap.close() } catch { /* ignore */ }
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

    // Attribution
    if (msg.attribution) {
      const a = msg.attribution
      ctx.font = `${a.fontPx}px system-ui, -apple-system, sans-serif`
      const textWidth = ctx.measureText(a.text).width
      const x = msg.width - textWidth - a.padding * 2 - 8
      const y = msg.height - a.fontPx - a.padding - 8
      ctx.fillStyle = 'rgba(255,255,255,0.85)'
      ctx.fillRect(x, y, textWidth + a.padding * 2, a.fontPx + a.padding)
      ctx.fillStyle = '#333'
      ctx.textBaseline = 'top'
      ctx.fillText(a.text, x + a.padding, y + a.padding / 2)
    }

    const blob = await canvas.convertToBlob({
      type: msg.mime ?? 'image/png',
      quality: msg.quality,
    })

    const response: ComposeResponseSuccess = { ok: true, blob }
    ;(self as unknown as DedicatedWorkerGlobalScope).postMessage(response)
  } catch (err) {
    const response: ComposeResponseError = {
      ok: false,
      error: (err as Error).message,
    }
    ;(self as unknown as DedicatedWorkerGlobalScope).postMessage(response)
  }
})

// Keep TypeScript happy in worker context
export {}
