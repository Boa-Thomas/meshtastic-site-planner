import type { Packet, SimEvent, SimulationConfig } from './types'

/**
 * Implements the Meshtastic managed flood routing protocol state machine.
 *
 * Key responsibilities:
 * - Deduplication: packets already seen by a node are dropped
 * - Hop limit enforcement: packets exceeding maxHopLimit are not rebroadcast
 * - ACK tracking: direct messages register a pending ACK and are retried
 *   up to maxRetransmissions if no ACK is received within the timeout window
 */
export class MeshtasticProtocol {
  /** Composite keys of "packetId:receiverNodeId" that have already been processed. */
  private seenPackets = new Set<string>()

  /**
   * Pending ACKs for direct messages.
   * Maps packet ID → { retry count, originating event }.
   */
  private pendingAcks = new Map<
    string,
    { retries: number; originEvent: SimEvent }
  >()

  private config: SimulationConfig

  constructor(config: SimulationConfig) {
    this.config = config
  }

  /**
   * Decide whether a packet should be processed by the given receiver.
   *
   * A packet is dropped (returns false) if the receiver has already seen it.
   * The first time a receiver encounters a packet it is recorded and true is returned.
   *
   * @param packet - the received packet
   * @param receiverNodeId - ID of the node that received the packet
   */
  shouldProcess(packet: Packet, receiverNodeId: string): boolean {
    const key = `${packet.id}:${receiverNodeId}`
    if (this.seenPackets.has(key)) return false
    this.seenPackets.add(key)
    return true
  }

  /**
   * Decide whether a packet should be rebroadcast.
   * Returns false once the hop limit has been reached.
   *
   * @param packet - packet to evaluate
   */
  shouldRebroadcast(packet: Packet): boolean {
    return packet.currentHopCount < packet.maxHopLimit
  }

  /**
   * Create a copy of the packet with the hop count incremented by one
   * and the relay node appended to the route path.
   * Does not modify the original packet.
   *
   * @param packet - packet to derive the rebroadcast from
   * @param relayNodeId - ID of the node that is rebroadcasting
   */
  createRebroadcast(packet: Packet, relayNodeId: string): Packet {
    return {
      ...packet,
      currentHopCount: packet.currentHopCount + 1,
      routePath: [...packet.routePath, relayNodeId],
    }
  }

  /**
   * Register a direct message that expects an ACK from its destination.
   * Called immediately after a direct message is scheduled for transmission.
   *
   * @param packet - the outgoing packet
   * @param event - the send event (kept for potential retry scheduling)
   */
  registerPendingAck(packet: Packet, event: SimEvent): void {
    this.pendingAcks.set(packet.id, { retries: 0, originEvent: event })
  }

  /**
   * Handle an incoming ACK for a previously registered direct message.
   *
   * @param packetId - the original (non-ACK) packet ID being acknowledged
   * @returns true if the ACK was expected and has been cleared
   */
  handleAck(packetId: string): boolean {
    if (this.pendingAcks.has(packetId)) {
      this.pendingAcks.delete(packetId)
      return true
    }
    return false
  }

  /**
   * Check whether a direct message should be retransmitted after a timeout.
   *
   * Increments the retry counter. Returns -1 if the packet is unknown or
   * has already exhausted all allowed retransmissions.
   *
   * @param packetId - the original packet ID whose timeout fired
   * @returns the new retry count (≥ 1), or -1 if no further retries are allowed
   */
  checkRetransmit(packetId: string): number {
    const pending = this.pendingAcks.get(packetId)
    if (!pending) return -1

    if (pending.retries >= this.config.maxRetransmissions) {
      // Exhausted all retries — give up
      this.pendingAcks.delete(packetId)
      return -1
    }

    pending.retries++
    return pending.retries
  }

  /**
   * Build a minimal ACK packet in response to a received direct message.
   *
   * @param originalPacket - the packet being acknowledged
   * @param ackSenderNodeId - the node that received the message and is sending the ACK
   */
  createAckPacket(originalPacket: Packet, ackSenderNodeId: string): Packet {
    return {
      id: `ack-${originalPacket.id}`,
      originNodeId: ackSenderNodeId,
      destinationNodeId: originalPacket.originNodeId,
      currentHopCount: 0,
      maxHopLimit: originalPacket.maxHopLimit,
      payloadSizeBytes: 0,  // ACK carries no application payload
      isAck: true,
      retryCount: 0,
      routePath: [ackSenderNodeId],
    }
  }

  /** Reset all protocol state (seen packets and pending ACKs). */
  clear(): void {
    this.seenPackets.clear()
    this.pendingAcks.clear()
  }

  /** Number of direct messages currently awaiting an ACK. */
  get pendingAckCount(): number {
    return this.pendingAcks.size
  }
}
