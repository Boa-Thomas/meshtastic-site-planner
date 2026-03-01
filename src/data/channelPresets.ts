import type { ChannelPreset } from '../types/index'

/**
 * Meshtastic standard LoRa channel configurations.
 *
 * Parameter definitions:
 * - sf  — Spreading Factor (7–12). Higher SF = longer range, lower bitrate.
 * - bw  — Bandwidth in kHz (62.5 / 125 / 250 / 500).
 * - cr  — Coding Rate denominator. 5 = CR 4/5 (fastest), 8 = CR 4/8 (most robust).
 * - sensitivityDbm — Approximate minimum received signal level for reliable decode.
 * - bitrateBps — Approximate raw on-air LoRa symbol rate in bits per second.
 *
 * Sensitivity formula reference (approximation):
 *   sensitivity ≈ -174 + 10·log10(BW_Hz) + NF + SNR_required
 * where NF ≈ 6 dB and SNR_required depends on SF.
 *
 * Bitrate formula:
 *   bitrate = SF · (4 / (4 + cr)) · BW / 2^SF   [bits/s]
 *
 * Source: Meshtastic firmware channel_settings.h and LoRa Alliance specs.
 */
export const channelPresets: ChannelPreset[] = [
  {
    id: 'SHORT_TURBO',
    name: 'Short Range / Turbo',
    sf: 7,
    bw: 500,
    cr: 5,
    sensitivityDbm: -108,
    bitrateBps: 6836,
  },
  {
    id: 'SHORT_FAST',
    name: 'Short Range / Fast',
    sf: 7,
    bw: 250,
    cr: 5,
    sensitivityDbm: -111,
    bitrateBps: 3418,
  },
  {
    id: 'SHORT_SLOW',
    name: 'Short Range / Slow',
    sf: 8,
    bw: 250,
    cr: 5,
    sensitivityDbm: -114,
    bitrateBps: 1953,
  },
  {
    id: 'MEDIUM_FAST',
    name: 'Medium Range / Fast',
    sf: 9,
    bw: 250,
    cr: 5,
    sensitivityDbm: -117,
    bitrateBps: 1068,
  },
  {
    id: 'MEDIUM_SLOW',
    name: 'Medium Range / Slow',
    sf: 10,
    bw: 250,
    cr: 5,
    sensitivityDbm: -120,
    bitrateBps: 586,
  },
  {
    id: 'LONG_FAST',
    name: 'Long Range / Fast',
    sf: 11,
    bw: 250,
    cr: 5,
    sensitivityDbm: -123,
    bitrateBps: 317,
  },
  {
    id: 'LONG_MODERATE',
    name: 'Long Range / Moderate',
    sf: 11,
    bw: 125,
    cr: 8,
    sensitivityDbm: -126,
    bitrateBps: 137,
  },
  {
    id: 'LONG_SLOW',
    name: 'Long Range / Slow',
    sf: 12,
    bw: 125,
    cr: 8,
    sensitivityDbm: -129,
    bitrateBps: 73,
  },
  {
    id: 'VERY_LONG_SLOW',
    name: 'Very Long Range / Slow',
    sf: 12,
    bw: 62.5,
    cr: 8,
    sensitivityDbm: -132,
    bitrateBps: 36,
  },
]

/** The Meshtastic firmware default channel preset ID. */
export const DEFAULT_CHANNEL_PRESET_ID = 'LONG_FAST'
