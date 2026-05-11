/**
 * Parallel basemap-tile fetch with concurrency limit, subdomain rotation,
 * retry on failure, and graceful fallback to a gray placeholder for missing tiles.
 *
 * Only OSM and CartoCDN are CORS-friendly. Other providers (Esri Satellite,
 * OpenTopoMap) will fail the fetch under cross-origin restrictions.
 */

import L from 'leaflet'

/** Templates extracted from src/stores/mapStore.ts.
 *  `{s}` is subdomain, `{z}/{x}/{y}` are tile coords, `{r}` is retina suffix
 *  (`""` or `"@2x"`).
 */
export const TILE_URLS: Record<string, string> = {
  OSM: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  'Carto Light': 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
}

export const CORS_FRIENDLY_LAYERS = new Set(Object.keys(TILE_URLS))

const SUBDOMAINS = ['a', 'b', 'c']

export interface TileGrid {
  zoom: number
  /** Inclusive bounds in tile-index space at this zoom. */
  tx0: number
  ty0: number
  tx1: number
  ty1: number
  cols: number
  rows: number
}

export interface FetchedTile {
  bitmap: ImageBitmap | null
  tx: number
  ty: number
  /** Destination pixel offsets relative to the world-pixel rect at zoom Z. */
  dx: number
  dy: number
}

/** Convert lat/lng to OSM tile coordinates at zoom z. */
export function lngLatToTile(lng: number, lat: number, z: number): { x: number; y: number } {
  const scale = 2 ** z
  const x = ((lng + 180) / 360) * scale
  const sinLat = Math.sin((lat * Math.PI) / 180)
  const y = (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * scale
  return { x, y }
}

/** Compute the tile grid covering the bounds at the requested zoom. */
export function computeTileGrid(bounds: L.LatLngBounds, zoom: number): TileGrid {
  const nw = lngLatToTile(bounds.getWest(), bounds.getNorth(), zoom)
  const se = lngLatToTile(bounds.getEast(), bounds.getSouth(), zoom)
  const tx0 = Math.floor(nw.x)
  const tx1 = Math.floor(se.x)
  const ty0 = Math.floor(nw.y)
  const ty1 = Math.floor(se.y)
  return {
    zoom,
    tx0,
    ty0,
    tx1,
    ty1,
    cols: tx1 - tx0 + 1,
    rows: ty1 - ty0 + 1,
  }
}

function tileUrl(template: string, x: number, y: number, z: number, retina: boolean): string {
  const subIdx = Math.abs(x + y) % SUBDOMAINS.length
  return template
    .replace('{s}', SUBDOMAINS[subIdx])
    .replace('{z}', String(z))
    .replace('{x}', String(x))
    .replace('{y}', String(y))
    .replace('{r}', retina ? '@2x' : '')
}

async function fetchOneTile(
  url: string,
  signal: AbortSignal | undefined,
  retries = 2,
): Promise<ImageBitmap | null> {
  for (let attempt = 0; attempt <= retries; attempt++) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    try {
      const res = await fetch(url, { signal, mode: 'cors' })
      if (!res.ok) {
        if (res.status === 404) return null // tile doesn't exist at this zoom
        throw new Error(`HTTP ${res.status}`)
      }
      const blob = await res.blob()
      return await createImageBitmap(blob)
    } catch (err) {
      if ((err as Error).name === 'AbortError') throw err
      if (attempt === retries) {
        console.warn(`[tileFetch] Failed after ${retries + 1} attempts: ${url}`, err)
        return null
      }
      const backoff = 200 * 2 ** attempt
      await new Promise((r) => setTimeout(r, backoff))
    }
  }
  return null
}

export interface FetchTilesOptions {
  layerName: string
  grid: TileGrid
  retina?: boolean
  concurrency?: number
  signal?: AbortSignal
  onProgress?: (done: number, total: number) => void
}

/**
 * Fetch every tile in the grid as ImageBitmaps using a fixed-concurrency pool.
 * Returns one entry per (tx, ty) including the destination pixel offset.
 */
export async function fetchTiles(opts: FetchTilesOptions): Promise<FetchedTile[]> {
  const template = TILE_URLS[opts.layerName]
  if (!template) {
    throw new Error(`Basemap '${opts.layerName}' is not CORS-friendly for high-res export.`)
  }
  const { grid, retina = false, concurrency = 6, signal, onProgress } = opts
  const tileSize = retina ? 512 : 256

  const tiles: FetchedTile[] = []
  for (let ty = grid.ty0; ty <= grid.ty1; ty++) {
    for (let tx = grid.tx0; tx <= grid.tx1; tx++) {
      tiles.push({
        bitmap: null,
        tx,
        ty,
        dx: (tx - grid.tx0) * tileSize,
        dy: (ty - grid.ty0) * tileSize,
      })
    }
  }

  let done = 0
  let cursor = 0
  const total = tiles.length

  const worker = async () => {
    while (cursor < total) {
      const idx = cursor++
      if (idx >= total) break
      const t = tiles[idx]
      const url = tileUrl(template, t.tx, t.ty, grid.zoom, retina)
      try {
        t.bitmap = await fetchOneTile(url, signal)
      } catch (err) {
        if ((err as Error).name === 'AbortError') throw err
        t.bitmap = null
      }
      done++
      onProgress?.(done, total)
    }
  }

  const workers = Array.from({ length: Math.min(concurrency, total) }, () => worker())
  await Promise.all(workers)
  return tiles
}

/** Paint a gray placeholder for missing tiles. */
export function paintMissingTile(
  ctx: CanvasRenderingContext2D,
  dx: number,
  dy: number,
  size: number,
): void {
  ctx.fillStyle = '#eaeaea'
  ctx.fillRect(dx, dy, size, size)
}
