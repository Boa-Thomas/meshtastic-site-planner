import type { DevicePreset } from '../types/index'

/**
 * Catalogue of common Meshtastic-compatible hardware devices with their
 * default RF parameters.
 *
 * Notes:
 * - Frequency values default to the US 915 MHz band. Users should adjust
 *   frequencyMhz to match their regional regulatory allocation.
 * - rxSensitivityDbm is listed for the LONG_FAST channel (SF11 BW250 CR4/5)
 *   which is the Meshtastic firmware default.
 * - txPowerW is derived from txPowerDbm: P(W) = 10^((dBm-30)/10).
 */
export const devicePresets: DevicePreset[] = [
  {
    id: 'heltec_v3',
    name: 'Heltec V3',
    txPowerDbm: 22,
    txPowerW: 0.158,
    frequencyMhz: 915,
    antennaGainDbi: 2,
    rxSensitivityDbm: -136,
    chipset: 'sx1262',
  },
  {
    id: 'rak_wisblock_4631',
    name: 'RAK WisBlock 4631',
    txPowerDbm: 22,
    txPowerW: 0.158,
    frequencyMhz: 915,
    antennaGainDbi: 2,
    rxSensitivityDbm: -136,
    chipset: 'sx1262',
  },
  {
    id: 'tbeam_supreme',
    name: 'T-Beam Supreme',
    txPowerDbm: 22,
    txPowerW: 0.158,
    frequencyMhz: 915,
    antennaGainDbi: 2,
    rxSensitivityDbm: -136,
    chipset: 'sx1262',
  },
  {
    id: 'tbeam_v12',
    name: 'T-Beam v1.2',
    txPowerDbm: 17,
    txPowerW: 0.05,
    frequencyMhz: 915,
    antennaGainDbi: 2,
    rxSensitivityDbm: -136,
    chipset: 'sx1276',
  },
  {
    id: 'techo',
    name: 'T-Echo',
    txPowerDbm: 22,
    txPowerW: 0.158,
    frequencyMhz: 915,
    antennaGainDbi: 1,
    rxSensitivityDbm: -136,
    chipset: 'sx1262',
  },
  {
    id: 'station_g2',
    name: 'Station G2',
    txPowerDbm: 30,
    txPowerW: 1.0,
    frequencyMhz: 915,
    antennaGainDbi: 3,
    rxSensitivityDbm: -136,
    chipset: 'sx1262',
  },
  {
    id: 'rak_wisblock_11310',
    name: 'RAK WisBlock 11310',
    txPowerDbm: 22,
    txPowerW: 0.158,
    frequencyMhz: 915,
    antennaGainDbi: 2,
    rxSensitivityDbm: -136,
    chipset: 'lr1110',
  },
]
