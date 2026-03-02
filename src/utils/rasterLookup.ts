/**
 * Lookup RSSI value from a GeoRaster at a specific lat/lon coordinate.
 *
 * The raster stores palette-indexed values (0–254), where 255 is noData.
 * This function converts the pixel index back to a dBm value using the
 * same linear mapping that SPLAT! uses when generating the GeoTIFF.
 *
 * @param raster - parsed GeoRaster object (from `georaster`)
 * @param display - display params with min_dbm and max_dbm
 * @param lat - latitude in decimal degrees (WGS-84)
 * @param lon - longitude in decimal degrees (WGS-84)
 * @returns RSSI in dBm, or null if the coordinate is outside the raster or noData
 */
export function lookupRasterRssi(
  raster: any,
  display: { min_dbm: number; max_dbm: number },
  lat: number,
  lon: number,
): number | null {
  if (!raster || !raster.values || raster.values.length === 0) return null

  const { xmin, xmax, ymin, ymax, width, height } = raster

  // Bounds check
  if (lon < xmin || lon > xmax || lat < ymin || lat > ymax) return null

  // Convert lat/lon to pixel indices
  // GeoRaster stores data top-down: row 0 = ymax, row (height-1) = ymin
  const col = Math.floor(((lon - xmin) / (xmax - xmin)) * width)
  const row = Math.floor(((ymax - lat) / (ymax - ymin)) * height)

  // Clamp to valid range
  if (row < 0 || row >= height || col < 0 || col >= width) return null

  // raster.values is [band][row][col] — we use band 0
  const pixel = raster.values[0]?.[row]?.[col]
  if (pixel === undefined || pixel === null || pixel === 255) return null

  // Convert palette index (0–254) back to dBm
  const rssiDbm = display.min_dbm + (pixel / 254) * (display.max_dbm - display.min_dbm)
  return rssiDbm
}
