import type { MeshNode, ChannelPreset } from '../types'
import type {
  SimEvent,
  Packet,
  SimulationConfig,
  SimulationMetrics,
  LinkInfo,
} from './types'
import { createDefaultConfig } from './types'
import { EventQueue } from './EventQueue'
import { AirtimeCalculator } from './AirtimeCalculator'
import { LinkBudget } from './LinkBudget'
import { ContentionWindow } from './ContentionWindow'
import { ChannelModel } from './ChannelModel'
import { MeshtasticProtocol } from './MeshtasticProtocol'
import { calculateMetrics, createEmptyMetrics } from './SimulationMetrics'

export class SimulationEngine {
  private eventQueue = new EventQueue()
  private channelModel = new ChannelModel()
  private protocol: MeshtasticProtocol
  private eventIdCounter = 0
  private processedEvents: SimEvent[] = []

  private nodes: MeshNode[] = []
  private channelPreset: ChannelPreset
  private config: SimulationConfig
  private currentTimeMs = 0

  /**
   * Link cache computed once at initialisation.
   * Key format: "fromId->toId"
   */
  private linkCache = new Map<string, LinkInfo>()

  /**
   * Optional callback invoked after every processed event.
   * Useful for real-time visualisation or progress reporting.
   */
  onEvent?: (event: SimEvent) => void

  constructor(
    nodes: MeshNode[],
    channelPreset: ChannelPreset,
    config?: Partial<SimulationConfig>,
  ) {
    this.nodes = [...nodes]
    this.channelPreset = channelPreset
    this.config = { ...createDefaultConfig(), ...config }
    this.protocol = new MeshtasticProtocol(this.config)
    this.buildLinkCache()
  }

  // ---------------------------------------------------------------------------
  // Link cache helpers
  // ---------------------------------------------------------------------------

  private buildLinkCache(): void {
    this.linkCache.clear()
    for (const from of this.nodes) {
      for (const to of this.nodes) {
        if (from.id === to.id) continue
        const key = `${from.id}->${to.id}`
        this.linkCache.set(key, LinkBudget.calculateFSPL(from, to))
      }
    }
  }

  private getLink(fromId: string, toId: string): LinkInfo | undefined {
    return this.linkCache.get(`${fromId}->${toId}`)
  }

  // ---------------------------------------------------------------------------
  // Internal utilities
  // ---------------------------------------------------------------------------

  private nextEventId(): number {
    return ++this.eventIdCounter
  }

  /**
   * Enqueue an event only if it falls within the simulation time window.
   */
  private scheduleEvent(event: SimEvent): void {
    if (event.time <= this.config.durationMs) {
      this.eventQueue.insert(event)
    }
  }

  // ---------------------------------------------------------------------------
  // Public API — message injection
  // ---------------------------------------------------------------------------

  /**
   * Schedule a broadcast message from the specified node at the current
   * simulation time. The message will be flooded to all reachable nodes
   * up to the sender's hop limit.
   *
   * @param fromNodeId - ID of the originating node
   * @param payloadBytes - application payload size in bytes (default: 32)
   */
  sendBroadcast(fromNodeId: string, payloadBytes: number = 32): void {
    const senderNode = this.nodes.find((n) => n.id === fromNodeId)

    const packet: Packet = {
      id: crypto.randomUUID(),
      originNodeId: fromNodeId,
      destinationNodeId: undefined,  // broadcast
      currentHopCount: 0,
      maxHopLimit: senderNode?.hopLimit ?? 3,
      payloadSizeBytes: payloadBytes,
      isAck: false,
      retryCount: 0,
      routePath: [fromNodeId],
    }

    const airtime = AirtimeCalculator.calculate(payloadBytes, this.channelPreset)
    packet.txStartTime = this.currentTimeMs
    packet.txEndTime = this.currentTimeMs + airtime

    this.scheduleEvent({
      id: this.nextEventId(),
      time: this.currentTimeMs,
      type: 'message_send',
      sourceNodeId: fromNodeId,
      packet,
    })
  }

  /**
   * Schedule a directed message from one node to another at the current
   * simulation time. An ACK is expected from the destination; the message
   * will be retransmitted up to maxRetransmissions times on timeout.
   *
   * @param fromNodeId - ID of the originating node
   * @param toNodeId - ID of the intended destination node
   * @param payloadBytes - application payload size in bytes (default: 32)
   */
  sendDirect(
    fromNodeId: string,
    toNodeId: string,
    payloadBytes: number = 32,
  ): void {
    const senderNode = this.nodes.find((n) => n.id === fromNodeId)

    const packet: Packet = {
      id: crypto.randomUUID(),
      originNodeId: fromNodeId,
      destinationNodeId: toNodeId,
      currentHopCount: 0,
      maxHopLimit: senderNode?.hopLimit ?? 3,
      payloadSizeBytes: payloadBytes,
      isAck: false,
      retryCount: 0,
      routePath: [fromNodeId],
    }

    const airtime = AirtimeCalculator.calculate(payloadBytes, this.channelPreset)
    packet.txStartTime = this.currentTimeMs
    packet.txEndTime = this.currentTimeMs + airtime

    const event: SimEvent = {
      id: this.nextEventId(),
      time: this.currentTimeMs,
      type: 'message_send',
      sourceNodeId: fromNodeId,
      packet,
    }

    this.scheduleEvent(event)
    this.protocol.registerPendingAck(packet, event)
  }

