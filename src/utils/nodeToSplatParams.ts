import type { MeshNode, SplatParams } from '../types/index'

/** Environment, simulation and display settings shared across all nodes. */
export interface SharedSettings {
  environment: SplatParams['environment']
  simulation: SplatParams['simulation']
  display: SplatParams['display']
  terrain?: NonNullable<SplatParams['terrain']>
}

// Additional system loss in dB based on obstruction level at the site
const obstructionLossDb: Record<string, number> = {
  clear: 0,
  partial: 8,
  heavy: 20,
}

// Effective height multiplier based on installation type.
// Portable/window installs typically suffer from shadowing and reduced AGL.
const installationHeightFactor: Record<string, number> = {
  portable: 0.8,
  window: 0.9,
  rooftop: 1.0,
  mast: 1.0,
  tower: 1.0,
}

/**
 * Converts a MeshNode planning entity into the SplatParams format expected
 * by the /predict API endpoint.
 *
 * Notable transformations:
 * - txHeight is multiplied by the installation-type height factor
 * - obstructionLevel adds extra system loss on the receiver side
 *
 * Note: clutter_height is an environmental path parameter (average canopy
 * along the propagation path) and comes from shared environment settings.
 * Local obstruction at the site is modelled by obstructionLossDb instead.
 */
export function nodeToSplatParams(node: MeshNode, shared?: SharedSettings): SplatParams {
  const effectiveHeight =
    node.antennaHeight * (installationHeightFactor[node.installationType] ?? 1.0)

  const extraLoss = obstructionLossDb[node.obstructionLevel] ?? 0

  return {
    transmitter: {
      name: node.name,
      tx_lat: node.lat,
      tx_lon: node.lon,
      tx_power: node.txPowerW,
      tx_freq: node.frequencyMhz,
      tx_height: effectiveHeight,
      tx_gain: node.txGainDbi,
    },
    receiver: {
      rx_sensitivity: node.rxSensitivityDbm,
      rx_height: node.antennaHeight,
      rx_gain: node.rxGainDbi,
      rx_loss: node.rxLossDb + extraLoss,
    },
    environment: shared
      ? { ...shared.environment }
      : {
          radio_climate: 'continental_temperate',
          polarization: 'vertical',
          clutter_height: 10.0,
          ground_dielectric: 15.0,
          ground_conductivity: 0.005,
          atmosphere_bending: 301.0,
        },
    simulation: shared?.simulation ?? {
      situation_fraction: 95.0,
      time_fraction: 95.0,
      simulation_extent: 30.0,
      high_resolution: false,
    },
    display: shared?.display ?? {
      color_scale: 'plasma',
      min_dbm: -130.0,
      max_dbm: -80.0,
      overlay_transparency: 50,
    },
    terrain: shared?.terrain ?? {
      dem_source: '',
      clutter_source: '',
      clutter_penetration_factor: null,
    },
  }
}
