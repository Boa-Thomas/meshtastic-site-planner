/**
 * Client-side colormap lookup tables.
 *
 * Each colormap is a 256-entry array of [R, G, B] tuples.
 * Index 0 = weakest signal (min dBm), index 254 = strongest signal (max dBm).
 * Index 255 is reserved for noData (transparent).
 *
 * These tables were generated from matplotlib colormaps and are used to apply
 * color to grayscale GeoTIFF data received from the SPLAT! backend.
 */

type RGB = [number, number, number]

// Helper: interpolate between color stops
function interpolateColormap(stops: Array<{ t: number; r: number; g: number; b: number }>): RGB[] {
  const lut: RGB[] = new Array(256)
  for (let i = 0; i < 256; i++) {
    const t = i / 255
    // Find surrounding stops
    let lo = stops[0], hi = stops[stops.length - 1]
    for (let s = 0; s < stops.length - 1; s++) {
      if (t >= stops[s].t && t <= stops[s + 1].t) {
        lo = stops[s]
        hi = stops[s + 1]
        break
      }
    }
    const range = hi.t - lo.t
    const f = range === 0 ? 0 : (t - lo.t) / range
    lut[i] = [
      Math.round(lo.r + f * (hi.r - lo.r)),
      Math.round(lo.g + f * (hi.g - lo.g)),
      Math.round(lo.b + f * (hi.b - lo.b)),
    ]
  }
  return lut
}

// Plasma colormap (perceptually uniform)
const plasma = interpolateColormap([
  { t: 0.0, r: 13, g: 8, b: 135 },
  { t: 0.125, r: 84, g: 2, b: 163 },
  { t: 0.25, r: 139, g: 10, b: 165 },
  { t: 0.375, r: 185, g: 50, b: 137 },
  { t: 0.5, r: 219, g: 92, b: 104 },
  { t: 0.625, r: 244, g: 136, b: 73 },
  { t: 0.75, r: 254, g: 188, b: 43 },
  { t: 0.875, r: 240, g: 249, b: 33 },
  { t: 1.0, r: 240, g: 249, b: 33 },
])

// Viridis colormap (perceptually uniform)
const viridis = interpolateColormap([
  { t: 0.0, r: 68, g: 1, b: 84 },
  { t: 0.125, r: 72, g: 36, b: 117 },
  { t: 0.25, r: 65, g: 68, b: 135 },
  { t: 0.375, r: 53, g: 95, b: 141 },
  { t: 0.5, r: 42, g: 120, b: 142 },
  { t: 0.625, r: 33, g: 145, b: 140 },
  { t: 0.75, r: 53, g: 183, b: 121 },
  { t: 0.875, r: 122, g: 209, b: 81 },
  { t: 1.0, r: 253, g: 231, b: 37 },
])

// Turbo colormap (Google)
const turbo = interpolateColormap([
  { t: 0.0, r: 48, g: 18, b: 59 },
  { t: 0.1, r: 67, g: 62, b: 175 },
  { t: 0.2, r: 44, g: 120, b: 247 },
  { t: 0.3, r: 16, g: 176, b: 218 },
  { t: 0.4, r: 34, g: 221, b: 141 },
  { t: 0.5, r: 121, g: 244, b: 72 },
  { t: 0.6, r: 202, g: 234, b: 44 },
  { t: 0.7, r: 252, g: 196, b: 27 },
  { t: 0.8, r: 249, g: 131, b: 17 },
  { t: 0.9, r: 222, g: 63, b: 6 },
  { t: 1.0, r: 122, g: 4, b: 3 },
])

// Jet colormap (classic rainbow, HSV-based)
const jet = interpolateColormap([
  { t: 0.0, r: 0, g: 0, b: 127 },
  { t: 0.11, r: 0, g: 0, b: 255 },
  { t: 0.125, r: 0, g: 0, b: 255 },
  { t: 0.34, r: 0, g: 255, b: 255 },
  { t: 0.35, r: 0, g: 255, b: 255 },
  { t: 0.5, r: 0, g: 255, b: 0 },
  { t: 0.65, r: 255, g: 255, b: 0 },
  { t: 0.66, r: 255, g: 255, b: 0 },
  { t: 0.89, r: 255, g: 0, b: 0 },
  { t: 1.0, r: 127, g: 0, b: 0 },
])

// Cool colormap (cyan → magenta)
const cool = interpolateColormap([
  { t: 0.0, r: 0, g: 255, b: 255 },
  { t: 1.0, r: 255, g: 0, b: 255 },
])

// Rainbow colormap (matplotlib's rainbow)
const rainbow = interpolateColormap([
  { t: 0.0, r: 128, g: 0, b: 255 },
  { t: 0.167, r: 0, g: 0, b: 255 },
  { t: 0.333, r: 0, g: 255, b: 255 },
  { t: 0.5, r: 0, g: 255, b: 0 },
  { t: 0.667, r: 255, g: 255, b: 0 },
  { t: 0.833, r: 255, g: 128, b: 0 },
  { t: 1.0, r: 255, g: 0, b: 0 },
])

// CMRmap colormap (black → white through blue/red)
const CMRmap = interpolateColormap([
  { t: 0.0, r: 0, g: 0, b: 0 },
  { t: 0.125, r: 21, g: 21, b: 116 },
  { t: 0.25, r: 72, g: 17, b: 170 },
  { t: 0.375, r: 165, g: 21, b: 132 },
  { t: 0.5, r: 214, g: 68, b: 49 },
  { t: 0.625, r: 230, g: 131, b: 16 },
  { t: 0.75, r: 224, g: 205, b: 34 },
  { t: 0.875, r: 231, g: 234, b: 170 },
  { t: 1.0, r: 255, g: 255, b: 255 },
])

const COLORMAPS: Record<string, RGB[]> = {
  plasma,
  viridis,
  turbo,
  jet,
  cool,
  rainbow,
  CMRmap,
}

/**
 * Look up the RGB color for a given normalized value [0, 1] in the specified colormap.
 */
export function colormapLookup(name: string, t: number): RGB {
  const lut = COLORMAPS[name]
  if (!lut) {
    // Fallback: grayscale
    const v = Math.round(t * 255)
    return [v, v, v]
  }
  const idx = Math.max(0, Math.min(254, Math.round(t * 254)))
  return lut[idx]
}

export const AVAILABLE_COLORMAPS = Object.keys(COLORMAPS)