  // ---------------------------------------------------------------------------
  // Simulation execution
  // ---------------------------------------------------------------------------

  /**
   * Process a single event from the queue (step mode).
   *
   * @returns the processed event, or undefined when the queue is empty or the
   *          simulation time limit has been exceeded
   */
  step(): SimEvent | undefined {
    if (this.eventQueue.isEmpty) return undefined

    const event = this.eventQueue.extractMin()!
    this.currentTimeMs = event.time

    if (this.currentTimeMs > this.config.durationMs) return undefined

    this.processEvent(event)
    this.processedEvents.push(event)

    if (this.onEvent) this.onEvent(event)

    // Periodically remove expired transmissions from the channel model
    if (this.processedEvents.length % 100 === 0) {
      this.channelModel.cleanup(this.currentTimeMs - 5_000)
    }

    return event
  }

  /**
   * Run the entire simulation to completion and return the final metrics.
   * Equivalent to calling step() in a loop until it returns undefined.
   */
  run(): SimulationMetrics {
    while (!this.eventQueue.isEmpty) {
      const result = this.step()
      if (!result) break
    }
    return this.getMetrics()
  }

  // ---------------------------------------------------------------------------
  // Event handlers
  // ---------------------------------------------------------------------------

  private processEvent(event: SimEvent): void {
    switch (event.type) {
      case 'message_send':
        this.handleSend(event)
        break
      case 'message_receive':
        this.handleReceive(event)
        break
      case 'message_rebroadcast':
        this.handleRebroadcast(event)
        break
      case 'ack_send':
        // ACK transmission is handled identically to a regular send
        this.handleSend(event)
        break
      case 'ack_receive':
        this.handleAckReceive(event)
        break
      case 'timeout':
        this.handleTimeout(event)
        break
      // channel_busy and lbt_defer are informational — no state change needed
    }
  }

  /**
   * Handle a message_send or ack_send event.
   *
   * Registers the transmission on the channel model (detecting collisions),
   * then schedules receive events for every node that can hear the transmission.
   * For direct messages a timeout event is also scheduled to trigger retry logic.
   */
  private handleSend(event: SimEvent): void {
    const sender = event.sourceNodeId
    const airtime = AirtimeCalculator.calculate(
      event.packet.payloadSizeBytes,
      this.channelPreset,
    )

    // Register with channel model — returns any overlapping transmissions
    const collisions = this.channelModel.addTransmission(
      sender,
      event.time,
      event.time + airtime,
      event,
    )

    // Schedule receive events for all reachable neighbours
    for (const node of this.nodes) {
      if (node.id === sender) continue

      const link = this.getLink(sender, node.id)
      if (!link || !link.canHear) continue

      // EM propagation delay (negligible for LoRa distances but modelled for accuracy)
      // Speed of light: 300,000 km/s → delay in ms
      const propagationDelay = (link.distanceKm / 300_000) * 1_000
      const receiveTime = event.time + airtime + propagationDelay

      const receivedPacket: Packet = {
        ...event.packet,
        snrAtReceiver: link.snrDb,
        rssiAtReceiver: link.rssiDbm,
      }

      if (collisions.length > 0) {
        // Collision detected — schedule a collision event instead of a receive
        this.scheduleEvent({
          id: this.nextEventId(),
          time: receiveTime,
          type: 'collision',
          sourceNodeId: sender,
          targetNodeId: node.id,
          packet: receivedPacket,
        })
      } else {
        const receiveType = event.packet.isAck ? 'ack_receive' : 'message_receive'
        this.scheduleEvent({
          id: this.nextEventId(),
          time: receiveTime,
          type: receiveType,
          sourceNodeId: sender,
          targetNodeId: node.id,
          packet: receivedPacket,
        })
      }
    }

    // Schedule an ACK timeout for direct (non-ACK) messages
    if (event.packet.destinationNodeId && !event.packet.isAck) {
      const timeoutMs = airtime * 4  // wait 4× airtime before considering ACK lost
      this.scheduleEvent({
        id: this.nextEventId(),
        time: event.time + timeoutMs,
        type: 'timeout',
        sourceNodeId: sender,
        packet: event.packet,
      })
    }
  }

