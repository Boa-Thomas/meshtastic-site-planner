import { defineStore } from 'pinia'
import type { MeshNode, ChannelPresetId } from '../types/index'
import { devicePresets } from '../data/devicePresets'
import { channelPresets, DEFAULT_CHANNEL_PRESET_ID } from '../data/channelPresets'
import {
  getNodes,
  createNode as apiCreateNode,
  updateNodeApi,
  deleteNodeApi,
  deleteAllNodes as apiDeleteAllNodes,
  batchCreateNodes,
} from '../services/api'

const LEGACY_STORAGE_KEY = 'meshtastic-planner-nodes'

export const useNodesStore = defineStore('nodes', {
  state: () => ({
    nodes: [] as MeshNode[],
    selectedNodeId: null as string | null,
    isPlacingNode: false,
    loading: false,
    initialized: false,
  }),
  getters: {
    selectedNode: (state) => state.nodes.find(n => n.id === state.selectedNodeId),
    nodeById: (state) => (id: string) => state.nodes.find(n => n.id === id),
  },
  actions: {
    async initialize() {
      if (this.initialized) return
      this.loading = true
      try {
        let serverNodes = await getNodes()

        // One-time migration from localStorage
        if (serverNodes.length === 0) {
          try {
            const raw = localStorage.getItem(LEGACY_STORAGE_KEY)
            if (raw) {
              const localNodes: MeshNode[] = JSON.parse(raw)
              if (Array.isArray(localNodes) && localNodes.length > 0) {
                serverNodes = await batchCreateNodes(localNodes)
                localStorage.removeItem(LEGACY_STORAGE_KEY)
                console.info('[NodesStore] Migrated', serverNodes.length, 'nodes from localStorage to server')
              }
            }
          } catch (migrationErr) {
            console.warn('[NodesStore] localStorage migration failed:', migrationErr)
          }
        }

        this.nodes = serverNodes
        this.initialized = true
      } catch (err) {
        console.error('[NodesStore] Failed to initialize from server:', err)
        // Fallback: try localStorage for offline resilience
        try {
          const raw = localStorage.getItem(LEGACY_STORAGE_KEY)
          if (raw) {
            const parsed = JSON.parse(raw)
            this.nodes = Array.isArray(parsed) ? parsed : []
          }
        } catch { /* ignore */ }
      } finally {
        this.loading = false
      }
    },
    async addNode(node: MeshNode) {
      try {
        const created = await apiCreateNode(node)
        this.nodes.push(created)
        this.selectedNodeId = created.id
      } catch (err) {
        console.error('[NodesStore] Failed to create node:', err)
        throw err
      }
    },
    async removeNode(id: string) {
      try {
        await deleteNodeApi(id)
        const idx = this.nodes.findIndex(n => n.id === id)
        if (idx >= 0) this.nodes.splice(idx, 1)
        if (this.selectedNodeId === id) this.selectedNodeId = null
      } catch (err) {
        console.error('[NodesStore] Failed to delete node:', err)
        throw err
      }
    },
    async updateNode(id: string, updates: Partial<MeshNode>) {
      try {
        const updated = await updateNodeApi(id, updates)
        const node = this.nodes.find(n => n.id === id)
        if (node) Object.assign(node, updated)
      } catch (err) {
        console.error('[NodesStore] Failed to update node:', err)
        throw err
      }
    },
    async applyDevicePreset(nodeId: string, presetId: string) {
      const preset = devicePresets.find(p => p.id === presetId)
      if (!preset) return
      await this.updateNode(nodeId, {
        devicePresetId: presetId,
        txPowerW: preset.txPowerW,
        txPowerDbm: preset.txPowerDbm,
        frequencyMhz: preset.frequencyMhz,
        txGainDbi: preset.antennaGainDbi,
        rxSensitivityDbm: preset.rxSensitivityDbm,
      })
    },
    async applyChannelPreset(nodeId: string, presetId: ChannelPresetId) {
      const preset = channelPresets.find(p => p.id === presetId)
      const node = this.nodes.find(n => n.id === nodeId)
      if (!preset || !node) return
      await this.updateNode(nodeId, {
        channelPresetId: presetId,
        rxSensitivityDbm: preset.sensitivityDbm,
      })
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
        elevationM: undefined,
        windowCone: undefined,
      }
    },
    async clearAllNodes() {
      try {
        await apiDeleteAllNodes()
        this.nodes = []
        this.selectedNodeId = null
      } catch (err) {
        console.error('[NodesStore] Failed to clear all nodes:', err)
        throw err
      }
    },
    async clearAllSiteIds() {
      for (const node of this.nodes) {
        if (node.siteId) {
          try {
            await updateNodeApi(node.id, { siteId: undefined })
            node.siteId = undefined
          } catch (err) {
            console.warn('[NodesStore] Failed to clear siteId for node', node.id, err)
          }
        }
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
