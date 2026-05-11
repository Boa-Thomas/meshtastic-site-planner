/**
 * Pure utilities for high-resolution map composition.
 * No Vue / Pinia / Leaflet event side-effects -- safe to unit-test.
 */

import L from 'leaflet'
import type { Site } from '../types'

const TILE_SIZE = 256
const MAX_ZOOM = 19

/** Project lat/lng to world pixels at zoom z using Leaflet's Web Mercator CRS. */
export function project(lat: number, lng: number, zoom: number): L.Point {
  return L.CRS.EPSG3857.latLngToPoint(L.latLng(lat, lng), zoom)
}

/** Inverse projection. */
export function unproject(x: number, y: number, zoom: number): L.LatLng {
  return L.CRS.EPSG3857.pointToLatLng(L.point(x, y), zoom)
}

/** Rectangle in world-pixel space at a given zoom. */
export interface WorldRect {
  zoom: number
  x0: number
  y0: number
  x1: number
  y1: number
  width: number
  height: number
}

/** Geographic bounds covered by a `Site`'s raster (computed from raster.values). */
export function tightBoundsForSite(site: Site): L.LatLngBounds | null {
  const raster = site.raster as any
  if (!raster?.values?.[0]) {
    const fallback = (site.rasterLayer as any)?.getBounds?.()
    return fallback ?? null
  }
  const vals = raster.values[0] as number[][]
  const H = raster.height as number
  const W = raster.width as number
  let minR = H
  let maxR = -1
  let minC = W
  let maxC = -1
  for (let r = 0; r < H; r++) {
    const row = vals[r]
    for (let c = 0; c < W; c++) {
      if (row[c] !== 255) {
        if (r < minR) minR = r
        if (r > maxR) maxR = r
        if (c < minC) minC = c
        if (c > maxC) maxC = c
      }
    }
  }
  if (maxR < 0) return null
  const latMax = raster.ymax - minR * raster.pixelHeight
  const latMin = raster.ymax - (maxR + 1) * raster.pixelHeight
  const lngMin = raster.xmin + minC * raster.pixelWidth
  const lngMax = raster.xmin + (maxC + 1) * raster.pixelWidth
  return L.latLngBounds([
    [latMin, lngMin],
    [latMax, lngMax],
  ])
}

/** Combined tight bounds across all visible, non-preview sites with rasters. */
export function tightBoundsForSites(sites: Site[]): L.LatLngBounds | null {
  const out = L.latLngBounds([])
  let any = false
  for (const s of sites) {
    if (!s.visible || s.isPreview) continue
    const b = tightBoundsForSite(s)
    if (b) {
      out.extend(b)
      any = true
    }
  }
  return any ? out : null
}

/**
 * Choose the lowest zoom level whose tile resolution at the centre latitude
 * is finer than (or equal to) the raster's native pixel resolution. Going
 * deeper than that doesn't add information to the overlay -- the basemap may
 * still benefit, which is what `minZoom` is for.
 *
 * native pixel size = pixelWidth (degrees) * 111320 m/deg * cos(lat)
 */
export function autoFitZoom(
  bounds: L.LatLngBounds,
  rasterPixelWidthDeg: number,
  maxZoom = MAX_ZOOM,
  minZoom = 1,
): number {
  const lat = bounds.getCenter().lat
  const metresPerDegLng = 111320 * Math.cos((lat * Math.PI) / 180)
  const rasterMetresPerPixel = Math.abs(rasterPixelWidthDeg) * metresPerDegLng
  const earthCircumference = 40075016.686
  for (let z = 1; z <= maxZoom; z++) {
    const tileMetres = earthCircumference * Math.cos((lat * Math.PI) / 180) / 2 ** z
    const tileMetresPerPixel = tileMetres / TILE_SIZE
    if (tileMetresPerPixel <= rasterMetresPerPixel) {
      return Math.max(z, minZoom)
    }
  }
  return Math.max(maxZoom, minZoom)
}

/** Approximate metres-per-pixel of an OSM/CartoCDN tile at the given lat/zoom. */
export function tileMetresPerPixel(lat: number, zoom: number): number {
  const earthCircumference = 40075016.686
  return (earthCircumference * Math.cos((lat * Math.PI) / 180)) / (TILE_SIZE * 2 ** zoom)
}

