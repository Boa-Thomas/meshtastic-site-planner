// Re-export existing interfaces (kept identical to src/types.ts)
export interface Site {
  params: SplatParams
  taskId: string
  raster: any
  rasterLayer?: any
}

export interface SplatParams {
  transmitter: {
    name: string
    tx_lat: number
    tx_lon: number
    tx_power: number
    tx_freq: number
    tx_height: number
    tx_gain: number
  }
  receiver: {
    rx_sensitivity: number
    rx_height: number
    rx_gain: number
    rx_loss: number
  }
  environment: {
    radio_climate: string
    polarization: string
    clutter_height: number
    ground_dielectric: number
    ground_conductivity: number
    atmosphere_bending: number
  }
  simulation: {
    situation_fraction: number
    time_fraction: number
    simulation_extent: number
    high_resolution: boolean
  }
  display: {
    color_scale: string
    min_dbm: number
    max_dbm: number
    overlay_transparency: number
  }
}

// ---------------------------------------------------------------------------
// Installation / Environment types
// ---------------------------------------------------------------------------

/** Physical installation type for a node antenna */
export type InstallationType = 'mast' | 'rooftop' | 'window' | 'portable' | 'tower'

/** Whether the antenna radiates in all directions or a focused beam */
export type AntennaOrientation = 'omnidirectional' | 'directional'

/** Estimated level of obstruction around the antenna site */
export type ObstructionLevel = 'clear' | 'partial' | 'heavy'

// ---------------------------------------------------------------------------
// Channel / Device / Chipset types
// ---------------------------------------------------------------------------

/** Meshtastic standard channel preset identifiers */
export type ChannelPresetId =
  | 'SHORT_TURBO'
  | 'SHORT_FAST'
  | 'SHORT_SLOW'
  | 'MEDIUM_FAST'
  | 'MEDIUM_SLOW'
  | 'LONG_FAST'
  | 'LONG_MODERATE'
  | 'LONG_SLOW'
  | 'VERY_LONG_SLOW'

/** LoRa radio chipset variants used in common Meshtastic hardware */
export type ChipsetType = 'sx1262' | 'sx1276' | 'sx1268' | 'lr1110'

// ---------------------------------------------------------------------------
// Preset interfaces
// ---------------------------------------------------------------------------

/** A known Meshtastic device with its default RF parameters */
export interface DevicePreset {
  /** Unique identifier for the preset (snake_case, e.g. "heltec_v3") */
  id: string
  /** Human-readable device name */
  name: string
  /** Transmit power in Watts */
  txPowerW: number
  /** Transmit power in dBm */
  txPowerDbm: number
  /** Operating frequency in MHz (region-dependent; stored as 915 for default) */
  frequencyMhz: number
  /** Default antenna gain in dBi (stock antenna) */
  antennaGainDbi: number
  /** Receiver sensitivity in dBm at the configured channel preset */
  rxSensitivityDbm: number
  /** LoRa chipset used in this device */
  chipset: ChipsetType
}

/** A Meshtastic standard LoRa channel configuration */
export interface ChannelPreset {
  /** Unique identifier matching Meshtastic firmware enum */
  id: ChannelPresetId
  /** Human-readable channel name */
  name: string
  /** LoRa Spreading Factor (7–12) */
  sf: number
  /** Bandwidth in kHz (62.5, 125, 250, or 500) */
  bw: number
  /**
   * Coding Rate denominator (5–8).
   * A value of 5 means CR 4/5; 8 means CR 4/8.
   */
  cr: number
  /** Approximate receiver sensitivity in dBm */
  sensitivityDbm: number
  /** Approximate raw LoRa bitrate in bits-per-second */
  bitrateBps: number
}

/** A physical antenna option with gain and radiation pattern */
export interface AntennaPreset {
  /** Unique identifier (snake_case) */
  id: string
  /** Human-readable antenna name */
  name: string
  /** Antenna gain in dBi */
  gainDbi: number
  /** Radiation pattern type */
  type: AntennaOrientation
  /** Half-power beamwidth in degrees — only relevant for directional antennas */
  beamwidthDeg?: number
}

// ---------------------------------------------------------------------------
// MeshNode — central planning entity
// ---------------------------------------------------------------------------

/**
 * Represents a single Meshtastic node on the planning map.
 * Combines location, RF parameters, installation context and optional
 * references to device/channel presets and a SPLAT! simulation result.
 */
export interface MeshNode {
  /** UUID-based unique identifier */
  id: string

  /** Display name for this node */
  name: string

  /** Geographic latitude (decimal degrees, WGS-84) */
  lat: number

  /** Geographic longitude (decimal degrees, WGS-84) */
  lon: number

  // -- TX parameters --------------------------------------------------------

  /** Transmit power in Watts */
  txPowerW: number

  /** Transmit power in dBm */
  txPowerDbm: number

  /** Operating frequency in MHz */
  frequencyMhz: number

  /** Transmitter antenna height above ground level (AGL) in metres */
  txHeight: number

  /** Transmitter antenna gain in dBi */
  txGainDbi: number

  // -- RX parameters --------------------------------------------------------

  /** Receiver sensitivity in dBm (at the active channel preset) */
  rxSensitivityDbm: number

  /** Receiver antenna height AGL in metres */
  rxHeight: number

  /** Receiver antenna gain in dBi */
  rxGainDbi: number

  /** Additional receive-side cable/connector losses in dB */
  rxLossDb: number

  // -- Installation context -------------------------------------------------

  /** How the node/antenna is physically installed */
  installationType: InstallationType

  /** Whether the antenna is omnidirectional or directional */
  antennaOrientation: AntennaOrientation

  /**
   * Directional antenna pointing — only populated when
   * `antennaOrientation === 'directional'`
   */
  directionalParams?: {
    /** Azimuth bearing in degrees (0 = North, clockwise) */
    azimuth: number
    /** Half-power beamwidth in degrees */
    beamwidth: number
  }

  /** Estimated obstruction level at the site */
  obstructionLevel: ObstructionLevel

  // -- Preset references ----------------------------------------------------

  /** ID of the selected DevicePreset, if any */
  devicePresetId?: string

  /** Active Meshtastic channel configuration */
  channelPresetId: ChannelPresetId

  /**
   * Meshtastic hop limit (0–7).
   * Controls how many times a packet may be re-broadcast.
   */
  hopLimit: number

  /**
   * ID of the associated SPLAT! coverage simulation (Site.taskId).
   * Populated after a successful /predict run for this node.
   */
  siteId?: string
}
