import type { MeshNode } from '../types'
import type { LinkInfo, PathLossConfig } from './types'

export class LinkBudget {
  /** Default field of view for a window installation when no cone is configured (degrees). */
  static readonly DEFAULT_WINDOW_BEAMWIDTH = 120

  /**
   * Convert a windowCone { startDeg, endDeg } to { center, beamwidth }.
   * Handles wrap-around (e.g. start=270, end=90 → north-facing window).
   */
  static windowConeToBeam(startDeg: number, endDeg: number): { center: number; beamwidth: number } {
    if (endDeg >= startDeg) {
      return {
        center: (startDeg + endDeg) / 2,
        beamwidth: endDeg - startDeg,
      }
    }
    // Wrap-around case (e.g. 270° → 90°)
    const beamwidth = 360 - startDeg + endDeg
    const center = ((startDeg + endDeg + 360) / 2) % 360
    return { center, beamwidth }
  }

  /**
   * Calculate link budget between two nodes using Free Space Path Loss (FSPL)
   * with optional dual-slope extension for beyond-breakpoint attenuation.
   *
   * When `pathLossConfig` is provided and distance exceeds the breakpoint,
   * a steeper path loss exponent is applied:
   *   d ≤ breakpoint:  FSPL = 20·log10(d) + 20·log10(f) + 32.44
   *   d > breakpoint:  PL = FSPL(bp) + 10·n·log10(d/bp)
   *
   * @param from - transmitting node
   * @param to - receiving node
   * @param pathLossConfig - optional dual-slope parameters (omit for pure FSPL)
   * @returns LinkInfo with RSSI, SNR, distance, and canHear flag
   */
  static calculateFSPL(from: MeshNode, to: MeshNode, pathLossConfig?: PathLossConfig): LinkInfo {
    const distanceKm = LinkBudget.haversineKm(from.lat, from.lon, to.lat, to.lon)

    if (distanceKm < 0.001) {
      // Nodes at essentially the same location
      return {
        fromNodeId: from.id,
        toNodeId: to.id,
        rssiDbm: 0,
        snrDb: 50,
        distanceKm: 0,
        canHear: true,
      }
    }

    // Path loss calculation: pure FSPL or dual-slope
    let pathLoss: number
    const freqLog = 20 * Math.log10(from.frequencyMhz) + 32.44

    if (pathLossConfig && distanceKm > pathLossConfig.breakpointKm) {
      // Dual-slope: FSPL up to breakpoint, then steeper exponent beyond
      const fsplAtBreakpoint = 20 * Math.log10(pathLossConfig.breakpointKm) + freqLog
      pathLoss = fsplAtBreakpoint + 10 * pathLossConfig.pathLossExponent * Math.log10(distanceKm / pathLossConfig.breakpointKm)
    } else {
      // Pure FSPL: 20·log10(d_km) + 20·log10(f_MHz) + 32.44
      pathLoss = 20 * Math.log10(distanceKm) + freqLog
    }
    const fspl = pathLoss

    // EIRP = transmit power (dBm) + transmitter antenna gain (dBi)
    const eirp = from.txPowerDbm + from.txGainDbi

    // Received signal level = EIRP - path loss + RX gain - RX cable losses
    let rssiDbm = eirp - fspl + to.rxGainDbi - to.rxLossDb

    // Apply obstruction losses for both ends of the link
    rssiDbm -= LinkBudget.obstructionLoss(from.obstructionLevel)
    rssiDbm -= LinkBudget.obstructionLoss(to.obstructionLevel)

    // Apply directional antenna off-axis loss for the transmitter
    if (from.antennaOrientation === 'directional' && from.directionalParams) {
      const bearing = LinkBudget.bearingDeg(from.lat, from.lon, to.lat, to.lon)
      const offAxis = Math.abs(
        LinkBudget.angleDiff(bearing, from.directionalParams.azimuth),
      )
      rssiDbm -= LinkBudget.directionalLoss(offAxis, from.directionalParams.beamwidth)
    }

    // Window installation loss for the transmitter (restricted field of view)
    if (from.installationType === 'window') {
      const bearing = LinkBudget.bearingDeg(from.lat, from.lon, to.lat, to.lon)
      if (from.windowCone) {
        const { center, beamwidth } = LinkBudget.windowConeToBeam(from.windowCone.startDeg, from.windowCone.endDeg)
        const offAxis = Math.abs(LinkBudget.angleDiff(bearing, center))
        rssiDbm -= LinkBudget.directionalLoss(offAxis, beamwidth)
      } else {
        // Fallback: no cone configured → no window loss (omnidirectional)
      }
    }

    // Apply directional antenna off-axis loss for the receiver
    if (to.antennaOrientation === 'directional' && to.directionalParams) {
      const bearing = LinkBudget.bearingDeg(to.lat, to.lon, from.lat, from.lon)
      const offAxis = Math.abs(
        LinkBudget.angleDiff(bearing, to.directionalParams.azimuth),
      )
      rssiDbm -= LinkBudget.directionalLoss(offAxis, to.directionalParams.beamwidth)
    }

    // Window installation loss for the receiver (restricted field of view)
    if (to.installationType === 'window') {
      const bearing = LinkBudget.bearingDeg(to.lat, to.lon, from.lat, from.lon)
      if (to.windowCone) {
        const { center, beamwidth } = LinkBudget.windowConeToBeam(to.windowCone.startDeg, to.windowCone.endDeg)
        const offAxis = Math.abs(LinkBudget.angleDiff(bearing, center))
        rssiDbm -= LinkBudget.directionalLoss(offAxis, beamwidth)
      } else {
        // Fallback: no cone configured → no window loss (omnidirectional)
      }
    }

    // SNR approximation: RSSI minus the ambient noise floor
    // Typical LoRa noise floor at room temperature: around -120 dBm
    const noiseFloor = -120
    const snrDb = rssiDbm - noiseFloor

    // A node can hear the transmission if RSSI is above its receiver sensitivity
    const canHear = rssiDbm >= to.rxSensitivityDbm

    return {
      fromNodeId: from.id,
      toNodeId: to.id,
      rssiDbm,
      snrDb,
      distanceKm,
      canHear,
    }
  }

