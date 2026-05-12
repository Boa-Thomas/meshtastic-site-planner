/**
 * High-resolution export orchestrator.
 *
 * Pipeline (per `exportHiRes` call):
 *   1. Validate (visible sites with taskId? basemap CORS-friendly?)
 *   2. Compute tight geographic bounds across visible sites
 *   3. Pick output zoom (street-readable floor, fit-overlay, or manual)
 *   4. Compute world-pixel rect for the bounds at that zoom
 *   5. Plan chunks if size exceeds canvas limits
 *   6. For each chunk: build a ComposeRequest (basemap tiles, overlay PNG,
 *      markers, colorbar, attribution) and hand it to the composeRunner
 *      (OffscreenCanvas worker when available, main-thread fallback otherwise).
 *   7. Encode to PNG / PNG-ZIP / PDF and trigger download.
 */

import { ref } from 'vue'
import L from 'leaflet'
import type { Site } from '../types'
import { useMapStore } from '../stores/mapStore'
import { useSitesStore } from '../stores/sitesStore'
import { useNodesStore } from '../stores/nodesStore'
import {
  getRenderPng,
  getRenderMosaicPng,
  getColorbarUrl,
  type RenderResample,
} from '../services/api'
import {
  CORS_FRIENDLY_LAYERS,
  computeTileGrid,
  fetchTiles,
  type TileGrid,
} from '../utils/tileFetch'
import {
  autoFitZoom,
  buildComposeAttribution,
  buildComposeColorbar,
  buildComposeMarkers,
  buildTileComposeList,
  planChunks,
  STREET_READABLE_ZOOM,
  tightBoundsForSites,
  worldRectForBounds,
  type WorldRect,
} from '../services/hiResRenderer'
import { composeOffscreen, type ComposeRequest } from '../services/composeRunner'

const TILE_SIZE = 256

export type HiResFormat = 'png' | 'pdf' | 'png-zip'
export type ResolutionMode = 'street-readable' | 'fit-overlay' | 'manual-width' | 'manual-zoom'

export interface HiResExportOptions {
  format: HiResFormat
  baseLayer?: string
  includeBasemap?: boolean
  includeMarkers?: boolean
  includeColorbar?: boolean
  includeAttribution?: boolean
  resolutionMode?: ResolutionMode
  manualWidth?: number
  manualZoom?: number
  resample?: RenderResample
  retina?: boolean
  jpegQuality?: number
  fileName?: string
  maxDim?: number
}

export type HiResStage =
  | 'idle'
  | 'preparing'
  | 'tiles'
  | 'overlay'
  | 'composite'
  | 'encode'
  | 'done'
  | 'error'

export interface HiResProgress {
  stage: HiResStage
  done: number
  total: number
  pct: number
  message?: string
}

const DEFAULTS = {
  includeBasemap: true,
  includeMarkers: true,
  includeColorbar: true,
  includeAttribution: true,
  resolutionMode: 'street-readable' as ResolutionMode,
  resample: 'lanczos' as RenderResample,
  retina: false,
  jpegQuality: 0.9,
  maxDim: 8000,
} as const

