/**
 * Build an RSSI override map off the main thread when a Worker is available,
 * with a synchronous fallback for environments that don't support Workers
 * (jsdom tests, SSR). Returns the same RssiOverrideMap shape used by the DES
 * engine so callers can swap implementations without other changes.
 */

import { lookupRasterRssi } from './rasterLookup'
import type { MeshNode } from '../types/index'
import type { Site } from '../types/index'
import type { RssiOverrideMap } from '../des'

interface WorkerMessage {
  overrides: { key: string; rssi: number }[]
}

const WORKER_THRESHOLD = 50 // node count above which the worker is worthwhile

function hasWorkerSupport(): boolean {
  return typeof Worker !== 'undefined'
}

function buildSync(nodes: MeshNode[], sites: Site[]): RssiOverrideMap {
  const overrides: RssiOverrideMap = new Map()
  for (const txNode of nodes) {
    if (!txNode.siteId) continue
    const site = sites.find((s) => s.taskId === txNode.siteId)
    if (!site || !site.raster) continue
    const display = site.params.display
    for (const rxNode of nodes) {
      if (rxNode.id === txNode.id) continue
      const rssi = lookupRasterRssi(site.raster, display, rxNode.lat, rxNode.lon)
      if (rssi !== null) {
        overrides.set(`${txNode.id}->${rxNode.id}`, rssi)
      }
    }
  }
  return overrides
}

export async function buildRssiOverrideMapAsync(
  nodes: MeshNode[],
  sites: Site[],
): Promise<RssiOverrideMap> {
  // Skip the worker for small workloads — its setup cost dominates.
  if (!hasWorkerSupport() || nodes.length < WORKER_THRESHOLD) {
    return buildSync(nodes, sites)
  }

  const sitePayloads = nodes
    .filter((n) => n.siteId)
    .map((txNode) => {
      const site = sites.find((s) => s.taskId === txNode.siteId)
      const raster = site?.raster as
        | {
            xmin: number
            xmax: number
            ymin: number
            ymax: number
            width: number
            height: number
            values: number[][][]
          }
        | undefined
      if (!site || !raster) return null
      return {
        txNodeId: txNode.id,
        raster: {
          xmin: raster.xmin,
          xmax: raster.xmax,
          ymin: raster.ymin,
          ymax: raster.ymax,
          width: raster.width,
          height: raster.height,
          values: raster.values[0], // band 0
        },
        minDbm: site.params.display.min_dbm,
        maxDbm: site.params.display.max_dbm,
      }
    })
    .filter((s): s is NonNullable<typeof s> => s !== null)

  if (sitePayloads.length === 0) return new Map()

  const nodePositions = nodes.map((n) => ({ id: n.id, lat: n.lat, lon: n.lon }))

  const worker = new Worker(new URL('../workers/rssiLookup.worker.ts', import.meta.url), {
    type: 'module',
  })

  try {
    const result: RssiOverrideMap = await new Promise((resolve, reject) => {
      worker.onmessage = (e: MessageEvent<WorkerMessage>) => {
        const map: RssiOverrideMap = new Map()
        for (const o of e.data.overrides) map.set(o.key, o.rssi)
        resolve(map)
      }
      worker.onerror = (e) => reject(e)
      worker.postMessage({ sites: sitePayloads, nodes: nodePositions })
    })
    return result
  } finally {
    worker.terminate()
  }
}
