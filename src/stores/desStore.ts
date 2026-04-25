import { defineStore } from 'pinia'
import { markRaw } from 'vue'
import { SimulationEngine, createDefaultConfig } from '../des'
import type { SimEvent, SimulationConfig, SimulationMetrics, LinkInfo } from '../des'
import { createEmptyMetrics } from '../des'
import { PATH_LOSS_PROFILES } from '../des/types'
import type { PathLossProfileId } from '../des/types'
import type { MeshNode, ChannelPreset, Site } from '../types/index'
import { channelPresets } from '../data/channelPresets'
import { useNodesStore } from './nodesStore'
import { buildRssiOverrideMapAsync } from '../utils/rssiWorkerClient'

export type DesStatus = 'idle' | 'running' | 'paused' | 'completed'

export const useDesStore = defineStore('des', {
  state: () => ({
    status: 'idle' as DesStatus,
    engine: null as SimulationEngine | null,
    processedEvents: [] as SimEvent[],
    currentEventIndex: -1,
    metrics: createEmptyMetrics() as SimulationMetrics,
    config: createDefaultConfig() as SimulationConfig,
    pathLossProfileId: 'forest_mountain' as PathLossProfileId,
    playbackSpeed: 1,    // 1 = real-time, 2 = 2x, 0.5 = half speed, etc.
    animationTimerId: null as number | null,
    links: [] as LinkInfo[],
  }),

  getters: {
    currentEvent: (state): SimEvent | undefined => {
      if (state.currentEventIndex >= 0 && state.currentEventIndex < state.processedEvents.length) {
        return state.processedEvents[state.currentEventIndex]
      }
      return undefined
    },
    eventCount: (state): number => state.processedEvents.length,
    currentTimeMs: (state): number => state.engine?.getCurrentTime() ?? 0,
    hasPendingEvents: (state): boolean => state.engine?.hasPendingEvents ?? false,
  },

  actions: {
    /**
     * Initialize the DES engine with the current nodes and config.
     * Must be called before any simulation actions.
     */
    async initialize(channelPresetOverride?: ChannelPreset, sites?: Site[]) {
      const nodesStore = useNodesStore()
      if (nodesStore.nodes.length < 2) return

      // Find the channel preset for the first node (all should match)
      const firstNode = nodesStore.nodes[0]
      const preset = channelPresetOverride
        ?? channelPresets.find(p => p.id === firstNode.channelPresetId)
        ?? channelPresets[0]

      // Apply selected path loss profile to the simulation config
      const profile = PATH_LOSS_PROFILES.find(p => p.id === this.pathLossProfileId)
      if (profile) {
        this.config.pathLossConfig = profile.config
      }

      // Build RSSI overrides from SPLAT! raster data (if available).
      // Off-loads to a Web Worker when the mesh is large enough to benefit.
      const rssiOverrides = await buildRssiOverrideMapAsync(
        nodesStore.nodes as MeshNode[],
        sites ?? [],
      )

      // Create engine with markRaw to avoid Vue proxy wrapping (performance)
      this.engine = markRaw(new SimulationEngine(
        nodesStore.nodes as MeshNode[],
        preset,
        this.config,
        rssiOverrides,
      ))

      // Compute links for visualization
      this.links = this.engine.getAllLinks()

      this.processedEvents = []
      this.currentEventIndex = -1
      this.metrics = createEmptyMetrics()
      this.status = 'paused'
    },

    /**
     * Send a broadcast message from a node.
     */
    sendBroadcast(fromNodeId: string, payloadBytes: number = 32) {
      if (!this.engine) return
      this.engine.sendBroadcast(fromNodeId, payloadBytes)
    },

    /**
     * Send a direct message between two nodes.
     */
    sendDirect(fromNodeId: string, toNodeId: string, payloadBytes: number = 32) {
      if (!this.engine) return
      this.engine.sendDirect(fromNodeId, toNodeId, payloadBytes)
    },

    /**
     * Execute a single step (one event).
     */
    step(): SimEvent | undefined {
      if (!this.engine) return undefined
      const event = this.engine.step()
      if (event) {
        this.processedEvents.push(event)
        this.currentEventIndex = this.processedEvents.length - 1
        this.metrics = this.engine.getMetrics()
        this.status = this.engine.hasPendingEvents ? 'running' : 'completed'
      } else {
        this.status = 'completed'
      }
      return event
    },

    /**
     * Start automatic playback — steps through events at the configured speed.
     */
    play() {
      if (!this.engine || this.status === 'completed') return
      this.status = 'running'

      const stepInterval = Math.max(10, 50 / this.playbackSpeed)

      const tick = () => {
        if (this.status !== 'running') return
        const event = this.step()
        if (event && this.status === 'running') {
          this.animationTimerId = window.setTimeout(tick, stepInterval) as unknown as number
        }
      }
      tick()
    },

    /**
     * Pause automatic playback.
     */
    pause() {
      this.status = 'paused'
      if (this.animationTimerId !== null) {
        clearTimeout(this.animationTimerId)
        this.animationTimerId = null
      }
    },

    /**
     * Run to completion (no animation).
     */
    runToCompletion() {
      if (!this.engine) return
      this.status = 'running'
      const metrics = this.engine.run()
      this.processedEvents = this.engine.getProcessedEvents()
      this.currentEventIndex = this.processedEvents.length - 1
      this.metrics = metrics
      this.status = 'completed'
    },

    /**
     * Reset the simulation to initial state.
     */
    reset() {
      if (this.animationTimerId !== null) {
        clearTimeout(this.animationTimerId)
        this.animationTimerId = null
      }
      if (this.engine) {
        this.engine.reset()
        this.links = this.engine.getAllLinks()
      }
      this.processedEvents = []
      this.currentEventIndex = -1
      this.metrics = createEmptyMetrics()
      this.status = 'idle'
    },

    /**
     * Update the simulation config (region, duration, etc.)
     */
    updateConfig(updates: Partial<SimulationConfig>) {
      Object.assign(this.config, updates)
      // Sync pathLossProfileId from imported pathLossConfig
      if (updates.pathLossConfig) {
        const match = PATH_LOSS_PROFILES.find(
          p => p.config.pathLossExponent === updates.pathLossConfig!.pathLossExponent
            && p.config.breakpointKm === updates.pathLossConfig!.breakpointKm,
        )
        if (match) this.pathLossProfileId = match.id
      }
    },
  },
})
