import { defineStore } from 'pinia'
import type { MeshNode, ChannelPresetId } from '../types/index'
import { devicePresets } from '../data/devicePresets'
import { channelPresets, DEFAULT_CHANNEL_PRESET_ID } from '../data/channelPresets'

const STORAGE_KEY = 'meshtastic-planner-nodes'

function loadNodes(): MeshNode[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveNodes(nodes: MeshNode[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(nodes))
  } catch {
    // localStorage may be full or unavailable — fail silently
  }
}

export const useNodesStore = defineStore('nodes', {
  state: () => ({
    nodes: loadNodes(),
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
      saveNodes(this.nodes)
    },
    removeNode(id: string) {
      const idx = this.nodes.findIndex(n => n.id === id)
      if (idx >= 0) this.nodes.splice(idx, 1)
      if (this.selectedNodeId === id) this.selectedNodeId = null
      saveNodes(this.nodes)
    },
    updateNode(id: string, updates: Partial<MeshNode>) {
      const node = this.nodes.find(n => n.id === id)
      if (node) {
        Object.assign(node, updates)
        saveNodes(this.nodes)
      }
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
      saveNodes(this.nodes)
    },
    applyChannelPreset(nodeId: string, presetId: ChannelPresetId) {
      const preset = channelPresets.find(p => p.id === presetId)
      const node = this.nodes.find(n => n.id === nodeId)
      if (!preset || !node) return
      node.channelPresetId = presetId
      node.rxSensitivityDbm = preset.sensitivityDbm
      saveNodes(this.nodes)
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
        txGainDbi: 2.0,
        antennaHeight: 2.0,
        rxSensitivityDbm: -136,
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
