import { describe, it, expect } from 'vitest'
import L from 'leaflet'
import {
  autoFitZoom,
  detailTierForZoom,
  DETAIL_TIER_LABEL,
  planChunks,
  project,
  STREET_READABLE_ZOOM,
  tightBoundsForSite,
  tightBoundsForSites,
  tileMetresPerPixel,
  unproject,
  worldRectForBounds,
} from '../hiResRenderer'

// --------------------------------------------------------------------------- //
// Projection                                                                  //
// --------------------------------------------------------------------------- //

describe('project / unproject', () => {
  it('round-trips at common zoom levels', () => {
    for (const z of [3, 8, 12, 16, 19]) {
      for (const [lat, lng] of [
        [0, 0],
        [-23.5, -46.6], // São Paulo
        [40.7, -74.0],  // New York
        [48.85, 2.35],  // Paris
      ]) {
        const p = project(lat, lng, z)
        const ll = unproject(p.x, p.y, z)
        expect(ll.lat).toBeCloseTo(lat, 4)
        expect(ll.lng).toBeCloseTo(lng, 4)
      }
    }
  })

  it('doubles world width per zoom level', () => {
    const z0 = project(0, 180, 0).x
    const z1 = project(0, 180, 1).x
    expect(z1).toBeCloseTo(z0 * 2, 1)
  })
})

// --------------------------------------------------------------------------- //
// autoFitZoom                                                                 //
// --------------------------------------------------------------------------- //

describe('autoFitZoom', () => {
  const bounds = L.latLngBounds([[-23.6, -46.7], [-23.4, -46.5]])

  it('picks higher zooms for finer rasters', () => {
    // 30m raster (HD): smaller pixelWidth in degrees
    const hdZoom = autoFitZoom(bounds, 30 / 111320)
    // 90m raster (default): larger pixelWidth
    const defZoom = autoFitZoom(bounds, 90 / 111320)
    expect(hdZoom).toBeGreaterThan(defZoom)
  })

  it('enforces the minZoom floor (street-readable)', () => {
    // Very coarse raster (huge pixelWidth) -- without floor would pick z<<15
    const z = autoFitZoom(bounds, 0.01, 19, STREET_READABLE_ZOOM)
    expect(z).toBeGreaterThanOrEqual(STREET_READABLE_ZOOM)
  })

  it('respects maxZoom cap', () => {
    // Ultra-fine raster (sub-metre) would otherwise pick z=19+
    const z = autoFitZoom(bounds, 0.0000001, 17)
    expect(z).toBeLessThanOrEqual(17)
  })
})

// --------------------------------------------------------------------------- //
// detailTierForZoom                                                           //
// --------------------------------------------------------------------------- //

describe('detailTierForZoom', () => {
  it('labels common zoom levels correctly', () => {
    expect(detailTierForZoom(5)).toBe('country')
    expect(detailTierForZoom(8)).toBe('region')
    expect(detailTierForZoom(11)).toBe('city')
    expect(detailTierForZoom(13)).toBe('neighborhood')
    expect(detailTierForZoom(16)).toBe('street')
    expect(detailTierForZoom(18)).toBe('building')
  })

  it('labels are non-empty', () => {
    for (const tier of Object.values(DETAIL_TIER_LABEL)) {
      expect(tier).toBeTruthy()
    }
  })
})

// --------------------------------------------------------------------------- //
// tileMetresPerPixel                                                          //
// --------------------------------------------------------------------------- //

describe('tileMetresPerPixel', () => {
  it('halves with each zoom level', () => {
    const a = tileMetresPerPixel(0, 10)
    const b = tileMetresPerPixel(0, 11)
    expect(b).toBeCloseTo(a / 2, 1)
  })

  it('matches the well-known equator zoom 0 value (~156543 m/px)', () => {
    const mpx = tileMetresPerPixel(0, 0)
    expect(mpx).toBeGreaterThan(155000)
    expect(mpx).toBeLessThan(160000)
  })
})

// --------------------------------------------------------------------------- //
// worldRectForBounds                                                          //
// --------------------------------------------------------------------------- //

