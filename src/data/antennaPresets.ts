import type { AntennaPreset } from '../types/index'

/**
 * Common antenna options for Meshtastic node planning.
 *
 * Gain values are nominal / manufacturer-rated.
 * beamwidthDeg represents the approximate half-power (3 dB) beamwidth
 * and is only meaningful for directional antennas.
 */
export const antennaPresets: AntennaPreset[] = [
  {
    id: 'stock_stubby',
    name: 'Stock Stubby',
    gainDbi: 1,
    type: 'omnidirectional',
  },
  {
    id: 'stock_whip',
    name: 'Stock Whip (quarter-wave)',
    gainDbi: 2.15,
    type: 'omnidirectional',
  },
  {
    id: 'omni_5dbi',
    name: '5 dBi Omni',
    gainDbi: 5,
    type: 'omnidirectional',
  },
  {
    id: 'omni_6dbi',
    name: '6 dBi Omni',
    gainDbi: 6,
    type: 'omnidirectional',
  },
  {
    id: 'yagi_9dbi',
    name: '9 dBi Yagi',
    gainDbi: 9,
    type: 'directional',
    beamwidthDeg: 60,
  },
  {
    id: 'yagi_12dbi',
    name: '12 dBi Yagi',
    gainDbi: 12,
    type: 'directional',
    beamwidthDeg: 45,
  },
]
