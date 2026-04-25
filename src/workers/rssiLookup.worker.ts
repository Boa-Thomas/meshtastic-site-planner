/**
 * Web Worker for batched RSSI lookups against SPLAT! coverage rasters.
 *
 * The main thread posts a list of jobs (one per TX site) and node positions;
 * the worker computes lookupRasterRssi for every (tx, rx) pair off-thread and
 * returns a flat array of overrides. This keeps the UI responsive when the
 * mesh has tens of nodes and several rasters.
 *
 * Note: rasterio values are nested arrays (band -> row -> col). Posting them
 * by structured clone is acceptable because they typically fit in a few MB
 * per raster and Workers are pooled per simulation.
 */

interface NodePos {
  id: string
  lat: number
  lon: number
}

interface RasterPayload {
  xmin: number
  xmax: number
  ymin: number
  ymax: number
  width: number
  height: number
  values: number[][] // band 0 only
}

interface SiteJob {
  txNodeId: string
  raster: RasterPayload
  minDbm: number
  maxDbm: number
}

interface WorkerInput {
  sites: SiteJob[]
  nodes: NodePos[]
}

interface RssiOverride {
  key: string // `${txId}->${rxId}`
  rssi: number
}

interface WorkerOutput {
  overrides: RssiOverride[]
}

function lookupRssi(
  raster: RasterPayload,
  minDbm: number,
  maxDbm: number,
  lat: number,
  lon: number,
): number | null {
  const { xmin, xmax, ymin, ymax, width, height, values } = raster
  if (lon < xmin || lon > xmax || lat < ymin || lat > ymax) return null

  const col = Math.floor(((lon - xmin) / (xmax - xmin)) * width)
  const row = Math.floor(((ymax - lat) / (ymax - ymin)) * height)
  if (row < 0 || row >= height || col < 0 || col >= width) return null

  const pixel = values?.[row]?.[col]
  if (pixel === undefined || pixel === null || pixel === 255) return null

  return minDbm + (pixel / 254) * (maxDbm - minDbm)
}

self.onmessage = (event: MessageEvent<WorkerInput>) => {
  const { sites, nodes } = event.data
  const overrides: RssiOverride[] = []

  for (const job of sites) {
    for (const rx of nodes) {
      if (rx.id === job.txNodeId) continue
      const rssi = lookupRssi(job.raster, job.minDbm, job.maxDbm, rx.lat, rx.lon)
      if (rssi !== null) {
        overrides.push({ key: `${job.txNodeId}->${rx.id}`, rssi })
      }
    }
  }

  const out: WorkerOutput = { overrides }
  ;(self as unknown as Worker).postMessage(out)
}

export {}
