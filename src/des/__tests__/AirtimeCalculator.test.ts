import { describe, it, expect } from 'vitest'
import { AirtimeCalculator } from '../AirtimeCalculator'
import { channelPresets } from '../../data/channelPresets'
import type { ChannelPreset } from '../../types/index'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getPreset(id: string): ChannelPreset {
  const p = channelPresets.find((c) => c.id === id)
  if (!p) throw new Error(`Preset not found: ${id}`)
  return p
}

/**
 * Manually computes LoRa airtime using the Semtech formula so we can
 * cross-check the AirtimeCalculator output.
 */
function manualAirtime(
  payloadBytes: number,
  sf: number,
  bwKhz: number,
  cr: number,
  preamble = 8,
  explicit = true,
  crc = true,
): number {
  const bw = bwKhz * 1000
  const de = sf >= 11 && bwKhz <= 125 ? 1 : 0
  const ih = explicit ? 0 : 1
  const crcBit = crc ? 1 : 0
  const tSymbol = (Math.pow(2, sf) / bw) * 1000
  const tPreamble = (preamble + 4.25) * tSymbol
  const num = 8 * payloadBytes - 4 * sf + 28 + 16 * crcBit - 20 * ih
  const den = 4 * (sf - 2 * de)
  const payloadSymbols = 8 + Math.max(0, Math.ceil(num / den) * cr)
  return tPreamble + payloadSymbols * tSymbol
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AirtimeCalculator', () => {
  const SHORT_TURBO = getPreset('SHORT_TURBO')   // SF7 / BW500 / CR5
  const LONG_FAST = getPreset('LONG_FAST')        // SF11 / BW250 / CR5
  const VERY_LONG_SLOW = getPreset('VERY_LONG_SLOW') // SF12 / BW62.5 / CR8

  const PAYLOAD_32 = 32
  const PAYLOAD_200 = 200
  const PAYLOAD_0 = 0

  // -------------------------------------------------------------------------
  // Absolute airtime values for known presets
  // -------------------------------------------------------------------------

  it('SHORT_TURBO (SF7/BW500) airtime for 32-byte payload is less than 50 ms', () => {
    const airtime = AirtimeCalculator.calculate(PAYLOAD_32, SHORT_TURBO)
    expect(airtime).toBeLessThan(50)
    expect(airtime).toBeGreaterThan(0)
  })

  it('LONG_FAST (SF11/BW250) airtime for 32-byte payload is significantly longer than SHORT_TURBO', () => {
    const turboAirtime = AirtimeCalculator.calculate(PAYLOAD_32, SHORT_TURBO)
    const longAirtime = AirtimeCalculator.calculate(PAYLOAD_32, LONG_FAST)
    // LONG_FAST should be at least 5× slower than SHORT_TURBO
    expect(longAirtime).toBeGreaterThan(turboAirtime * 5)
  })

  it('VERY_LONG_SLOW (SF12/BW62.5) produces the longest airtime of the three', () => {
    const turboAirtime = AirtimeCalculator.calculate(PAYLOAD_32, SHORT_TURBO)
    const longAirtime = AirtimeCalculator.calculate(PAYLOAD_32, LONG_FAST)
    const veryLongAirtime = AirtimeCalculator.calculate(PAYLOAD_32, VERY_LONG_SLOW)

    expect(veryLongAirtime).toBeGreaterThan(longAirtime)
    expect(veryLongAirtime).toBeGreaterThan(turboAirtime)
  })

  // -------------------------------------------------------------------------
  // Payload size scaling
  // -------------------------------------------------------------------------

  it('larger payload produces longer airtime (same preset)', () => {
    const small = AirtimeCalculator.calculate(PAYLOAD_32, LONG_FAST)
    const large = AirtimeCalculator.calculate(PAYLOAD_200, LONG_FAST)
    expect(large).toBeGreaterThan(small)
  })

  it('payload scaling is monotonically increasing across the preset range', () => {
    const presets = [SHORT_TURBO, LONG_FAST, VERY_LONG_SLOW]
    for (const preset of presets) {
      const a32 = AirtimeCalculator.calculate(32, preset)
      const a64 = AirtimeCalculator.calculate(64, preset)
      const a128 = AirtimeCalculator.calculate(128, preset)
      expect(a64).toBeGreaterThan(a32)
      expect(a128).toBeGreaterThan(a64)
    }
  })

  // -------------------------------------------------------------------------
  // Zero-byte payload (ACK)
  // -------------------------------------------------------------------------

  it('zero-byte payload (ACK) produces minimal but non-zero airtime', () => {
    const ackAirtime = AirtimeCalculator.calculate(PAYLOAD_0, LONG_FAST)
    expect(ackAirtime).toBeGreaterThan(0)
    // ACK must be shorter than a 32-byte message on same preset
    const dataAirtime = AirtimeCalculator.calculate(PAYLOAD_32, LONG_FAST)
    expect(ackAirtime).toBeLessThan(dataAirtime)
  })

  it('zero-byte ACK airtime is non-zero for SHORT_TURBO as well', () => {
    expect(AirtimeCalculator.calculate(0, SHORT_TURBO)).toBeGreaterThan(0)
  })

  // -------------------------------------------------------------------------
  // Manual formula cross-check
  // -------------------------------------------------------------------------

  it('SHORT_TURBO 32-byte result matches manual Semtech formula', () => {
    const expected = manualAirtime(32, 7, 500, 5)
    const actual = AirtimeCalculator.calculate(32, SHORT_TURBO)
    expect(actual).toBeCloseTo(expected, 3)
  })

  it('LONG_FAST 32-byte result matches manual Semtech formula', () => {
    const expected = manualAirtime(32, 11, 250, 5)
    const actual = AirtimeCalculator.calculate(32, LONG_FAST)
    expect(actual).toBeCloseTo(expected, 3)
  })

  it('VERY_LONG_SLOW 32-byte result matches manual Semtech formula', () => {
    // SF12 / BW62.5 → de=0 because BW=62.5 which is ≤ 125 only when SF >= 11
    // Actually de logic: sf >= 11 && bw <= 125 → de=1
    // VERY_LONG_SLOW: sf=12, bw=62.5 → de=1
    const expected = manualAirtime(32, 12, 62.5, 8)
    const actual = AirtimeCalculator.calculate(32, VERY_LONG_SLOW)
    expect(actual).toBeCloseTo(expected, 3)
  })

  it('LONG_MODERATE uses low data rate optimization (SF11/BW125 → de=1)', () => {
    const LONG_MODERATE = getPreset('LONG_MODERATE')  // SF11 / BW125 / CR8
    const expected = manualAirtime(32, 11, 125, 8)
    const actual = AirtimeCalculator.calculate(32, LONG_MODERATE)
    expect(actual).toBeCloseTo(expected, 3)
  })

  // -------------------------------------------------------------------------
  // Approximate SF doubling rule
  // -------------------------------------------------------------------------

  it('increasing SF by 1 at the same BW roughly doubles the airtime', () => {
    // Compare MEDIUM_FAST (SF9/BW250) vs MEDIUM_SLOW (SF10/BW250)
    const MEDIUM_FAST = getPreset('MEDIUM_FAST')   // SF9 / BW250 / CR5
    const MEDIUM_SLOW = getPreset('MEDIUM_SLOW')   // SF10 / BW250 / CR5

    const at9 = AirtimeCalculator.calculate(32, MEDIUM_FAST)
    const at10 = AirtimeCalculator.calculate(32, MEDIUM_SLOW)

    const ratio = at10 / at9
    // The theoretical ratio is ~2× but with preamble overhead it can differ slightly
    expect(ratio).toBeGreaterThan(1.5)
    expect(ratio).toBeLessThan(3.0)
  })

  it('SHORT_FAST (SF7/BW250) vs SHORT_SLOW (SF8/BW250) airtime roughly doubles', () => {
    const SHORT_FAST = getPreset('SHORT_FAST')   // SF7 / BW250 / CR5
    const SHORT_SLOW = getPreset('SHORT_SLOW')   // SF8 / BW250 / CR5

    const at7 = AirtimeCalculator.calculate(32, SHORT_FAST)
    const at8 = AirtimeCalculator.calculate(32, SHORT_SLOW)

    const ratio = at8 / at7
    expect(ratio).toBeGreaterThan(1.5)
    expect(ratio).toBeLessThan(3.0)
  })

  // -------------------------------------------------------------------------
  // Custom preamble / header options
  // -------------------------------------------------------------------------

  it('implicit header produces shorter airtime than explicit header', () => {
    const explicit = AirtimeCalculator.calculate(32, LONG_FAST, 8, true)
    const implicit = AirtimeCalculator.calculate(32, LONG_FAST, 8, false)
    // Implicit header removes 20 symbols of overhead from the payload count
    expect(implicit).toBeLessThanOrEqual(explicit)
  })

  it('longer preamble produces longer airtime', () => {
    const short = AirtimeCalculator.calculate(32, LONG_FAST, 8)
    const long = AirtimeCalculator.calculate(32, LONG_FAST, 16)
    expect(long).toBeGreaterThan(short)
  })

  // -------------------------------------------------------------------------
  // All channel presets produce positive airtime
  // -------------------------------------------------------------------------

  it('all channel presets produce positive airtime for a 32-byte payload', () => {
    for (const preset of channelPresets) {
      const airtime = AirtimeCalculator.calculate(32, preset)
      expect(airtime).toBeGreaterThan(0)
    }
  })
})
