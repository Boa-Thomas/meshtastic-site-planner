import { describe, it, expect } from 'vitest'
import { lookupRasterRssi } from '../rasterLookup'

// ---------------------------------------------------------------------------
// Helper: build a minimal georaster-like object
// ---------------------------------------------------------------------------

function makeRaster(
  opts: {
    xmin?: number
    xmax?: number
    ymin?: number
    ymax?: number
    width?: number
    height?: number
    values?: number[][]
  } = {},
) {
  const {
    xmin = -47.0,
    xmax = -46.0,
    ymin = -24.0,
    ymax = -23.0,
    width = 10,
    height = 10,
    values,
  } = opts

  // Default: uniform pixel value of 127 (midpoint of 0–254)
  const pixelValues = values ?? Array.from({ length: height }, () => Array(width).fill(127))

  return {
    xmin,
    xmax,
    ymin,
    ymax,
    width,
    height,
    values: [pixelValues], // band 0
  }
}

const DEFAULT_DISPLAY = { min_dbm: -130, max_dbm: -80 }

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('lookupRasterRssi', () => {
  it('returns the correct dBm for a pixel value of 127 (midpoint)', () => {
    const raster = makeRaster()
    // lat/lon at the center of the raster
    const lat = -23.5
    const lon = -46.5

    const result = lookupRasterRssi(raster, DEFAULT_DISPLAY, lat, lon)

    // 127/254 * (-80 - (-130)) + (-130) = 0.5 * 50 + (-130) = -105
    expect(result).toBeCloseTo(-105, 0)
  })

  it('returns min_dbm for pixel value 0', () => {
    const row = Array(10).fill(0)
    const raster = makeRaster({ values: Array.from({ length: 10 }, () => [...row]) })
    const result = lookupRasterRssi(raster, DEFAULT_DISPLAY, -23.5, -46.5)
    expect(result).toBeCloseTo(-130, 0)
  })

  it('returns max_dbm for pixel value 254', () => {
    const row = Array(10).fill(254)
    const raster = makeRaster({ values: Array.from({ length: 10 }, () => [...row]) })
    const result = lookupRasterRssi(raster, DEFAULT_DISPLAY, -23.5, -46.5)
    expect(result).toBeCloseTo(-80, 0)
  })

  it('returns null for pixel value 255 (noData)', () => {
    const row = Array(10).fill(255)
    const raster = makeRaster({ values: Array.from({ length: 10 }, () => [...row]) })
    const result = lookupRasterRssi(raster, DEFAULT_DISPLAY, -23.5, -46.5)
    expect(result).toBeNull()
  })

  it('returns null when coordinates are outside the raster bounds', () => {
    const raster = makeRaster()

    // North of ymax
    expect(lookupRasterRssi(raster, DEFAULT_DISPLAY, -22.0, -46.5)).toBeNull()
    // South of ymin
    expect(lookupRasterRssi(raster, DEFAULT_DISPLAY, -25.0, -46.5)).toBeNull()
    // East of xmax
    expect(lookupRasterRssi(raster, DEFAULT_DISPLAY, -23.5, -45.0)).toBeNull()
    // West of xmin
    expect(lookupRasterRssi(raster, DEFAULT_DISPLAY, -23.5, -48.0)).toBeNull()
  })

  it('returns null when raster is null or has no values', () => {
    expect(lookupRasterRssi(null, DEFAULT_DISPLAY, -23.5, -46.5)).toBeNull()
    expect(lookupRasterRssi({ values: [] }, DEFAULT_DISPLAY, -23.5, -46.5)).toBeNull()
    expect(lookupRasterRssi(undefined, DEFAULT_DISPLAY, -23.5, -46.5)).toBeNull()
  })

  it('correctly maps pixel at the top-left corner of the raster', () => {
    // Top-left corner: lat = ymax, lon = xmin
    // The raster row 0 = ymax, col 0 = xmin
    const values = Array.from({ length: 10 }, () => Array(10).fill(127))
    values[0][0] = 200 // top-left pixel
    const raster = makeRaster({ values })

    // Query just inside the top-left corner
    const result = lookupRasterRssi(raster, DEFAULT_DISPLAY, -23.05, -46.95)
    // pixel 200 → -130 + (200/254) * 50 ≈ -90.63
    expect(result).toBeCloseTo(-130 + (200 / 254) * 50, 0)
  })

  it('correctly maps pixel at the bottom-right corner', () => {
    const values = Array.from({ length: 10 }, () => Array(10).fill(127))
    values[9][9] = 50 // bottom-right pixel
    const raster = makeRaster({ values })

    // Query just inside the bottom-right corner
    const result = lookupRasterRssi(raster, DEFAULT_DISPLAY, -23.95, -46.05)
    // pixel 50 → -130 + (50/254) * 50 ≈ -120.16
    expect(result).toBeCloseTo(-130 + (50 / 254) * 50, 0)
  })

  it('uses the provided display min/max range correctly', () => {
    const raster = makeRaster()
    const display = { min_dbm: -100, max_dbm: -60 }
    const result = lookupRasterRssi(raster, display, -23.5, -46.5)

    // pixel 127 → -100 + (127/254) * 40 = -100 + 20 = -80
    expect(result).toBeCloseTo(-80, 0)
  })
})