  /**
   * Handle a message_receive event.
   *
   * Applies deduplication, then either sends an ACK (if this node is the
   * destination of a direct message) or schedules a rebroadcast after the
   * contention window delay.
   */
  private handleReceive(event: SimEvent): void {
    const receiverId = event.targetNodeId!
    const packet = event.packet

    // Deduplication: drop the packet if this node has already processed it
    if (!this.protocol.shouldProcess(packet, receiverId)) return

    // Direct message arriving at its intended destination → send ACK
    if (packet.destinationNodeId === receiverId) {
      const ackPacket = this.protocol.createAckPacket(packet, receiverId)
      const ackAirtime = AirtimeCalculator.calculate(0, this.channelPreset)
      const ackStartTime = event.time + 10  // 10 ms processing delay

      ackPacket.txStartTime = ackStartTime
      ackPacket.txEndTime = ackStartTime + ackAirtime

      this.scheduleEvent({
        id: this.nextEventId(),
        time: ackStartTime,
        type: 'ack_send',
        sourceNodeId: receiverId,
        packet: ackPacket,
      })
      return
    }

    // Flood routing: rebroadcast if hop limit permits
    if (this.protocol.shouldRebroadcast(packet)) {
      const rebroadcastPacket = this.protocol.createRebroadcast(packet, receiverId)

      // Contention window: lower SNR → shorter delay (node is farther from origin)
      const delay = ContentionWindow.calculateDelay(packet.snrAtReceiver ?? 0)
      const rebroadcastTime = event.time + delay

      const airtime = AirtimeCalculator.calculate(
        rebroadcastPacket.payloadSizeBytes,
        this.channelPreset,
      )
      rebroadcastPacket.txStartTime = rebroadcastTime
      rebroadcastPacket.txEndTime = rebroadcastTime + airtime

      this.scheduleEvent({
        id: this.nextEventId(),
        time: rebroadcastTime,
        type: 'message_rebroadcast',
        sourceNodeId: receiverId,
        packet: rebroadcastPacket,
      })
    }
  }

  /**
   * Handle a message_rebroadcast event.
   * Functionally identical to a send — registers with the channel model and
   * propagates to all reachable neighbours.
   */
  private handleRebroadcast(event: SimEvent): void {
    this.handleSend(event)
  }

  /**
   * Handle an ack_receive event.
   * Clears the pending ACK for the original direct message.
   */
  private handleAckReceive(event: SimEvent): void {
    const receiverId = event.targetNodeId!

    // The ACK destination is the original sender — only they act on it
    if (event.packet.destinationNodeId !== receiverId) return

    // Strip the "ack-" prefix to get the original packet ID
    const originalPacketId = event.packet.id.replace(/^ack-/, '')
    this.protocol.handleAck(originalPacketId)
  }

  /**
   * Handle a timeout event for a direct message that did not receive an ACK.
   * Retransmits the packet if retries remain; otherwise gives up.
   */
  private handleTimeout(event: SimEvent): void {
    const retryCount = this.protocol.checkRetransmit(event.packet.id)
    if (retryCount < 0) return  // max retries exhausted

    const airtime = AirtimeCalculator.calculate(
      event.packet.payloadSizeBytes,
      this.channelPreset,
    )

    const retryPacket: Packet = {
      ...event.packet,
      retryCount,
      routePath: [event.sourceNodeId],
      txStartTime: event.time,
      txEndTime: event.time + airtime,
    }

    this.scheduleEvent({
      id: this.nextEventId(),
      time: event.time,
      type: 'message_send',
      sourceNodeId: event.sourceNodeId,
      packet: retryPacket,
    })
  }

  // ---------------------------------------------------------------------------
  // Public accessors
  // ---------------------------------------------------------------------------

  /** Return aggregated metrics for all events processed so far. */
  getMetrics(): SimulationMetrics {
    if (this.processedEvents.length === 0) return createEmptyMetrics()
    return calculateMetrics(this.processedEvents, this.config)
  }

  /** Return a shallow copy of all events processed so far. */
  getProcessedEvents(): SimEvent[] {
    return [...this.processedEvents]
  }

  /** Current simulation clock in milliseconds. */
  getCurrentTime(): number {
    return this.currentTimeMs
  }

  /** True when the event queue still has events to process. */
  get hasPendingEvents(): boolean {
    return !this.eventQueue.isEmpty
  }

  /**
   * Return the pre-computed link info between two specific nodes.
   * Returns undefined if either node ID is unknown.
   */
  getLinkInfo(fromId: string, toId: string): LinkInfo | undefined {
    return this.getLink(fromId, toId)
  }

  /**
   * Return all pre-computed links as a flat array.
   * Useful for map visualisation of reachable pairs.
   */
  getAllLinks(): LinkInfo[] {
    return Array.from(this.linkCache.values())
  }

  /**
   * Reset the engine to its initial state, preserving the node list,
   * channel preset and configuration.
   */
  reset(): void {
    this.eventQueue.clear()
    this.channelModel.clear()
    this.protocol.clear()
    this.processedEvents = []
    this.eventIdCounter = 0
    this.currentTimeMs = 0
    this.buildLinkCache()
  }
}