export function useExportHiRes() {
  const loading = ref(false)
  const error = ref('')
  const progress = ref<HiResProgress>({ stage: 'idle', done: 0, total: 0, pct: 0 })
  let controller: AbortController | null = null

  function reset() {
    error.value = ''
    progress.value = { stage: 'idle', done: 0, total: 0, pct: 0 }
  }

  function setStage(stage: HiResStage, message?: string) {
    progress.value = {
      ...progress.value,
      stage,
      message,
      pct: stage === 'done' ? 100 : progress.value.pct,
    }
  }

  function updateProgress(done: number, total: number) {
    const pct = total > 0 ? Math.round((done / total) * 100) : 0
    progress.value = { ...progress.value, done, total, pct }
  }

  function cancel() {
    if (controller) controller.abort()
  }

  async function exportHiRes(opts: HiResExportOptions): Promise<void> {
    const mapStore = useMapStore()
    const sitesStore = useSitesStore()
    const nodesStore = useNodesStore()

    const options = { ...DEFAULTS, ...opts }
    const baseLayer = options.baseLayer ?? mapStore.currentBaseLayer

    if (!CORS_FRIENDLY_LAYERS.has(baseLayer) && options.includeBasemap) {
      error.value = `Basemap '${baseLayer}' is not CORS-friendly. Switch to OSM or Carto Light.`
      return
    }

    const visibleSites = sitesStore.localSites.filter(
      (s) => s.visible && !s.isPreview && s.taskId && s.raster,
    )
    if (visibleSites.length === 0) {
      error.value = 'No visible coverage sites with results to export.'
      return
    }

    reset()
    loading.value = true
    setStage('preparing', 'Computing bounds and resolution...')
    controller = new AbortController()
    const signal = controller.signal

    try {
      const bounds = tightBoundsForSites(visibleSites)
      if (!bounds || !bounds.isValid()) {
        throw new Error('Failed to compute coverage bounds.')
      }

      const zoom = chooseZoom(bounds, visibleSites, options)
      const rect = worldRectForBounds(bounds, zoom)

      if (rect.width <= 0 || rect.height <= 0) {
        throw new Error(`Computed canvas has invalid size ${rect.width}x${rect.height}.`)
      }

      const plan = planChunks(rect.width, rect.height, options.maxDim)
      const chunked = plan.cols > 1 || plan.rows > 1
      const totalChunks = plan.cols * plan.rows
      const chunkBlobs: Array<{ blob: Blob; rect: WorldRect; col: number; row: number }> = []

      for (let row = 0; row < plan.rows; row++) {
        for (let col = 0; col < plan.cols; col++) {
          if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
          const chunkRect = subRect(rect, plan, col, row)
          const chunkIdx = row * plan.cols + col + 1
          const isLastChunk = row === plan.rows - 1 && col === plan.cols - 1

          // --- Phase: basemap tiles ---
          let tileBitmaps: Awaited<ReturnType<typeof fetchTiles>> = []
          if (options.includeBasemap) {
            setStage(
              'tiles',
              chunked
                ? `Chunk ${chunkIdx}/${totalChunks}: fetching basemap tiles...`
                : 'Fetching basemap tiles...',
            )
            tileBitmaps = await fetchBasemapTilesForChunk(
              chunkRect,
              baseLayer,
              options.retina,
              signal,
              updateProgress,
            )
          }

          // --- Phase: coverage overlay ---
          setStage(
            'overlay',
            chunked
              ? `Chunk ${chunkIdx}/${totalChunks}: rendering coverage overlay...`
              : 'Rendering coverage overlay...',
          )
          const overlayBitmap = await fetchOverlayBitmap(
            chunkRect,
            visibleSites,
            sitesStore,
            options.resample,
            signal,
          )

          // --- Phase: decorations (last chunk only) ---
          setStage('composite', isLastChunk ? 'Compositing markers and legend...' : 'Compositing chunk...')

          const tileSize = options.retina ? 512 : TILE_SIZE
          const composeRequest: ComposeRequest = {
            type: 'compose',
            width: chunkRect.width,
            height: chunkRect.height,
            background: '#ffffff',
            tiles: buildTileComposeList(tileBitmaps, chunkRect, tileSize),
            overlays: overlayBitmap
              ? [{ bitmap: overlayBitmap, dx: 0, dy: 0, w: chunkRect.width, h: chunkRect.height }]
              : [],
            mime: 'image/png',
          }

          if (isLastChunk) {
            if (options.includeMarkers) {
              composeRequest.markers = await buildComposeMarkers(
                nodesStore.nodes.map((n) => ({ lat: n.lat, lng: n.lon, label: n.name })),
                chunkRect,
                { iconScale: 1.5, drawLabels: true },
              )
            }
            if (options.includeColorbar) {
              const display = sitesStore.splatParams.display
              composeRequest.colorbar = await buildComposeColorbar(
                chunkRect.width,
                chunkRect.height,
                getColorbarUrl(display.color_scale, display.min_dbm, display.max_dbm, 400, 40),
                display.min_dbm,
                display.max_dbm,
                { anchor: 'bottom-left' },
              )
            }
            if (options.includeAttribution) {
              composeRequest.attribution = buildComposeAttribution(chunkRect.width, baseLayer)
            }
          }

          setStage('encode', `Encoding chunk ${chunkIdx}/${totalChunks}...`)
          const blob = await composeOffscreen(composeRequest, signal)
          chunkBlobs.push({ blob, rect: chunkRect, col, row })
        }
      }

      setStage('encode', 'Building output file...')
      const filename = options.fileName ?? defaultFilename(options.format)

      if (options.format === 'png' && chunkBlobs.length === 1) {
        downloadBlob(chunkBlobs[0].blob, filename)
      } else if (options.format === 'png-zip' || (options.format === 'png' && chunked)) {
        await downloadZip(chunkBlobs, rect, filename, baseLayer, zoom)
      } else if (options.format === 'pdf') {
        await downloadPdf(chunkBlobs, rect, filename, options.jpegQuality)
      } else {
        throw new Error(`Unsupported output combination: ${options.format} (${chunkBlobs.length} chunks)`)
      }

      setStage('done', `Saved ${filename}`)
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        setStage('idle', 'Cancelled')
        error.value = ''
      } else {
        setStage('error', (err as Error).message)
        error.value = (err as Error).message
        console.error('[useExportHiRes]', err)
      }
    } finally {
      loading.value = false
      controller = null
    }
  }

  return { loading, error, progress, exportHiRes, cancel }
}

