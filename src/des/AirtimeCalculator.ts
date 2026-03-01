import type { ChannelPreset } from '../types/index'

export class AirtimeCalculator {
  /**
   * Calculate LoRa packet airtime in milliseconds.
   * Uses the standard Semtech formula.
   *
   * Reference: Semtech AN1200.13 "LoRa Modem Designer's Guide"
   *
   * @param payloadBytes - payload size in bytes
   * @param preset - channel configuration (SF, BW, CR)
   * @param preambleSymbols - number of preamble symbols (default: 8 for LoRa)
   * @param explicitHeader - whether explicit header is used (default: true)
   * @param crcEnabled - whether CRC is enabled (default: true)
   */
  static calculate(
    payloadBytes: number,
    preset: ChannelPreset,
    preambleSymbols: number = 8,
    explicitHeader: boolean = true,
    crcEnabled: boolean = true,
  ): number {
    const sf = preset.sf
    const bw = preset.bw * 1000  // kHz to Hz

    // Low data rate optimization is mandatory for SF11/BW125 and SF12/BW125
    const de = sf >= 11 && preset.bw <= 125 ? 1 : 0
    // Implicit header flag (1 = implicit, 0 = explicit)
    const ih = explicitHeader ? 0 : 1
    const crc = crcEnabled ? 1 : 0

    // Symbol duration in ms
    const tSymbol = (Math.pow(2, sf) / bw) * 1000

    // Preamble duration (preamble symbols + 4.25 sync symbols)
    const tPreamble = (preambleSymbols + 4.25) * tSymbol

    // Payload symbol count using Semtech formula
    const numerator = 8 * payloadBytes - 4 * sf + 28 + 16 * crc - 20 * ih
    const denominator = 4 * (sf - 2 * de)
    const payloadSymbols = 8 + Math.max(0, Math.ceil(numerator / denominator) * preset.cr)

    // Total airtime
    const tPayload = payloadSymbols * tSymbol
    return tPreamble + tPayload
  }
}
