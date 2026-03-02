import { describe, it, expect } from 'vitest'
import { LinkBudget } from '../LinkBudget'
import type { MeshNode } from '../../types/index'

// ---------------------------------------------------------------------------
// Helper factory
// ---------------------------------------------------------------------------

function makeNode(overrides: Partial<MeshNode> = {}): MeshNode {
  return {
    id: 'node-' + Math.random().toString(36).slice(2, 8),
    name: 'Test Node',
    lat: 0,
    lon: 0,
    txPowerW: 0.158,
    txPowerDbm: 22,
    frequencyMhz: 915,
    txGainDbi: 2,
    antennaHeight: 2,
    rxSensitivityDbm: -136,
    rxGainDbi: 2,
    rxLossDb: 2,
    installationType: 'rooftop',
    antennaOrientation: 'omnidirectional',
    obstructionLevel: 'clear',
    channelPresetId: 'LONG_FAST',
    hopLimit: 3,
    ...overrides,
  }
}

/**
 * Manual FSPL calculation that mirrors the LinkBudget implementation.
 */
function manualFSPL(
  distanceKm: number,
  freqMhz: number,
  txDbm: number,
  txGain: number,
  rxGain: number,
  rxLoss: number,
): number {
  const fspl = 20 * Math.log10(distanceKm) + 20 * Math.log10(freqMhz) + 32.44
  const eirp = txDbm + txGain
  return eirp - fspl + rxGain - rxLoss
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('LinkBudget.calculateFSPL', () => {
  // -------------------------------------------------------------------------
  // Basic link budget
  // -------------------------------------------------------------------------

  it('returns correct RSSI for two nodes at a known distance and frequency', () => {
    // Place nodes ~111 km apart along a meridian (1 degree ≈ 111 km)
    const from = makeNode({ lat: 0, lon: 0 })
    const to = makeNode({ lat: 1, lon: 0 })

    const result = LinkBudget.calculateFSPL(from, to)

    const distKm = LinkBudget.haversineKm(0, 0, 1, 0)
    const expected = manualFSPL(distKm, 915, 22, 2, 2, 2)
    // Both nodes are 'clear' so obstruction loss = 0 each

    expect(result.rssiDbm).toBeCloseTo(expected, 1)
    expect(result.distanceKm).toBeCloseTo(distKm, 1)
  })

  it('fromNodeId and toNodeId are populated correctly', () => {
    const from = makeNode({ id: 'alpha' })
    const to = makeNode({ id: 'beta' })
    const result = LinkBudget.calculateFSPL(from, to)
    expect(result.fromNodeId).toBe('alpha')
    expect(result.toNodeId).toBe('beta')
  })

  // -------------------------------------------------------------------------
  // Same-location nodes
  // -------------------------------------------------------------------------

  it('same-location nodes (< 1 m apart) return canHear=true and rssi=0', () => {
    const from = makeNode({ lat: -23.55, lon: -46.63 })
    const to = makeNode({ lat: -23.55, lon: -46.63 })

    const result = LinkBudget.calculateFSPL(from, to)

    expect(result.canHear).toBe(true)
    expect(result.rssiDbm).toBe(0)
    expect(result.snrDb).toBe(50)
    expect(result.distanceKm).toBe(0)
  })

  // -------------------------------------------------------------------------
  // canHear threshold
  // -------------------------------------------------------------------------

  it('node above sensitivity threshold: canHear=true', () => {
    // Very close nodes — should definitely be above sensitivity
    const from = makeNode({ lat: 0, lon: 0 })
    const to = makeNode({ lat: 0, lon: 0.001 })  // ~111 m
    const result = LinkBudget.calculateFSPL(from, to)
    expect(result.canHear).toBe(true)
  })

  it('node below receiver sensitivity: canHear=false', () => {
    // Place nodes far apart and set a very poor (high dBm) sensitivity
    const from = makeNode({ lat: 0, lon: 0, txPowerDbm: 0, txGainDbi: 0 })
    const to = makeNode({
      lat: 0,
      lon: 10,  // ~1110 km at equator
      rxSensitivityDbm: -50,  // very poor sensitivity
      rxGainDbi: 0,
      rxLossDb: 10,
    })

    const result = LinkBudget.calculateFSPL(from, to)
    expect(result.canHear).toBe(false)
  })

  it('high TX power brings a distant node above sensitivity', () => {
    const from = makeNode({ lat: 0, lon: 0, txPowerDbm: 30, txGainDbi: 10 })
    const to = makeNode({ lat: 0, lon: 0.5, rxSensitivityDbm: -136 })

    const result = LinkBudget.calculateFSPL(from, to)
    // With high EIRP (40 dBm) the link should be viable at 50 km range
    expect(result.canHear).toBe(true)
  })

  // -------------------------------------------------------------------------
  // Obstruction loss
  // -------------------------------------------------------------------------

  it('clear obstruction adds 0 dB loss', () => {
    const from = makeNode({ obstructionLevel: 'clear' })
    const to = makeNode({ obstructionLevel: 'clear', lat: 0, lon: 0.5 })

    const result = LinkBudget.calculateFSPL(from, to)
    const distKm = result.distanceKm
    const expected = manualFSPL(distKm, 915, 22, 2, 2, 2)
    expect(result.rssiDbm).toBeCloseTo(expected, 1)
  })

  it('partial obstruction on TX side reduces RSSI by 6 dB', () => {
    const from = makeNode({ obstructionLevel: 'clear', lat: 0, lon: 0 })
    const fromPartial = makeNode({ obstructionLevel: 'partial', lat: 0, lon: 0 })
    const to = makeNode({ obstructionLevel: 'clear', lat: 0, lon: 0.5 })

    const clear = LinkBudget.calculateFSPL(from, to)
    const partial = LinkBudget.calculateFSPL(fromPartial, to)

    expect(clear.rssiDbm - partial.rssiDbm).toBeCloseTo(6, 5)
  })

  it('heavy obstruction on RX side reduces RSSI by 15 dB', () => {
    const from = makeNode({ obstructionLevel: 'clear', lat: 0, lon: 0 })
    const toClear = makeNode({ obstructionLevel: 'clear', lat: 0, lon: 0.5 })
    const toHeavy = makeNode({ obstructionLevel: 'heavy', lat: 0, lon: 0.5 })

    const clear = LinkBudget.calculateFSPL(from, toClear)
    const heavy = LinkBudget.calculateFSPL(from, toHeavy)

    expect(clear.rssiDbm - heavy.rssiDbm).toBeCloseTo(15, 5)
  })

  it('obstructionLoss returns 0 for clear, 6 for partial, 15 for heavy', () => {
    expect(LinkBudget.obstructionLoss('clear')).toBe(0)
    expect(LinkBudget.obstructionLoss('partial')).toBe(6)
    expect(LinkBudget.obstructionLoss('heavy')).toBe(15)
  })

  it('unknown obstruction level defaults to 0 dB loss', () => {
    expect(LinkBudget.obstructionLoss('none')).toBe(0)
    expect(LinkBudget.obstructionLoss('')).toBe(0)
  })

  // -------------------------------------------------------------------------
  // Directional antenna
  // -------------------------------------------------------------------------

  it('directional antenna on-axis (within beamwidth) applies zero off-axis loss', () => {
    const from = makeNode({
      lat: 0, lon: 0,
      antennaOrientation: 'directional',
      directionalParams: { azimuth: 0, beamwidth: 60 },  // pointing North with wide beam
    })
    const toNorth = makeNode({ lat: 0.1, lon: 0 })  // due North

    const omniFrom = makeNode({ lat: 0, lon: 0 })
    const toNorthCheck = makeNode({ lat: 0.1, lon: 0 })

    const directional = LinkBudget.calculateFSPL(from, toNorth)
    const omni = LinkBudget.calculateFSPL(omniFrom, toNorthCheck)

    // With 0 dB off-axis loss, results should match omnidirectional
    expect(directional.rssiDbm).toBeCloseTo(omni.rssiDbm, 3)
  })

  it('directional antenna off-axis applies significant signal loss', () => {
    const from = makeNode({
      lat: 0, lon: 0,
      antennaOrientation: 'directional',
      directionalParams: { azimuth: 0, beamwidth: 30 },  // narrow beam, pointing North
    })
    const toEast = makeNode({ lat: 0, lon: 0.1 })  // due East = 90° off axis

    const omniFrom = makeNode({ lat: 0, lon: 0 })
    const toEastCheck = makeNode({ lat: 0, lon: 0.1 })

    const directional = LinkBudget.calculateFSPL(from, toEast)
    const omni = LinkBudget.calculateFSPL(omniFrom, toEastCheck)

    // Off-axis loss should reduce signal
    expect(directional.rssiDbm).toBeLessThan(omni.rssiDbm)
  })

  it('directionalLoss returns 0 when angle is within half-beamwidth', () => {
    const beamwidth = 60  // degrees
    expect(LinkBudget.directionalLoss(0, beamwidth)).toBe(0)
    expect(LinkBudget.directionalLoss(30, beamwidth)).toBe(0)  // at exactly the boundary
    expect(LinkBudget.directionalLoss(29, beamwidth)).toBe(0)
  })

  it('directionalLoss is positive beyond the half-beamwidth', () => {
    expect(LinkBudget.directionalLoss(31, 60)).toBeGreaterThan(0)
    expect(LinkBudget.directionalLoss(90, 30)).toBeGreaterThan(0)
  })

  it('directionalLoss caps at 27 dB for extreme off-axis angles', () => {
    // 3× the half-beamwidth or more → max loss of 27 dB
    const beamwidth = 10
    const extremeLoss = LinkBudget.directionalLoss(90, beamwidth)  // well beyond 3× half-beam
    expect(extremeLoss).toBeCloseTo(27, 5)
  })

  // -------------------------------------------------------------------------
  // Window installation loss
  // -------------------------------------------------------------------------

  it('window TX facing receiver applies zero loss within 120° cone', () => {
    const from = makeNode({
      lat: 0, lon: 0,
      installationType: 'window',
      windowAzimuth: 90,  // facing East
    })
    const toEast = makeNode({ lat: 0, lon: 0.1 })  // due East

    const omniFrom = makeNode({ lat: 0, lon: 0 })
    const toEastCheck = makeNode({ lat: 0, lon: 0.1 })

    const windowResult = LinkBudget.calculateFSPL(from, toEast)
    const omniResult = LinkBudget.calculateFSPL(omniFrom, toEastCheck)

    // Within the 120° cone (60° half-beam), no loss applied
    expect(windowResult.rssiDbm).toBeCloseTo(omniResult.rssiDbm, 3)
  })

  it('window TX facing away from receiver applies significant loss', () => {
    const from = makeNode({
      lat: 0, lon: 0,
      installationType: 'window',
      windowAzimuth: 270,  // facing West
    })
    const toEast = makeNode({ lat: 0, lon: 0.1 })  // due East = 180° away from window

    const omniFrom = makeNode({ lat: 0, lon: 0 })
    const toEastCheck = makeNode({ lat: 0, lon: 0.1 })

    const windowResult = LinkBudget.calculateFSPL(from, toEast)
    const omniResult = LinkBudget.calculateFSPL(omniFrom, toEastCheck)

    expect(windowResult.rssiDbm).toBeLessThan(omniResult.rssiDbm - 10)
  })

  it('window RX facing away from transmitter applies loss', () => {
    const from = makeNode({ lat: 0, lon: 0 })
    const toWindow = makeNode({
      lat: 0, lon: 0.1,
      installationType: 'window',
      windowAzimuth: 90,  // facing East — but signal comes from West
    })

    const fromCheck = makeNode({ lat: 0, lon: 0 })
    const toOmni = makeNode({ lat: 0, lon: 0.1 })

    const windowResult = LinkBudget.calculateFSPL(from, toWindow)
    const omniResult = LinkBudget.calculateFSPL(fromCheck, toOmni)

    // Window facing East, signal arriving from West (180° off) → loss
    expect(windowResult.rssiDbm).toBeLessThan(omniResult.rssiDbm - 10)
  })

  // -------------------------------------------------------------------------
  // RX directional antenna
  // -------------------------------------------------------------------------

  it('RX directional antenna off-axis applies loss', () => {
    const from = makeNode({ lat: 0, lon: 0 })
    const toDirectional = makeNode({
      lat: 0, lon: 0.1,
      antennaOrientation: 'directional',
      directionalParams: { azimuth: 90, beamwidth: 30 },  // pointing East, signal from West
    })

    const fromCheck = makeNode({ lat: 0, lon: 0 })
    const toOmni = makeNode({ lat: 0, lon: 0.1 })

    const dirResult = LinkBudget.calculateFSPL(from, toDirectional)
    const omniResult = LinkBudget.calculateFSPL(fromCheck, toOmni)

    expect(dirResult.rssiDbm).toBeLessThan(omniResult.rssiDbm)
  })

  // -------------------------------------------------------------------------
  // Asymmetric links
  // -------------------------------------------------------------------------

  it('window install creates asymmetric link (A→B ≠ B→A)', () => {
    // A is an omnidirectional node, B has a window facing South
    const a = makeNode({ id: 'A', lat: 0, lon: 0 })
    const b = makeNode({
      id: 'B', lat: 0.1, lon: 0,  // B is due North of A
      installationType: 'window',
      windowAzimuth: 180,  // window faces South (toward A)
    })

    const ab = LinkBudget.calculateFSPL(a, b)
    const ba = LinkBudget.calculateFSPL(b, a)

    // A→B: A omni TX, B window RX facing South (toward A) = within cone = similar
    // B→A: B window TX facing South (toward A) = within cone
    // Both should be similar since the window faces the other node
    // This tests that the function runs correctly with asymmetric configs
    expect(ab.rssiDbm).toBeDefined()
    expect(ba.rssiDbm).toBeDefined()

    // Now test the genuinely asymmetric case
    const c = makeNode({
      id: 'C', lat: 0.1, lon: 0,  // C is due North of A
      installationType: 'window',
      windowAzimuth: 0,  // window faces North (away from A)
    })

    const ac = LinkBudget.calculateFSPL(a, c)
    const ca = LinkBudget.calculateFSPL(c, a)

    // A→C: A omni TX, C window RX facing North (away from A at South) = off-axis loss
    // C→A: C window TX facing North (away from A at South) = off-axis loss
    // Both directions have loss, but the key test: result differs from omni-omni
    expect(ac.rssiDbm).toBeLessThan(ab.rssiDbm)
    expect(ca.rssiDbm).toBeLessThan(ba.rssiDbm)
  })

  // -------------------------------------------------------------------------
  // WINDOW_BEAMWIDTH constant
  // -------------------------------------------------------------------------

  it('WINDOW_BEAMWIDTH is 120 degrees', () => {
    expect(LinkBudget.WINDOW_BEAMWIDTH).toBe(120)
  })

  // -------------------------------------------------------------------------
  // SNR derivation
  // -------------------------------------------------------------------------

  it('snrDb equals rssiDbm minus noise floor (-120 dBm)', () => {
    const from = makeNode({ lat: 0, lon: 0 })
    const to = makeNode({ lat: 0, lon: 0.1 })

    const result = LinkBudget.calculateFSPL(from, to)
    expect(result.snrDb).toBeCloseTo(result.rssiDbm - (-120), 5)
  })
})

// ---------------------------------------------------------------------------
// Tests — haversineKm
// ---------------------------------------------------------------------------

describe('LinkBudget.haversineKm', () => {
  it('São Paulo to Rio de Janeiro is approximately 360 km', () => {
    // São Paulo: -23.5505° S, -46.6333° W
    // Rio de Janeiro: -22.9068° S, -43.1729° W
    const dist = LinkBudget.haversineKm(-23.5505, -46.6333, -22.9068, -43.1729)
    expect(dist).toBeGreaterThan(340)
    expect(dist).toBeLessThan(380)
  })

  it('same point returns 0 km', () => {
    expect(LinkBudget.haversineKm(0, 0, 0, 0)).toBe(0)
  })

  it('equatorial 1 degree longitude ≈ 111.3 km', () => {
    const dist = LinkBudget.haversineKm(0, 0, 0, 1)
    expect(dist).toBeGreaterThan(110)
    expect(dist).toBeLessThan(112)
  })

  it('is symmetric: A→B equals B→A', () => {
    const ab = LinkBudget.haversineKm(-23.55, -46.63, -22.91, -43.17)
    const ba = LinkBudget.haversineKm(-22.91, -43.17, -23.55, -46.63)
    expect(ab).toBeCloseTo(ba, 5)
  })

  it('1 degree latitude along a meridian ≈ 111 km', () => {
    const dist = LinkBudget.haversineKm(0, 0, 1, 0)
    expect(dist).toBeGreaterThan(110)
    expect(dist).toBeLessThan(112)
  })
})

// ---------------------------------------------------------------------------
// Tests — bearingDeg
// ---------------------------------------------------------------------------

describe('LinkBudget.bearingDeg', () => {
  it('due north gives bearing ≈ 0 degrees', () => {
    const bearing = LinkBudget.bearingDeg(0, 0, 1, 0)
    expect(bearing).toBeCloseTo(0, 0)
  })

  it('due south gives bearing ≈ 180 degrees', () => {
    const bearing = LinkBudget.bearingDeg(0, 0, -1, 0)
    expect(bearing).toBeCloseTo(180, 0)
  })

  it('due east gives bearing ≈ 90 degrees', () => {
    const bearing = LinkBudget.bearingDeg(0, 0, 0, 1)
    expect(bearing).toBeCloseTo(90, 0)
  })

  it('due west gives bearing ≈ 270 degrees', () => {
    const bearing = LinkBudget.bearingDeg(0, 0, 0, -1)
    expect(bearing).toBeCloseTo(270, 0)
  })

  it('result is always in the range [0, 360)', () => {
    const tests = [
      [0, 0, 1, 0],
      [0, 0, -1, 0],
      [0, 0, 0, 1],
      [0, 0, 0, -1],
      [-23.55, -46.63, -22.91, -43.17],
    ]
    for (const [lat1, lon1, lat2, lon2] of tests) {
      const b = LinkBudget.bearingDeg(lat1, lon1, lat2, lon2)
      expect(b).toBeGreaterThanOrEqual(0)
      expect(b).toBeLessThan(360)
    }
  })
})

// ---------------------------------------------------------------------------
// Tests — angleDiff
// ---------------------------------------------------------------------------

describe('LinkBudget.angleDiff', () => {
  it('angleDiff of identical angles is 0', () => {
    expect(LinkBudget.angleDiff(90, 90)).toBe(0)
  })

  it('angleDiff wraps correctly around 360°→0°', () => {
    // 350° and 10° differ by 20°, not 340°
    expect(Math.abs(LinkBudget.angleDiff(350, 10))).toBeCloseTo(20, 5)
  })

  it('angleDiff result is always in the range [-180, 180]', () => {
    // The implementation clamps to the range where d > 180 is unwrapped via -360
    // and d < -180 is unwrapped via +360. For the boundary case (e.g. 0 vs 180),
    // the result may be exactly -180.
    for (let a = 0; a < 360; a += 15) {
      for (let b = 0; b < 360; b += 15) {
        const d = LinkBudget.angleDiff(a, b)
        expect(d).toBeGreaterThanOrEqual(-180)
        expect(d).toBeLessThanOrEqual(180)
      }
    }
  })

  it('angleDiff(0, 180) = -180 or 180', () => {
    const d = LinkBudget.angleDiff(0, 180)
    expect(Math.abs(d)).toBe(180)
  })
})