// --------------------------------------------------------------------------- //
// Helpers                                                                     //
// --------------------------------------------------------------------------- //

function chooseZoom(
  bounds: L.LatLngBounds,
  sites: Site[],
  options: HiResExportOptions,
): number {
  if (options.resolutionMode === 'manual-zoom' && options.manualZoom != null) {
    return clampZoom(options.manualZoom)
  }
  if (options.resolutionMode === 'manual-width' && options.manualWidth) {
    let bestZ = 14
    let bestDiff = Infinity
    for (let z = 1; z <= 19; z++) {
      const rect = worldRectForBounds(bounds, z)
      if (Math.abs(rect.width - options.manualWidth) < bestDiff) {
        bestDiff = Math.abs(rect.width - options.manualWidth)
        bestZ = z
      }
    }
    return clampZoom(bestZ)
  }

  let finestPxDeg = Infinity
  for (const s of sites) {
    const px = (s.raster as any)?.pixelWidth
    if (typeof px === 'number' && px > 0 && px < finestPxDeg) finestPxDeg = px
  }

  if (options.resolutionMode === 'street-readable') {
    const fromRaster = isFinite(finestPxDeg)
      ? autoFitZoom(bounds, finestPxDeg, 19, STREET_READABLE_ZOOM)
      : STREET_READABLE_ZOOM
    return clampZoom(Math.max(fromRaster, STREET_READABLE_ZOOM))
  }

  if (!isFinite(finestPxDeg)) return 14
  return clampZoom(autoFitZoom(bounds, finestPxDeg))
}

function clampZoom(z: number): number {
  return Math.max(1, Math.min(19, Math.round(z)))
}

function subRect(
  rect: WorldRect,
  plan: { cols: number; rows: number; chunkWidth: number; chunkHeight: number },
  col: number,
  row: number,
): WorldRect {
  const x0 = rect.x0 + col * plan.chunkWidth
  const y0 = rect.y0 + row * plan.chunkHeight
  const x1 = col === plan.cols - 1 ? rect.x1 : x0 + plan.chunkWidth
  const y1 = row === plan.rows - 1 ? rect.y1 : y0 + plan.chunkHeight
  return { zoom: rect.zoom, x0, y0, x1, y1, width: x1 - x0, height: y1 - y0 }
}

async function fetchBasemapTilesForChunk(
  rect: WorldRect,
  layerName: string,
  retina: boolean,
  signal: AbortSignal,
  onProgress: (done: number, total: number) => void,
) {
  const grid: TileGrid = computeTileGrid(
    L.latLngBounds(
      L.CRS.EPSG3857.pointToLatLng(L.point(rect.x0, rect.y1), rect.zoom),
      L.CRS.EPSG3857.pointToLatLng(L.point(rect.x1, rect.y0), rect.zoom),
    ),
    rect.zoom,
  )
  return fetchTiles({
    layerName,
    grid,
    retina,
    concurrency: 6,
    signal,
    onProgress,
  })
}

