import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useNodesStore } from '../nodesStore'
import { devicePresets } from '../../data/devicePresets'
import { channelPresets } from '../../data/channelPresets'

// Mock the API module so tests don't need a running backend
vi.mock('../../services/api', () => ({
  getNodes: vi.fn().mockResolvedValue([]),
  createNode: vi.fn().mockImplementation((node: any) => Promise.resolve(node)),
  updateNodeApi: vi.fn().mockImplementation((_id: string, updates: any) => Promise.resolve(updates)),
  deleteNodeApi: vi.fn().mockResolvedValue(undefined),
  deleteAllNodes: vi.fn().mockResolvedValue(undefined),
  batchCreateNodes: vi.fn().mockImplementation((nodes: any[]) => Promise.resolve(nodes)),
}))

describe('nodesStore', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  // ---------------------------------------------------------------------------
  // addNode
  // ---------------------------------------------------------------------------

  describe('addNode', () => {
    it('adds a node to the store', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(-23.55, -46.63, 'Test Node')
      await store.addNode(node)

      expect(store.nodes.length).toBe(1)
      expect(store.nodes[0].name).toBe('Test Node')
    })

    it('sets selectedNodeId to the newly added node id', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(-23.55, -46.63, 'Test Node')
      await store.addNode(node)

      expect(store.selectedNodeId).toBe(node.id)
    })
  })

  // ---------------------------------------------------------------------------
  // removeNode
  // ---------------------------------------------------------------------------

  describe('removeNode', () => {
    it('removes a node by id and leaves the list empty', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(-23.55, -46.63, 'Node A')
      await store.addNode(node)
      await store.removeNode(node.id)

      expect(store.nodes.length).toBe(0)
    })

    it('sets selectedNodeId to null when the selected node is removed', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(-23.55, -46.63, 'Node A')
      await store.addNode(node)
      expect(store.selectedNodeId).toBe(node.id)

      await store.removeNode(node.id)
      expect(store.selectedNodeId).toBeNull()
    })

    it('does not affect other nodes when removing a specific one', async () => {
      const store = useNodesStore()
      const node1 = store.createDefaultNode(-23.55, -46.63, 'Node A')
      const node2 = store.createDefaultNode(-23.56, -46.64, 'Node B')
      await store.addNode(node1)
      await store.addNode(node2)

      await store.removeNode(node1.id)

      expect(store.nodes.length).toBe(1)
      expect(store.nodes[0].id).toBe(node2.id)
    })
  })

  // ---------------------------------------------------------------------------
  // updateNode
  // ---------------------------------------------------------------------------

  describe('updateNode', () => {
    it('updates the name of an existing node', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(-23.55, -46.63, 'Original Name')
      await store.addNode(node)

      await store.updateNode(node.id, { name: 'Updated Name' })

      expect(store.nodes[0].name).toBe('Updated Name')
    })

    it('updates multiple fields at once', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(-23.55, -46.63, 'Node A')
      await store.addNode(node)

      await store.updateNode(node.id, { txPowerDbm: 30, antennaHeight: 10 })

      expect(store.nodes[0].txPowerDbm).toBe(30)
      expect(store.nodes[0].antennaHeight).toBe(10)
    })

    it('does nothing when the node id does not exist', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(-23.55, -46.63, 'Node A')
      await store.addNode(node)

      // Update with a non-existent id — API mock resolves, but node not found locally
      try {
        await store.updateNode('non-existent-id', { name: 'Ghost' })
      } catch { /* expected — API may reject */ }

      expect(store.nodes[0].name).toBe('Node A')
    })
  })

  // ---------------------------------------------------------------------------
  // createDefaultNode
  // ---------------------------------------------------------------------------

  describe('createDefaultNode', () => {
    it('returns a node with the provided lat, lon, and name', () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(-23.55, -46.63, 'My Node')

      expect(node.lat).toBe(-23.55)
      expect(node.lon).toBe(-46.63)
      expect(node.name).toBe('My Node')
    })

    it('returns a node with hopLimit = 3 by default', () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(0, 0, 'Node')

      expect(node.hopLimit).toBe(3)
    })

    it('returns a node with channelPresetId = LONG_FAST by default', () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(0, 0, 'Node')

      expect(node.channelPresetId).toBe('LONG_FAST')
    })

    it('assigns a unique UUID-format id to each node', () => {
      const store = useNodesStore()
      const node1 = store.createDefaultNode(0, 0, 'Node 1')
      const node2 = store.createDefaultNode(0, 0, 'Node 2')

      expect(node1.id).not.toBe(node2.id)
      // UUID v4 pattern
      expect(node1.id).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
      )
    })

    it('sets default RF parameter values correctly', () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(0, 0, 'Node')

      expect(node.txPowerW).toBeCloseTo(0.158)
      expect(node.txPowerDbm).toBe(22)
      expect(node.frequencyMhz).toBe(915.0)
      expect(node.txGainDbi).toBe(2.0)
      expect(node.antennaHeight).toBe(2.0)
      expect(node.rxSensitivityDbm).toBe(-136)
      expect(node.rxGainDbi).toBe(2.0)
      expect(node.rxLossDb).toBe(2.0)
    })

    it('has elevationM undefined by default', () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(0, 0, 'Node')
      expect(node.elevationM).toBeUndefined()
    })

    it('has windowCone undefined by default', () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(0, 0, 'Node')
      expect(node.windowCone).toBeUndefined()
    })
  })

  // ---------------------------------------------------------------------------
  // applyDevicePreset
  // ---------------------------------------------------------------------------

  describe('applyDevicePreset', () => {
    it('applies the heltec_v3 preset: txPowerDbm=22, txPowerW=0.158', async () => {
      const store = useNodesStore()
      // Start with different values so we can confirm they are overwritten
      const node = store.createDefaultNode(-23.55, -46.63, 'Node A')
      node.txPowerDbm = 10
      node.txPowerW = 0.01
      await store.addNode(node)

      await store.applyDevicePreset(node.id, 'heltec_v3')

      const updated = store.nodes[0]
      expect(updated.txPowerDbm).toBe(22)
      expect(updated.txPowerW).toBeCloseTo(0.158)
    })

    it('applies the heltec_v3 preset frequency correctly', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(0, 0, 'Node')
      await store.addNode(node)

      await store.applyDevicePreset(node.id, 'heltec_v3')

      expect(store.nodes[0].frequencyMhz).toBe(915)
    })

    it('sets devicePresetId on the node', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(0, 0, 'Node')
      await store.addNode(node)

      await store.applyDevicePreset(node.id, 'heltec_v3')

      expect(store.nodes[0].devicePresetId).toBe('heltec_v3')
    })

    it('applies rxSensitivityDbm from the preset', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(0, 0, 'Node')
      await store.addNode(node)

      await store.applyDevicePreset(node.id, 'heltec_v3')

      const preset = devicePresets.find((p) => p.id === 'heltec_v3')!
      expect(store.nodes[0].rxSensitivityDbm).toBe(preset.rxSensitivityDbm)
    })

    it('does nothing when node id does not exist', async () => {
      const store = useNodesStore()
      // Should not throw
      await store.applyDevicePreset('non-existent', 'heltec_v3')
    })

    it('does nothing when preset id does not exist', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(0, 0, 'Node')
      await store.addNode(node)
      const originalPower = node.txPowerDbm

      await store.applyDevicePreset(node.id, 'does_not_exist')

      expect(store.nodes[0].txPowerDbm).toBe(originalPower)
    })
  })

  // ---------------------------------------------------------------------------
  // applyChannelPreset
  // ---------------------------------------------------------------------------

  describe('applyChannelPreset', () => {
    it('applies SHORT_TURBO preset: rxSensitivityDbm = -108', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(0, 0, 'Node')
      await store.addNode(node)

      await store.applyChannelPreset(node.id, 'SHORT_TURBO')

      const preset = channelPresets.find((p) => p.id === 'SHORT_TURBO')!
      expect(store.nodes[0].rxSensitivityDbm).toBe(preset.sensitivityDbm)
      expect(store.nodes[0].rxSensitivityDbm).toBe(-108)
    })

    it('updates channelPresetId on the node', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(0, 0, 'Node')
      await store.addNode(node)

      await store.applyChannelPreset(node.id, 'VERY_LONG_SLOW')

      expect(store.nodes[0].channelPresetId).toBe('VERY_LONG_SLOW')
    })

    it('sets correct sensitivity for LONG_SLOW (-129 dBm)', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(0, 0, 'Node')
      await store.addNode(node)

      await store.applyChannelPreset(node.id, 'LONG_SLOW')

      expect(store.nodes[0].rxSensitivityDbm).toBe(-129)
    })
  })

  // ---------------------------------------------------------------------------
  // isPlacingNode
  // ---------------------------------------------------------------------------

  describe('isPlacingNode', () => {
    it('starts as false', () => {
      const store = useNodesStore()
      expect(store.isPlacingNode).toBe(false)
    })

    it('startPlacingNode sets isPlacingNode to true', () => {
      const store = useNodesStore()
      store.startPlacingNode()
      expect(store.isPlacingNode).toBe(true)
    })

    it('stopPlacingNode sets isPlacingNode to false', () => {
      const store = useNodesStore()
      store.startPlacingNode()
      store.stopPlacingNode()
      expect(store.isPlacingNode).toBe(false)
    })
  })

  // ---------------------------------------------------------------------------
  // selectedNode getter
  // ---------------------------------------------------------------------------

  describe('selectedNode getter', () => {
    it('returns the node matching selectedNodeId', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(-23.55, -46.63, 'Node A')
      await store.addNode(node)

      expect(store.selectedNode).toBeDefined()
      expect(store.selectedNode?.id).toBe(node.id)
    })

    it('returns undefined after the selected node is removed', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(-23.55, -46.63, 'Node A')
      await store.addNode(node)
      await store.removeNode(node.id)

      expect(store.selectedNode).toBeUndefined()
    })

    it('returns undefined when no node is selected', () => {
      const store = useNodesStore()
      expect(store.selectedNode).toBeUndefined()
    })
  })

  // ---------------------------------------------------------------------------
  // nodeById getter
  // ---------------------------------------------------------------------------

  describe('nodeById getter', () => {
    it('returns the correct node for the given id', async () => {
      const store = useNodesStore()
      const node1 = store.createDefaultNode(-23.55, -46.63, 'Node A')
      const node2 = store.createDefaultNode(-23.56, -46.64, 'Node B')
      await store.addNode(node1)
      await store.addNode(node2)

      const found = store.nodeById(node1.id)
      expect(found).toBeDefined()
      expect(found?.name).toBe('Node A')
    })

    it('returns undefined for an unknown id', async () => {
      const store = useNodesStore()
      const node = store.createDefaultNode(0, 0, 'Node')
      await store.addNode(node)

      expect(store.nodeById('unknown-id')).toBeUndefined()
    })
  })
})