/**
 * Human-readable "what will be visible at this zoom" tier. Calibrated against
 * the standard OSM zoom levels: at z=15+ street names start to render in OSM
 * tiles; at z=13-14 only the largest streets appear.
 */
export type DetailTier = 'country' | 'region' | 'city' | 'neighborhood' | 'street' | 'building'

export function detailTierForZoom(zoom: number): DetailTier {
  if (zoom <= 6) return 'country'
  if (zoom <= 9) return 'region'
  if (zoom <= 12) return 'city'
  if (zoom <= 14) return 'neighborhood'
  if (zoom <= 17) return 'street'
  return 'building'
}

export const DETAIL_TIER_LABEL: Record<DetailTier, string> = {
  country: 'country level (no streets visible)',
  region: 'region level (no streets visible)',
  city: 'city level (only main roads)',
  neighborhood: 'neighborhood (main streets only)',
  street: 'street level (street names readable)',
  building: 'building level (very fine detail)',
}

/** Recommended zoom to make street names readable in OSM/Carto tiles. */
export const STREET_READABLE_ZOOM = 15

/** Compute the world-pixel rectangle for the bounds at a given zoom. */
export function worldRectForBounds(bounds: L.LatLngBounds, zoom: number): WorldRect {
  const nw = project(bounds.getNorth(), bounds.getWest(), zoom)
  const se = project(bounds.getSouth(), bounds.getEast(), zoom)
  const x0 = Math.floor(nw.x)
  const y0 = Math.floor(nw.y)
  const x1 = Math.ceil(se.x)
  const y1 = Math.ceil(se.y)
  return {
    zoom,
    x0,
    y0,
    x1,
    y1,
    width: x1 - x0,
    height: y1 - y0,
  }
}

/** Best-effort estimate of an RGBA canvas's memory footprint in MB. */
export function estimateCanvasMB(width: number, height: number): number {
  return (width * height * 4) / (1024 * 1024)
}

/**
 * Decide whether output must be chunked. Conservative: 8000 px on either axis
 * or > 256 MB total triggers chunking.
 */
export interface ChunkPlan {
  cols: number
  rows: number
  chunkWidth: number
  chunkHeight: number
}

export function planChunks(width: number, height: number, maxDim = 8000): ChunkPlan {
  const cols = Math.ceil(width / maxDim)
  const rows = Math.ceil(height / maxDim)
  const chunkWidth = Math.ceil(width / cols)
  const chunkHeight = Math.ceil(height / rows)
  return { cols, rows, chunkWidth, chunkHeight }
}

/** Tile data returned by `fetchTiles` (kept compatible). */
export interface FetchedTile {
  bitmap: ImageBitmap | null
  tx: number
  ty: number
  dx: number
  dy: number
}

/** Build the per-chunk basemap tile specs. */
export function buildTileComposeList(
  tiles: FetchedTile[],
  rect: WorldRect,
  tileSize: number,
): Array<{ bitmap: ImageBitmap; dx: number; dy: number; size: number }> {
  const out: Array<{ bitmap: ImageBitmap; dx: number; dy: number; size: number }> = []
  for (const t of tiles) {
    if (!t.bitmap) continue
    const tileWorldX = t.tx * tileSize
    const tileWorldY = t.ty * tileSize
    out.push({
      bitmap: t.bitmap,
      dx: tileWorldX - rect.x0,
      dy: tileWorldY - rect.y0,
      size: tileSize,
    })
  }
  return out
}

/**
 * Convert the meshNodeMarker SVG (src/layers.ts) into an ImageBitmap once.
 * Cached at module scope.
 */
let markerBitmapPromise: Promise<ImageBitmap> | null = null
const MARKER_SIZE = 20

