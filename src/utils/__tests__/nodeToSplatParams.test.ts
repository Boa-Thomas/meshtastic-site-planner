import { describe, it, expect } from 'vitest'
import { nodeToSplatParams, SharedSettings } from '../nodeToSplatParams'
import type { MeshNode } from '../../types/index'

/** Minimal valid MeshNode fixture */
function makeNode(overrides: Partial<MeshNode> = {}): MeshNode {
  return {
    id: 'test-node-id',
    name: 'Test Node',
    lat: -27.0,
    lon: -49.0,
    txPowerW: 0.158,
    txPowerDbm: 22,
    frequencyMhz: 915,
    txGainDbi: 2,
    antennaHeight: 10,
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

const sharedSettings: SharedSettings = {
  environment: {
    radio_climate: 'continental_subtropical',
    polarization: 'vertical',
    clutter_height: 10,
    ground_dielectric: 15,
    ground_conductivity: 0.005,
    atmosphere_bending: 301,
  },
  simulation: {
    situation_fraction: 95,
    time_fraction: 95,
    simulation_extent: 90,
    high_resolution: true,
  },
  display: {
    color_scale: 'plasma',
    min_dbm: -140,
    max_dbm: -60,
    overlay_transparency: 50,
  },
}

describe('nodeToSplatParams', () => {
  // -----------------------------------------------------------------------
  // clutter_height preservation (the main bug fix)
  // -----------------------------------------------------------------------

  it('preserves global clutter_height from shared settings regardless of obstructionLevel', () => {
    for (const level of ['clear', 'partial', 'heavy'] as const) {
      const node = makeNode({ obstructionLevel: level })
      const params = nodeToSplatParams(node, sharedSettings)
      expect(params.environment.clutter_height).toBe(10)
    }
  })

  it('does NOT map obstructionLevel to clutter_height (no per-site override)', () => {
    const clearNode = makeNode({ obstructionLevel: 'clear' })
    const heavyNode = makeNode({ obstructionLevel: 'heavy' })

    const clearParams = nodeToSplatParams(clearNode, sharedSettings)
    const heavyParams = nodeToSplatParams(heavyNode, sharedSettings)

    // Both must use the same global clutter_height
    expect(clearParams.environment.clutter_height).toBe(heavyParams.environment.clutter_height)
  })

  it('uses default clutter_height of 10.0 when no shared settings are provided', () => {
    const node = makeNode({ obstructionLevel: 'clear' })
    const params = nodeToSplatParams(node)
    expect(params.environment.clutter_height).toBe(10.0)
  })

  // -----------------------------------------------------------------------
  // Shared environment pass-through
  // -----------------------------------------------------------------------

  it('passes through all shared environment properties unchanged', () => {
    const node = makeNode()
    const params = nodeToSplatParams(node, sharedSettings)
    expect(params.environment).toEqual(sharedSettings.environment)
  })

  // -----------------------------------------------------------------------
  // Obstruction loss mapping
  // -----------------------------------------------------------------------

  it('adds obstruction loss to rx_loss for partial obstruction', () => {
    const node = makeNode({ obstructionLevel: 'partial', rxLossDb: 2 })
    const params = nodeToSplatParams(node, sharedSettings)
    expect(params.receiver.rx_loss).toBe(2 + 8) // 8 dB extra for partial
  })

  it('adds obstruction loss to rx_loss for heavy obstruction', () => {
    const node = makeNode({ obstructionLevel: 'heavy', rxLossDb: 2 })
    const params = nodeToSplatParams(node, sharedSettings)
    expect(params.receiver.rx_loss).toBe(2 + 20) // 20 dB extra for heavy
  })

  it('adds no extra loss for clear obstruction', () => {
    const node = makeNode({ obstructionLevel: 'clear', rxLossDb: 2 })
    const params = nodeToSplatParams(node, sharedSettings)
    expect(params.receiver.rx_loss).toBe(2)
  })

  // -----------------------------------------------------------------------
  // Installation type height factor
  // -----------------------------------------------------------------------

  it('applies 0.8 height factor for portable installation', () => {
    const node = makeNode({ installationType: 'portable', antennaHeight: 10 })
    const params = nodeToSplatParams(node, sharedSettings)
    expect(params.transmitter.tx_height).toBeCloseTo(8.0)
  })

  it('applies 0.9 height factor for window installation', () => {
    const node = makeNode({ installationType: 'window', antennaHeight: 10 })
    const params = nodeToSplatParams(node, sharedSettings)
    expect(params.transmitter.tx_height).toBeCloseTo(9.0)
  })

  it('applies 1.0 height factor for rooftop installation', () => {
    const node = makeNode({ installationType: 'rooftop', antennaHeight: 10 })
    const params = nodeToSplatParams(node, sharedSettings)
    expect(params.transmitter.tx_height).toBeCloseTo(10.0)
  })

  // -----------------------------------------------------------------------
  // Transmitter/Receiver mapping
  // -----------------------------------------------------------------------

  it('maps node properties to transmitter params correctly', () => {
    const node = makeNode({
      name: 'Cambirela',
      lat: -27.726,
      lon: -48.668,
      txPowerW: 0.158,
      frequencyMhz: 915,
      txGainDbi: 5,
    })
    const params = nodeToSplatParams(node, sharedSettings)
    expect(params.transmitter.name).toBe('Cambirela')
    expect(params.transmitter.tx_lat).toBe(-27.726)
    expect(params.transmitter.tx_lon).toBe(-48.668)
    expect(params.transmitter.tx_power).toBe(0.158)
    expect(params.transmitter.tx_freq).toBe(915)
    expect(params.transmitter.tx_gain).toBe(5)
  })

  it('maps node properties to receiver params correctly', () => {
    const node = makeNode({ rxSensitivityDbm: -136, rxGainDbi: 3, rxLossDb: 1 })
    const params = nodeToSplatParams(node, sharedSettings)
    expect(params.receiver.rx_sensitivity).toBe(-136)
    expect(params.receiver.rx_gain).toBe(3)
    expect(params.receiver.rx_height).toBe(10)
  })

  // -----------------------------------------------------------------------
  // Default fallback (no shared settings)
  // -----------------------------------------------------------------------

  it('uses sensible defaults when no shared settings are provided', () => {
    const node = makeNode()
    const params = nodeToSplatParams(node)
    expect(params.environment.radio_climate).toBe('continental_temperate')
    expect(params.simulation.simulation_extent).toBe(30.0)
    expect(params.display.color_scale).toBe('plasma')
  })
})
