import { defineStore } from 'pinia'
import type { MeshNode, ChannelPresetId } from '../types/index'
import { devicePresets } from '../data/devicePresets'
import { channelPresets, DEFAULT_CHANNEL_PRESET_ID } from '../data/channelPresets'

export const useNodesStore = defineStore('nodes', {
  state: () => ({
    nodes: [] as MeshNode[],
    selectedNodeId: null as string | null,
    isPlacingNode: false,
  }),
  getters: {
    selectedNode: (state) => state.nodes.find(n => n.id === state.selectedNodeId),
    nodeById: (state) => (id: string) => state.nodes.find(n => n.id === id),
  },
  actions: {
    addNode(node: MeshNode) {
      this.nodes.push(node)
      this.selectedNodeId = node.id
    },
    removeNode(id: string) {
      const idx = this.nodes.findIndex(n => n.id === id)
      if (idx >= 0) this.nodes.splice(idx, 1)
      if (this.selectedNodeId === id) this.selectedNodeId = null
    },
    updateNode(id: string, updates: Partial<MeshNode>) {
      const node = this.nodes.find(n => n.id === id)
      if (node) Object.assign(node, updates)
    },
    applyDevicePreset(nodeId: string, presetId: string) {
      const preset = devicePresets.find(p => p.id === presetId)
      const node = this.nodes.find(n => n.id === nodeId)
      if (!preset || !node) return
      node.devicePresetId = presetId
      node.txPowerW = preset.txPowerW
      node.txPowerDbm = preset.txPowerDbm
      node.frequencyMhz = preset.frequencyMhz
      node.txGainDbi = preset.antennaGainDbi
      node.rxSensitivityDbm = preset.rxSensitivityDbm
    },
    applyChannelPreset(nodeId: string, presetId: ChannelPresetId) {
      const preset = channelPresets.find(p => p.id === presetId)
      const node = this.nodes.find(n => n.id === nodeId)
      if (!preset || !node) return
      node.channelPresetId = presetId
      node.rxSensitivityDbm = preset.sensitivityDbm
    },
    createDefaultNode(lat: number, lon: number, name: string): MeshNode {
      return {
        id: crypto.randomUUID(),
        name,
        lat,
        lon,
        txPowerW: 0.158,
        txPowerDbm: 22,
        frequencyMhz: 915.0,
        txHeight: 2.0,
        txGainDbi: 2.0,
        rxSensitivityDbm: -136,
        rxHeight: 1.0,
        rxGainDbi: 2.0,
        rxLossDb: 2.0,
        installationType: 'rooftop',
        antennaOrientation: 'omnidirectional',
        obstructionLevel: 'clear',
        channelPresetId: DEFAULT_CHANNEL_PRESET_ID,
        hopLimit: 3,
      }
    },
    startPlacingNode() {
      this.isPlacingNode = true
    },
    stopPlacingNode() {
      this.isPlacingNode = false
    },
  },
})