async function fetchOverlayBitmap(
  rect: WorldRect,
  sites: Site[],
  sitesStore: ReturnType<typeof useSitesStore>,
  resample: RenderResample,
  signal: AbortSignal,
): Promise<ImageBitmap | null> {
  const display = sitesStore.splatParams.display
  const opacity = display.overlay_transparency / 100

  const swLL = L.CRS.EPSG3857.pointToLatLng(L.point(rect.x0, rect.y1), rect.zoom)
  const neLL = L.CRS.EPSG3857.pointToLatLng(L.point(rect.x1, rect.y0), rect.zoom)
  const swM = L.CRS.EPSG3857.project(swLL)
  const neM = L.CRS.EPSG3857.project(neLL)
  const bbox3857: [number, number, number, number] = [swM.x, swM.y, neM.x, neM.y]

  const renderOpts = {
    colormap: display.color_scale,
    minDbm: display.min_dbm,
    maxDbm: display.max_dbm,
    opacity,
    srs: 'epsg3857' as const,
    resample,
    width: rect.width,
    bbox: bbox3857,
  }

  if (sites.length > 1) {
    try {
      const { blob } = await getRenderMosaicPng(
        sites.map((s) => s.taskId),
        renderOpts,
        signal,
      )
      return await createImageBitmap(blob)
    } catch (err) {
      if ((err as Error).name === 'AbortError') throw err
      console.warn('[useExportHiRes] Mosaic failed; falling back to per-site fetches:', err)
    }
  }

  // Single-site path (also fallback if mosaic failed)
  if (sites.length === 0) return null
  if (sites.length === 1) {
    try {
      const { blob } = await getRenderPng(sites[0].taskId, renderOpts, signal)
      return await createImageBitmap(blob)
    } catch (err) {
      if ((err as Error).name === 'AbortError') throw err
      console.warn(`[useExportHiRes] Site ${sites[0].taskId} render failed:`, err)
      return null
    }
  }
  // Multi-site fallback when mosaic failed: composite client-side onto an
  // intermediate canvas, then return the result as a single bitmap.
  const c = new OffscreenCanvas(rect.width, rect.height)
  const cctx = c.getContext('2d')
  if (!cctx) return null
  for (const site of sites) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    try {
      const { blob } = await getRenderPng(site.taskId, renderOpts, signal)
      const bmp = await createImageBitmap(blob)
      cctx.drawImage(bmp, 0, 0, rect.width, rect.height)
      bmp.close?.()
    } catch (err) {
      if ((err as Error).name === 'AbortError') throw err
      console.warn(`[useExportHiRes] Site ${site.taskId} render failed:`, err)
    }
  }
  return c.transferToImageBitmap()
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function defaultFilename(format: HiResFormat): string {
  const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
  const ext = format === 'pdf' ? 'pdf' : format === 'png-zip' ? 'zip' : 'png'
  return `coverage-map-${ts}.${ext}`
}

async function downloadZip(
  chunks: Array<{ blob: Blob; rect: WorldRect; col: number; row: number }>,
  fullRect: WorldRect,
  filename: string,
  baseLayer: string,
  zoom: number,
): Promise<void> {
  const { default: JSZip } = await import('jszip')
  const zip = new JSZip()
  const manifest = {
    generated_at: new Date().toISOString(),
    base_layer: baseLayer,
    zoom,
    total_size_px: { width: fullRect.width, height: fullRect.height },
    chunks: chunks.map((c) => {
      const sw = L.CRS.EPSG3857.pointToLatLng(L.point(c.rect.x0, c.rect.y1), c.rect.zoom)
      const ne = L.CRS.EPSG3857.pointToLatLng(L.point(c.rect.x1, c.rect.y0), c.rect.zoom)
      return {
        file: `coverage-r${c.row}-c${c.col}.png`,
        row: c.row,
        col: c.col,
        size_px: { width: c.rect.width, height: c.rect.height },
        offset_px: { x: c.rect.x0 - fullRect.x0, y: c.rect.y0 - fullRect.y0 },
        bounds_4326: { west: sw.lng, south: sw.lat, east: ne.lng, north: ne.lat },
      }
    }),
  }
  zip.file('manifest.json', JSON.stringify(manifest, null, 2))
  for (const c of chunks) {
    zip.file(`coverage-r${c.row}-c${c.col}.png`, c.blob)
  }
  const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' })
  downloadBlob(blob, filename)
}

async function downloadPdf(
  chunks: Array<{ blob: Blob; rect: WorldRect; col: number; row: number }>,
  fullRect: WorldRect,
  filename: string,
  jpegQuality: number,
): Promise<void> {
  const { jsPDF } = await import('jspdf')
  const w = fullRect.width
  const h = fullRect.height
  const pdf = new jsPDF({
    orientation: w >= h ? 'l' : 'p',
    unit: 'px',
    format: [w, h],
  })
  for (const c of chunks) {
    const dataUrl = await blobToDataUrl(c.blob, 'image/jpeg', jpegQuality)
    pdf.addImage(
      dataUrl,
      'JPEG',
      c.rect.x0 - fullRect.x0,
      c.rect.y0 - fullRect.y0,
      c.rect.width,
      c.rect.height,
      undefined,
      'FAST',
    )
  }
  pdf.save(filename)
}

async function blobToDataUrl(blob: Blob, mime: string, quality: number): Promise<string> {
  const bmp = await createImageBitmap(blob)
  const c = document.createElement('canvas')
  c.width = bmp.width
  c.height = bmp.height
  const ctx = c.getContext('2d')!
  ctx.drawImage(bmp, 0, 0)
  bmp.close?.()
  const dataUrl = c.toDataURL(mime, quality)
  c.width = 0
  c.height = 0
  return dataUrl
}
