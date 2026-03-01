/**
 * Implements the Meshtastic managed flood contention window.
 *
 * In Meshtastic's protocol, nodes that receive a packet with a lower SNR
 * (i.e. they are farther from the transmitter) get a shorter rebroadcast
 * delay. This ensures that the message propagates outward efficiently,
 * because distant nodes rebroadcast before nearby ones that likely already
 * heard the original transmission.
 */
export class ContentionWindow {
  /** Duration of each contention slot in milliseconds. */
  static readonly SLOT_TIME_MS = 15

  /** Total number of contention slots available. */
  static readonly NUM_SLOTS = 32

  /**
   * Calculate the rebroadcast delay for a node based on its received SNR.
   *
   * Lower SNR → slot 0 → shortest delay (node rebroadcasts first).
   * Higher SNR → slot 31 → longest delay (node may defer if closer nodes retransmit).
   *
   * A small random jitter within the slot prevents simultaneous rebroadcasts
   * between nodes with identical SNR values.
   *
   * @param snrDb - signal-to-noise ratio at the receiver in dB
   * @param minSnr - minimum expected SNR for the normalization range (default: -20 dB)
   * @param maxSnr - maximum expected SNR for the normalization range (default: 30 dB)
   * @returns delay in milliseconds before the node should rebroadcast
   */
  static calculateDelay(
    snrDb: number,
    minSnr: number = -20,
    maxSnr: number = 30,
  ): number {
    // Clamp SNR to the expected operating range
    const clampedSnr = Math.max(minSnr, Math.min(maxSnr, snrDb))

    // Map SNR linearly to slot index:
    //   low SNR → slot 0 (shortest delay)
    //   high SNR → slot NUM_SLOTS-1 (longest delay)
    const normalized = (clampedSnr - minSnr) / (maxSnr - minSnr)  // 0..1
    const slot = Math.floor(normalized * (ContentionWindow.NUM_SLOTS - 1))

    // Add random jitter within the slot to reduce simultaneous rebroadcasts
    const jitter = Math.random() * ContentionWindow.SLOT_TIME_MS

    return slot * ContentionWindow.SLOT_TIME_MS + jitter
  }

  /**
   * Deterministic version of calculateDelay with no random jitter.
   * Useful for reproducible unit tests.
   *
   * @param snrDb - signal-to-noise ratio at the receiver in dB
   * @param minSnr - minimum SNR for normalization range (default: -20 dB)
   * @param maxSnr - maximum SNR for normalization range (default: 30 dB)
   * @returns deterministic delay in milliseconds
   */
  static calculateDelayDeterministic(
    snrDb: number,
    minSnr: number = -20,
    maxSnr: number = 30,
  ): number {
    const clampedSnr = Math.max(minSnr, Math.min(maxSnr, snrDb))
    const normalized = (clampedSnr - minSnr) / (maxSnr - minSnr)
    const slot = Math.floor(normalized * (ContentionWindow.NUM_SLOTS - 1))
    return slot * ContentionWindow.SLOT_TIME_MS
  }
}