export function getMarkerBitmap(): Promise<ImageBitmap> {
  if (markerBitmapPromise) return markerBitmapPromise
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20">
    <circle cx="10" cy="10" r="8" fill="#22c55e" stroke="#ffffff" stroke-width="2"/>
    <circle cx="10" cy="10" r="3" fill="#ffffff"/>
  </svg>`
  const blob = new Blob([svg], { type: 'image/svg+xml' })
  markerBitmapPromise = createImageBitmap(blob)
  return markerBitmapPromise
}

export interface MarkerDef {
  lat: number
  lng: number
  label?: string
}

/** Convert geographic markers into worker-ready ComposeMarkers spec. */
export async function buildComposeMarkers(
  markers: MarkerDef[],
  rect: WorldRect,
  options: { iconScale?: number; drawLabels?: boolean } = {},
): Promise<{
  bitmap: ImageBitmap
  size: number
  positions: Array<{ cx: number; cy: number; label?: string }>
} | undefined> {
  if (markers.length === 0) return undefined
  const scale = options.iconScale ?? 1.5
  const drawLabels = options.drawLabels ?? true
  const iconSize = MARKER_SIZE * scale

  const positions: Array<{ cx: number; cy: number; label?: string }> = []
  for (const m of markers) {
    const p = project(m.lat, m.lng, rect.zoom)
    const cx = p.x - rect.x0
    const cy = p.y - rect.y0
    if (cx < -iconSize || cx > rect.width + iconSize) continue
    if (cy < -iconSize || cy > rect.height + iconSize) continue
    positions.push({ cx, cy, label: drawLabels ? m.label : undefined })
  }
  if (positions.length === 0) return undefined

  // Clone the shared marker bitmap so the original stays usable across chunks
  const shared = await getMarkerBitmap()
  const clone = await createImageBitmap(shared)
  return { bitmap: clone, size: iconSize, positions }
}

/** Build attribution spec for compose worker / fallback. */
export function buildComposeAttribution(width: number, layerName: string): {
  text: string
  fontPx: number
  padding: number
} {
  const text =
    layerName === 'Carto Light'
      ? '© OpenStreetMap contributors © CARTO'
      : '© OpenStreetMap contributors'
  const pad = 8
  const fontPx = Math.max(12, Math.round(width / 200))
  return { text, fontPx, padding: pad }
}

export interface ColorbarLayout {
  anchor?: 'bottom-left' | 'bottom-right'
  width?: number
  barHeight?: number
  margin?: number
  fontPx?: number
}

/** Fetch the backend colorbar and build a worker-ready ComposeColorbar spec. */
export async function buildComposeColorbar(
  canvasWidth: number,
  canvasHeight: number,
  colorbarImageUrl: string,
  minDbm: number,
  maxDbm: number,
  layout: ColorbarLayout = {},
): Promise<{
  bitmap: ImageBitmap | null
  x: number
  y: number
  w: number
  h: number
  fontPx: number
  ticks: Array<{ text: string; x: number; align: 'left' | 'center' | 'right' }>
}> {
  const anchor = layout.anchor ?? 'bottom-left'
  const margin = layout.margin ?? 20
  const fontPx = layout.fontPx ?? Math.max(14, Math.round(canvasWidth / 160))
  const barWidth = layout.width ?? Math.min(420, Math.round(canvasWidth * 0.3))
  const barHeight = layout.barHeight ?? Math.max(16, Math.round(fontPx * 1.2))
  const totalH = barHeight + fontPx + 8
  const x = anchor === 'bottom-right' ? canvasWidth - barWidth - margin : margin
  const y = canvasHeight - totalH - margin

  let bitmap: ImageBitmap | null = null
  try {
    const res = await fetch(colorbarImageUrl, { mode: 'cors' })
    if (res.ok) {
      bitmap = await createImageBitmap(await res.blob())
    }
  } catch (err) {
    console.warn('[hiResRenderer] colorbar fetch failed', err)
  }

  const ticks: Array<{ text: string; x: number; align: 'left' | 'center' | 'right' }> = [
    { text: `${Math.round(minDbm)} dBm`, x, align: 'left' },
    { text: `${Math.round((minDbm + maxDbm) / 2)} dBm`, x: x + barWidth / 2, align: 'center' },
    { text: `${Math.round(maxDbm)} dBm`, x: x + barWidth, align: 'right' },
  ]
  return { bitmap, x, y, w: barWidth, h: barHeight, fontPx, ticks }
}
