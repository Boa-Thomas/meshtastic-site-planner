export type EventType =
  | 'message_send'
  | 'message_receive'
  | 'message_rebroadcast'
  | 'ack_send'
  | 'ack_receive'
  | 'collision'
  | 'timeout'
  | 'channel_busy'
  | 'lbt_defer'

export interface SimEvent {
  id: number
  time: number  // milliseconds since simulation start
  type: EventType
  sourceNodeId: string
  targetNodeId?: string
  packet: Packet
}

export interface Packet {
  id: string
  originNodeId: string
  destinationNodeId?: string  // undefined = broadcast
  currentHopCount: number
  maxHopLimit: number
  payloadSizeBytes: number
  snrAtReceiver?: number
  rssiAtReceiver?: number
  isAck: boolean
  retryCount: number
  txStartTime?: number
  txEndTime?: number
  /** Ordered list of node IDs this packet has traversed (origin, relay1, relay2, …) */
  routePath: string[]
}

export interface LinkInfo {
  fromNodeId: string
  toNodeId: string
  rssiDbm: number
  snrDb: number
  distanceKm: number
  canHear: boolean
}

export type RegionId = 'BR_915' | 'US_902' | 'EU_868' | 'EU_433'

export interface SimulationConfig {
  durationMs: number        // max simulation time
  dutyCyclePercent: number  // 100 for US/BR, 10 for EU
  lbtEnabled: boolean       // Listen Before Talk
  lbtThresholdDbm: number   // threshold for channel clear detection
  maxRetransmissions: number // max retries for direct messages (default: 3)
  noiseFloorDbm: number     // ambient noise floor (default: -120)
  region: RegionId
  pathLossConfig?: PathLossConfig  // dual-slope model; omit for pure FSPL (n=2.0)
}

export interface SimulationState {
  currentTimeMs: number
  isRunning: boolean
  eventCount: number
}

export interface SimulationMetrics {
  totalMessagesSent: number
  totalMessagesDelivered: number
  deliveryRatio: number
  averageLatencyMs: number
  maxLatencyMs: number
  averageHopCount: number
  totalCollisions: number
  airtimeByNode: Map<string, number>
  dutyCycleByNode: Map<string, number>
}

/** Map of "fromId->toId" → RSSI in dBm, built from SPLAT! raster data */
export type RssiOverrideMap = Map<string, number>

/** Configuration for dual-slope path loss model. */
export interface PathLossConfig {
  /** Path loss exponent beyond breakpoint (2.0=free space, 3.0=forest, 3.5=dense urban) */
  pathLossExponent: number
  /** Distance in km below which pure FSPL is used */
  breakpointKm: number
}

export type PathLossProfileId = 'free_space' | 'suburban_rural' | 'forest_mountain' | 'dense_urban'

export interface PathLossProfile {
  id: PathLossProfileId
  name: string
  config: PathLossConfig
}

export const PATH_LOSS_PROFILES: PathLossProfile[] = [
  { id: 'free_space', name: 'Free Space (LOS)', config: { pathLossExponent: 2.0, breakpointKm: 1.0 } },
  { id: 'suburban_rural', name: 'Suburban / Rural', config: { pathLossExponent: 2.8, breakpointKm: 1.0 } },
  { id: 'forest_mountain', name: 'Forest / Mountain', config: { pathLossExponent: 3.0, breakpointKm: 1.0 } },
  { id: 'dense_urban', name: 'Dense Urban', config: { pathLossExponent: 3.5, breakpointKm: 0.5 } },
]

// Region defaults
export const REGION_DEFAULTS: Record<RegionId, { frequencyMhz: number; dutyCyclePercent: number }> = {
  BR_915: { frequencyMhz: 915, dutyCyclePercent: 100 },
  US_902: { frequencyMhz: 902, dutyCyclePercent: 100 },
  EU_868: { frequencyMhz: 868, dutyCyclePercent: 10 },
  EU_433: { frequencyMhz: 433, dutyCyclePercent: 10 },
}

export function createDefaultConfig(): SimulationConfig {
  return {
    durationMs: 60_000,  // 1 minute
    dutyCyclePercent: 100,
    lbtEnabled: false,
    lbtThresholdDbm: -90,
    maxRetransmissions: 3,
    noiseFloorDbm: -120,
    region: 'BR_915',
  }
}
