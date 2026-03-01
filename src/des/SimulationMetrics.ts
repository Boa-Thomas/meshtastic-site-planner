import type { SimEvent, SimulationMetrics, SimulationConfig } from './types'

/** Create a metrics object with all counters zeroed. */
export function createEmptyMetrics(): SimulationMetrics {
  return {
    totalMessagesSent: 0,
    totalMessagesDelivered: 0,
    deliveryRatio: 0,
    averageLatencyMs: 0,
    maxLatencyMs: 0,
    averageHopCount: 0,
    totalCollisions: 0,
    airtimeByNode: new Map(),
    dutyCycleByNode: new Map(),
  }
}

/**
 * Calculate simulation metrics by aggregating all processed events.
 *
 * Latency is measured from the 'message_send' event time to the first
 * 'message_receive' event that represents successful delivery (either
 * the destination node for direct messages, or any node for broadcasts).
 *
 * Airtime is accumulated for all 'message_send' and 'message_rebroadcast'
 * events that carry valid txStartTime/txEndTime fields.
 *
 * @param events - ordered list of all events processed by the engine
 * @param config - simulation configuration (used for duty cycle calculation)
 */
export function calculateMetrics(
  events: SimEvent[],
  config: SimulationConfig,
): SimulationMetrics {
  const metrics = createEmptyMetrics()

  // Map of packet ID → time of the originating send event
  const sendTimes = new Map<string, number>()

  // Per-packet delivery tracking to avoid counting duplicate receives
  const deliveredPackets = new Set<string>()

  const deliveryLatencies: number[] = []
  const deliveredHops: number[] = []

  for (const event of events) {
    switch (event.type) {
      case 'message_send': {
        metrics.totalMessagesSent++
        sendTimes.set(event.packet.id, event.time)

        // Accumulate channel airtime for the sending node
        if (
          event.packet.txStartTime !== undefined &&
          event.packet.txEndTime !== undefined
        ) {
          const airtime = event.packet.txEndTime - event.packet.txStartTime
          const current = metrics.airtimeByNode.get(event.sourceNodeId) ?? 0
          metrics.airtimeByNode.set(event.sourceNodeId, current + airtime)
        }
        break
      }

      case 'message_receive': {
        const pkt = event.packet
        const destinationId = event.targetNodeId

        // Count as delivered when:
        //   - It is a direct message and we are the intended destination, OR
        //   - It is a broadcast (no destinationNodeId) and any receiver counts
        const isDirectDelivery =
          pkt.destinationNodeId !== undefined &&
          pkt.destinationNodeId === destinationId
        const isBroadcastDelivery = pkt.destinationNodeId === undefined

        if (isDirectDelivery || isBroadcastDelivery) {
          // Deduplicate: count each packet delivered to each node only once
          const deliveryKey = `${pkt.id}:${destinationId}`
          if (!deliveredPackets.has(deliveryKey)) {
            deliveredPackets.add(deliveryKey)
            metrics.totalMessagesDelivered++

            const sendTime = sendTimes.get(pkt.id)
            if (sendTime !== undefined) {
              const latency = event.time - sendTime
              deliveryLatencies.push(latency)
              deliveredHops.push(pkt.currentHopCount)
            }
          }
        }
        break
      }

      case 'message_rebroadcast': {
        // Accumulate airtime for rebroadcasting nodes
        if (
          event.packet.txStartTime !== undefined &&
          event.packet.txEndTime !== undefined
        ) {
          const airtime = event.packet.txEndTime - event.packet.txStartTime
          const current = metrics.airtimeByNode.get(event.sourceNodeId) ?? 0
          metrics.airtimeByNode.set(event.sourceNodeId, current + airtime)
        }
        break
      }

      case 'collision': {
        metrics.totalCollisions++
        break
      }
    }
  }

  // Compute aggregate latency statistics
  if (deliveryLatencies.length > 0) {
    metrics.averageLatencyMs =
      deliveryLatencies.reduce((a, b) => a + b, 0) / deliveryLatencies.length
    metrics.maxLatencyMs = Math.max(...deliveryLatencies)
  }

  // Compute average hop count for delivered messages
  if (deliveredHops.length > 0) {
    metrics.averageHopCount =
      deliveredHops.reduce((a, b) => a + b, 0) / deliveredHops.length
  }

  // Delivery ratio: fraction of sent messages that were successfully received
  if (metrics.totalMessagesSent > 0) {
    metrics.deliveryRatio =
      metrics.totalMessagesDelivered / metrics.totalMessagesSent
  }

  // Duty cycle per node: airtime / total simulation duration (as percentage)
  for (const [nodeId, airtime] of metrics.airtimeByNode) {
    metrics.dutyCycleByNode.set(
      nodeId,
      (airtime / config.durationMs) * 100,
    )
  }

  return metrics
}
