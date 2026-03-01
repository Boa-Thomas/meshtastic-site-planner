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