  /**
   * Haversine great-circle distance between two WGS-84 coordinates.
   * @returns distance in kilometres
   */
  static haversineKm(
    lat1: number,
    lon1: number,
    lat2: number,
    lon2: number,
  ): number {
    const R = 6371  // Earth radius in km
    const dLat = ((lat2 - lat1) * Math.PI) / 180
    const dLon = ((lon2 - lon1) * Math.PI) / 180
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos((lat1 * Math.PI) / 180) *
        Math.cos((lat2 * Math.PI) / 180) *
        Math.sin(dLon / 2) ** 2
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  }

  /**
   * Initial bearing from point 1 to point 2.
   * @returns bearing in degrees (0 = North, clockwise)
   */
  static bearingDeg(
    lat1: number,
    lon1: number,
    lat2: number,
    lon2: number,
  ): number {
    const dLon = ((lon2 - lon1) * Math.PI) / 180
    const y =
      Math.sin(dLon) * Math.cos((lat2 * Math.PI) / 180)
    const x =
      Math.cos((lat1 * Math.PI) / 180) * Math.sin((lat2 * Math.PI) / 180) -
      Math.sin((lat1 * Math.PI) / 180) *
        Math.cos((lat2 * Math.PI) / 180) *
        Math.cos(dLon)
    return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360
  }

  /**
   * Smallest signed angular difference between two bearings.
   * Result is in the range (-180, 180].
   */
  static angleDiff(a: number, b: number): number {
    let d = a - b
    while (d > 180) d -= 360
    while (d < -180) d += 360
    return d
  }

  /**
   * Off-axis loss for a directional antenna using a cos² model.
   * Returns 0 dB loss within the main lobe (within half-beamwidth).
   * Loss increases up to ~27 dB for angles 3× the half-beamwidth or more.
   *
   * @param offAxisDeg - angle from the antenna boresight in degrees
   * @param beamwidthDeg - half-power (3 dB) beamwidth in degrees
   * @returns additional path loss in dB
   */
  static directionalLoss(offAxisDeg: number, beamwidthDeg: number): number {
    const halfBeam = beamwidthDeg / 2
    if (offAxisDeg <= halfBeam) return 0

    // cos² model: loss ramps up beyond the half-beamwidth boundary
    const ratio = Math.min((offAxisDeg - halfBeam) / halfBeam, 3)
    return 3 * ratio * ratio  // 0..27 dB
  }

  /**
   * Additional signal loss due to physical obstructions at the antenna site.
   *
   * @param level - obstruction level from MeshNode
   * @returns additional loss in dB
   */
  static obstructionLoss(level: string): number {
    switch (level) {
      case 'partial':
        return 8
      case 'heavy':
        return 20
      default:
        return 0
    }
  }
}
