/**
 * Ambient module declarations for packages that ship without TypeScript types.
 *
 * These declarations provide just enough type information for the project to
 * compile cleanly. They can be replaced by upstream @types packages if those
 * ever become available.
 */

// ---------------------------------------------------------------------------
// georaster
// ---------------------------------------------------------------------------
declare module 'georaster' {
  /** Parsed raster metadata and pixel values returned by parseGeoraster(). */
  interface GeoRaster {
    /** Raster height in pixels */
    height: number
    /** Raster width in pixels */
    width: number
    /** Pixel value representing "no data" (typically -9999 or NaN) */
    noDataValue: number
    /** Number of raster bands */
    numberOfRasters: number
    /** Height of a single pixel in geographic units */
    pixelHeight: number
    /** Width of a single pixel in geographic units */
    pixelWidth: number
    /** EPSG projection code (e.g. 4326 for WGS-84) */
    projection: number
    /** Western bounding coordinate */
    xmin: number
    /** Eastern bounding coordinate */
    xmax: number
    /** Southern bounding coordinate */
    ymin: number
    /** Northern bounding coordinate */
    ymax: number
    /**
     * Pixel values indexed as [band][row][col].
     * For GeoTIFFs with a single band this is values[0][row][col].
     */
    values: number[][][]
    /**
     * Optional colour palette for indexed rasters.
     * Each entry is [R, G, B, A] with components in the 0–255 range.
     */
    palette?: Array<[number, number, number, number]>
  }

  /**
   * Parse a raw GeoTIFF ArrayBuffer into a GeoRaster object.
   *
   * @param data - The raw bytes of a GeoTIFF file.
   * @returns A promise that resolves to the parsed raster.
   */
  export default function parseGeoraster(data: ArrayBuffer): Promise<GeoRaster>
}

// ---------------------------------------------------------------------------
// georaster-layer-for-leaflet
// ---------------------------------------------------------------------------
declare module 'georaster-layer-for-leaflet' {
  import type L from 'leaflet'

  /** Options accepted by the GeoRasterLayer constructor. */
  interface GeoRasterLayerOptions extends L.GridLayerOptions {
    /** The parsed GeoRaster object to render. */
    georaster: any
    /** Layer opacity from 0 (transparent) to 1 (opaque). Default: 1. */
    opacity?: number
    /**
     * Internal canvas tile resolution in pixels.
     * Higher values improve visual quality at the cost of performance.
     * Default: 64.
     */
    resolution?: number
    /**
     * Map pixel band values to a CSS colour string.
     * Return `null` to leave the pixel transparent.
     *
     * @param values - Array of band values for the current pixel.
     * @returns A CSS colour string (e.g. `'rgba(255,0,0,0.8)'`) or `null`.
     */
    pixelValuesToColorFn?: (values: number[]) => string | null
  }

  /** Leaflet layer that renders a GeoRaster as a tiled canvas overlay. */
  export default class GeoRasterLayer extends L.GridLayer {
    constructor(options: GeoRasterLayerOptions)
  }
}

// ---------------------------------------------------------------------------
// randanimal
// ---------------------------------------------------------------------------
declare module 'randanimal' {
  /**
   * Synchronously generate a random adjective-animal name string.
   * Useful for generating human-friendly default node names.
   *
   * @returns A hyphenated string such as `'swift-penguin'`.
   */
  export function randanimalSync(): string
}
