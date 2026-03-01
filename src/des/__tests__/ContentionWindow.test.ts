import { describe, it, expect } from 'vitest'
import { ContentionWindow } from '../ContentionWindow'

// ---------------------------------------------------------------------------
// Constants mirrored from the implementation
// ---------------------------------------------------------------------------

const SLOT_TIME_MS = ContentionWindow.SLOT_TIME_MS   // 15
const NUM_SLOTS = ContentionWindow.NUM_SLOTS           // 32
const MAX_DELAY = (NUM_SLOTS - 1) * SLOT_TIME_MS      // 31 * 15 = 465 ms
const DEFAULT_MIN_SNR = -20
const DEFAULT_MAX_SNR = 30

// ---------------------------------------------------------------------------
// Tests — calculateDelayDeterministic
// ---------------------------------------------------------------------------

describe('ContentionWindow.calculateDelayDeterministic', () => {
  it('low SNR (-20 dB, minimum) maps to slot 0 → delay = 0 ms', () => {
    const delay = ContentionWindow.calculateDelayDeterministic(-20)
    expect(delay).toBe(0)
  })

  it('high SNR (30 dB, maximum) maps to slot 31 → delay = 465 ms', () => {
    const delay = ContentionWindow.calculateDelayDeterministic(30)
    expect(delay).toBe(465)
  })

  it('mid SNR (5 dB) produces a delay between 0 and 465 ms', () => {
    const delay = ContentionWindow.calculateDelayDeterministic(5)
    expect(delay).toBeGreaterThan(0)
    expect(delay).toBeLessThan(465)
  })

  it('SNR below minimum clamps to slot 0 → delay = 0 ms', () => {
    expect(ContentionWindow.calculateDelayDeterministic(-50)).toBe(0)
    expect(ContentionWindow.calculateDelayDeterministic(-100)).toBe(0)
    expect(ContentionWindow.calculateDelayDeterministic(-21)).toBe(0)
  })

  it('SNR above maximum clamps to slot 31 → delay = 465 ms', () => {
    expect(ContentionWindow.calculateDelayDeterministic(31)).toBe(MAX_DELAY)
    expect(ContentionWindow.calculateDelayDeterministic(100)).toBe(MAX_DELAY)
    expect(ContentionWindow.calculateDelayDeterministic(30)).toBe(MAX_DELAY)
  })

  it('delay is always a multiple of SLOT_TIME_MS (15 ms)', () => {
    const snrValues = [-20, -15, -10, -5, 0, 5, 10, 15, 20, 25, 30]
    for (const snr of snrValues) {
      const delay = ContentionWindow.calculateDelayDeterministic(snr)
      expect(delay % SLOT_TIME_MS).toBe(0)
    }
  })

  it('delay is monotonically non-decreasing as SNR increases', () => {
    let prev = -Infinity
    for (let snr = DEFAULT_MIN_SNR; snr <= DEFAULT_MAX_SNR; snr += 2) {
      const delay = ContentionWindow.calculateDelayDeterministic(snr)
      expect(delay).toBeGreaterThanOrEqual(prev)
      prev = delay
    }
  })

  it('exactly at SNR = 5 dB falls at the correct slot', () => {
    // normalized = (5 - (-20)) / (30 - (-20)) = 25 / 50 = 0.5
    // slot = floor(0.5 * 31) = 15
    const delay = ContentionWindow.calculateDelayDeterministic(5)
    expect(delay).toBe(15 * SLOT_TIME_MS)  // 225 ms
  })

  it('delay range is [0, 465] — all values are within bounds', () => {
    for (let snr = -30; snr <= 40; snr += 1) {
      const d = ContentionWindow.calculateDelayDeterministic(snr)
      expect(d).toBeGreaterThanOrEqual(0)
      expect(d).toBeLessThanOrEqual(MAX_DELAY)
    }
  })

  it('custom minSnr and maxSnr are respected', () => {
    // With min=0, max=10 and snr=5 → normalized=0.5 → slot=15 → 225 ms
    const delay = ContentionWindow.calculateDelayDeterministic(5, 0, 10)
    expect(delay).toBe(15 * SLOT_TIME_MS)
  })

  it('SNR at exact minimum with custom range returns 0', () => {
    expect(ContentionWindow.calculateDelayDeterministic(0, 0, 10)).toBe(0)
  })

  it('SNR at exact maximum with custom range returns max delay', () => {
    expect(ContentionWindow.calculateDelayDeterministic(10, 0, 10)).toBe(MAX_DELAY)
  })
})