describe('worldRectForBounds', () => {
  it('produces positive width/height aligned to the zoom', () => {
    const bounds = L.latLngBounds([[-23.6, -46.7], [-23.4, -46.5]])
    const rect = worldRectForBounds(bounds, 12)
    expect(rect.width).toBeGreaterThan(0)
    expect(rect.height).toBeGreaterThan(0)
    expect(rect.zoom).toBe(12)
  })

  it('doubles pixel width per zoom step', () => {
    const bounds = L.latLngBounds([[-23.6, -46.7], [-23.4, -46.5]])
    const r12 = worldRectForBounds(bounds, 12)
    const r13 = worldRectForBounds(bounds, 13)
    // Approximately 2x (rounding may differ by ±2px)
    expect(r13.width).toBeGreaterThan(r12.width * 1.9)
    expect(r13.width).toBeLessThan(r12.width * 2.1)
  })
})

// --------------------------------------------------------------------------- //
// planChunks                                                                  //
// --------------------------------------------------------------------------- //

describe('planChunks', () => {
  it('returns 1x1 when under the limit', () => {
    const plan = planChunks(4000, 3000, 8000)
    expect(plan.cols).toBe(1)
    expect(plan.rows).toBe(1)
  })

  it('splits into chunks when exceeding the limit', () => {
    const plan = planChunks(20000, 12000, 8000)
    expect(plan.cols).toBe(3)
    expect(plan.rows).toBe(2)
    expect(plan.chunkWidth * plan.cols).toBeGreaterThanOrEqual(20000)
  })

  it('handles exact multiples', () => {
    const plan = planChunks(8000, 8000, 8000)
    expect(plan.cols).toBe(1)
    expect(plan.rows).toBe(1)
  })
})

// --------------------------------------------------------------------------- //
// tightBoundsForSite                                                          //
// --------------------------------------------------------------------------- //

function makeSite(values: number[][]) {
  return {
    params: {} as never,
    taskId: 't',
    visible: true,
    raster: {
      values: [values],
      width: values[0].length,
      height: values.length,
      xmin: -46.6,
      xmax: -46.5,
      ymin: -23.6,
      ymax: -23.5,
      pixelWidth: 0.001,
      pixelHeight: 0.001,
    },
  }
}

describe('tightBoundsForSite', () => {
  it('returns null when raster is entirely nodata', () => {
    const site = makeSite([
      [255, 255, 255],
      [255, 255, 255],
      [255, 255, 255],
    ])
    expect(tightBoundsForSite(site as never)).toBeNull()
  })

  it('shrinks bounds to the signal region', () => {
    const site = makeSite([
      [255, 255, 255, 255, 255],
      [255, 255, 100, 100, 255],
      [255, 255, 100, 100, 255],
      [255, 255, 255, 255, 255],
      [255, 255, 255, 255, 255],
    ])
    const b = tightBoundsForSite(site as never)
    expect(b).not.toBeNull()
    expect(b!.isValid()).toBe(true)
    // The signal is at rows 1-2, cols 2-3 -- bounds should be narrower
    // than the full raster bounds.
    expect(b!.getNorth()).toBeLessThan(-23.5)
    expect(b!.getEast()).toBeLessThan(-46.5)
  })
})

describe('tightBoundsForSites', () => {
  it('returns null when no sites have signal', () => {
    const sites = [
      makeSite([[255]]),
      { ...makeSite([[100]]), visible: false },
    ]
    expect(tightBoundsForSites(sites as never)).toBeNull()
  })

  it('skips invisible and preview sites', () => {
    const sites = [
      { ...makeSite([[100]]), visible: false },
      { ...makeSite([[100]]), isPreview: true },
    ]
    expect(tightBoundsForSites(sites as never)).toBeNull()
  })

  it('unions multiple visible sites', () => {
    // Use multi-pixel rasters so the bounding boxes span their full extent.
    const a = makeSite([
      [100, 100, 100],
      [100, 100, 100],
      [100, 100, 100],
    ])
    const b = makeSite([
      [100, 100, 100],
      [100, 100, 100],
      [100, 100, 100],
    ])
    ;(b.raster as any).xmin = -46.4
    ;(b.raster as any).xmax = -46.397
    const u = tightBoundsForSites([a, b] as never)
    expect(u).not.toBeNull()
    expect(u!.getWest()).toBeLessThanOrEqual(-46.6)
    // East should be at least the western edge of B's bounds
    expect(u!.getEast()).toBeGreaterThanOrEqual(-46.4)
  })
})
