import type { SimEvent } from './types'

interface Transmission {
  nodeId: string
  startTimeMs: number
  endTimeMs: number
  event: SimEvent
}

/**
 * Tracks channel occupancy and detects packet collisions.
 *
 * The model uses a simplified shared-medium assumption: any two transmissions
 * that overlap in time at the same receiver constitute a collision. This is
 * appropriate for a half-duplex LoRa network where all nodes share the same
 * frequency channel.
 */
export class ChannelModel {
  private activeTransmissions: Transmission[] = []

  /**
   * Register a new transmission on the channel.
   *
   * Returns the list of currently active transmissions that overlap with the
   * new one. A non-empty list means a collision is occurring.
   *
   * @param nodeId - ID of the transmitting node
   * @param startTimeMs - transmission start time in milliseconds
   * @param endTimeMs - transmission end time in milliseconds
   * @param event - the associated simulation event
   * @returns array of colliding transmissions (empty if channel was clear)
   */
  addTransmission(
    nodeId: string,
    startTimeMs: number,
    endTimeMs: number,
    event: SimEvent,
  ): Transmission[] {
    const tx: Transmission = { nodeId, startTimeMs, endTimeMs, event }

    // Any existing transmission whose time window overlaps with this one is a collision
    const collisions = this.activeTransmissions.filter(
      (existing) =>
        existing.endTimeMs > startTimeMs && existing.startTimeMs < endTimeMs,
    )

    this.activeTransmissions.push(tx)
    return collisions
  }

  /**
   * Check whether the channel is occupied at a given simulation time.
   * Used for Listen-Before-Talk (LBT) enforcement.
   *
   * @param timeMs - simulation time to check in milliseconds
   * @returns true if any transmission is active at the given time
   */
  isChannelBusy(timeMs: number): boolean {
    return this.activeTransmissions.some(
      (tx) => tx.startTimeMs <= timeMs && tx.endTimeMs > timeMs,
    )
  }

  /**
   * Remove all transmissions that ended before the given time.
   * Should be called periodically to prevent unbounded memory growth
   * in long-running simulations.
   *
   * @param beforeTimeMs - remove transmissions ending before this time
   */
  cleanup(beforeTimeMs: number): void {
    this.activeTransmissions = this.activeTransmissions.filter(
      (tx) => tx.endTimeMs > beforeTimeMs,
    )
  }

  /** Remove all tracked transmissions. */
  clear(): void {
    this.activeTransmissions = []
  }

  /** Number of transmissions currently tracked (including completed ones until cleanup). */
  get activeCount(): number {
    return this.activeTransmissions.length
  }
}