// ---------------------------------------------------------------------------
// Tests — calculateDelay (non-deterministic)
// ---------------------------------------------------------------------------

describe('ContentionWindow.calculateDelay', () => {
  it('delay is always non-negative', () => {
    for (const snr of [-20, -10, 0, 10, 20, 30]) {
      const d = ContentionWindow.calculateDelay(snr)
      expect(d).toBeGreaterThanOrEqual(0)
    }
  })

  it('delay is always bounded above by (MAX_DELAY + SLOT_TIME_MS - epsilon)', () => {
    // Maximum possible: slot 31 * 15 + jitter where jitter < 15
    const maxPossible = MAX_DELAY + SLOT_TIME_MS
    for (let i = 0; i < 50; i++) {
      const d = ContentionWindow.calculateDelay(30)
      expect(d).toBeLessThan(maxPossible)
    }
  })

  it('delay is >= deterministic delay (jitter only adds, never subtracts)', () => {
    // Run several iterations to verify jitter is always additive
    const snrValues = [-20, -10, 0, 5, 15, 25, 30]
    for (const snr of snrValues) {
      const deterministicDelay = ContentionWindow.calculateDelayDeterministic(snr)
      for (let i = 0; i < 20; i++) {
        const stochasticDelay = ContentionWindow.calculateDelay(snr)
        expect(stochasticDelay).toBeGreaterThanOrEqual(deterministicDelay)
      }
    }
  })

  it('at min SNR (-20), delay is in [0, SLOT_TIME_MS)', () => {
    for (let i = 0; i < 20; i++) {
      const d = ContentionWindow.calculateDelay(-20)
      expect(d).toBeGreaterThanOrEqual(0)
      expect(d).toBeLessThan(SLOT_TIME_MS)
    }
  })

  it('at max SNR (30), delay is in [465, 480)', () => {
    for (let i = 0; i < 20; i++) {
      const d = ContentionWindow.calculateDelay(30)
      expect(d).toBeGreaterThanOrEqual(MAX_DELAY)
      expect(d).toBeLessThan(MAX_DELAY + SLOT_TIME_MS)
    }
  })

  it('low-SNR nodes rebroadcast before high-SNR nodes on average', () => {
    // Average over many runs: low SNR should produce shorter delay
    const runs = 100
    let sumLow = 0
    let sumHigh = 0
    for (let i = 0; i < runs; i++) {
      sumLow += ContentionWindow.calculateDelay(-15)   // close to min
      sumHigh += ContentionWindow.calculateDelay(25)   // close to max
    }
    expect(sumLow / runs).toBeLessThan(sumHigh / runs)
  })
})

// ---------------------------------------------------------------------------
// Tests — constants
// ---------------------------------------------------------------------------

describe('ContentionWindow constants', () => {
  it('SLOT_TIME_MS is 15', () => {
    expect(ContentionWindow.SLOT_TIME_MS).toBe(15)
  })

  it('NUM_SLOTS is 32', () => {
    expect(ContentionWindow.NUM_SLOTS).toBe(32)
  })

  it('maximum deterministic delay is 31 * 15 = 465 ms', () => {
    expect((ContentionWindow.NUM_SLOTS - 1) * ContentionWindow.SLOT_TIME_MS).toBe(465)
  })
})
