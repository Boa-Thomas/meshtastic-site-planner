import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useDesStore } from '../desStore'
import { useNodesStore } from '../nodesStore'

// Mock the API module so tests don't need a running backend
vi.mock('../../services/api', () => ({
  getNodes: vi.fn().mockResolvedValue([]),
  createNode: vi.fn().mockImplementation((node: any) => Promise.resolve(node)),
  updateNodeApi: vi.fn().mockImplementation((_id: string, updates: any) => Promise.resolve(updates)),
  deleteNodeApi: vi.fn().mockResolvedValue(undefined),
  deleteAllNodes: vi.fn().mockResolvedValue(undefined),
  batchCreateNodes: vi.fn().mockImplementation((nodes: any[]) => Promise.resolve(nodes)),
}))

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Add two nearby nodes to the nodesStore.
 * Placing them ~1.4 km apart ensures FSPL at 915 MHz is well within the
 * default LONG_FAST sensitivity of -136 dBm, so canHear = true for both.
 */
async function addTestNodes(nodesStore: ReturnType<typeof useNodesStore>) {
  const node1 = nodesStore.createDefaultNode(-23.55, -46.63, 'Node A')
  const node2 = nodesStore.createDefaultNode(-23.56, -46.64, 'Node B')
  await nodesStore.addNode(node1)
  await nodesStore.addNode(node2)
}

describe('desStore', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  // ---------------------------------------------------------------------------
  // initialize
  // ---------------------------------------------------------------------------

  describe('initialize', () => {
    it('sets status to paused and creates the engine when >= 2 nodes exist', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()

      expect(desStore.status).toBe('paused')
      expect(desStore.engine).not.toBeNull()
    })

    it('computes links after initialization', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()

      // 2 nodes → 2 directed links (A→B and B→A)
      expect(desStore.links.length).toBeGreaterThan(0)
    })

    it('resets processedEvents and metrics on re-initialize', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)
      desStore.runToCompletion()
      expect(desStore.processedEvents.length).toBeGreaterThan(0)

      // Re-initialize — state should be cleared
      await desStore.initialize()
      expect(desStore.processedEvents.length).toBe(0)
      expect(desStore.currentEventIndex).toBe(-1)
      expect(desStore.metrics.totalMessagesSent).toBe(0)
    })

    it('does NOT create an engine when fewer than 2 nodes exist', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      // Add only one node
      const node = nodesStore.createDefaultNode(-23.55, -46.63, 'Lone Node')
      await nodesStore.addNode(node)

      await desStore.initialize()

      expect(desStore.engine).toBeNull()
    })

    it('does NOT create an engine when no nodes exist', async () => {
      const desStore = useDesStore()
      await desStore.initialize()
      expect(desStore.engine).toBeNull()
    })
  })

  // ---------------------------------------------------------------------------
  // sendBroadcast + step
  // ---------------------------------------------------------------------------

  describe('sendBroadcast + step', () => {
    it('step returns an event after sendBroadcast', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      const event = desStore.step()

      expect(event).toBeDefined()
      expect(event?.type).toBe('message_send')
    })

    it('step appends the event to processedEvents', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      desStore.step()

      expect(desStore.processedEvents.length).toBeGreaterThan(0)
    })

    it('step updates currentEventIndex', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      desStore.step()

      expect(desStore.currentEventIndex).toBe(0)
    })

    it('step returns undefined when the queue is empty', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()

      // No broadcast sent — queue is empty
      const result = desStore.step()
      expect(result).toBeUndefined()
    })
  })

  // ---------------------------------------------------------------------------
  // play + pause
  // ---------------------------------------------------------------------------

  describe('play + pause', () => {
    it('play sets status to running', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      desStore.play()

      expect(desStore.status).toBe('running')

      // Clean up: pause to stop any timers
      desStore.pause()
    })

    it('pause sets status to paused', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      desStore.play()
      desStore.pause()

      expect(desStore.status).toBe('paused')
    })

    it('pause clears the animation timer', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      desStore.play()
      desStore.pause()

      expect(desStore.animationTimerId).toBeNull()
    })
  })

  // ---------------------------------------------------------------------------
  // runToCompletion
  // ---------------------------------------------------------------------------

  describe('runToCompletion', () => {
    it('sets status to completed', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      desStore.runToCompletion()

      expect(desStore.status).toBe('completed')
    })

    it('populates processedEvents after running to completion', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      desStore.runToCompletion()

      expect(desStore.processedEvents.length).toBeGreaterThan(0)
    })

    it('sets currentEventIndex to the last event index', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      desStore.runToCompletion()

      expect(desStore.currentEventIndex).toBe(desStore.processedEvents.length - 1)
    })

    it('does nothing if engine is null', () => {
      const desStore = useDesStore()

      // Should not throw when engine is null
      expect(() => desStore.runToCompletion()).not.toThrow()
      expect(desStore.status).toBe('idle')
    })
  })

  // ---------------------------------------------------------------------------
  // reset
  // ---------------------------------------------------------------------------

  describe('reset', () => {
    it('sets status back to idle', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)
      desStore.runToCompletion()

      desStore.reset()

      expect(desStore.status).toBe('idle')
    })

    it('clears processedEvents after reset', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)
      desStore.runToCompletion()
      expect(desStore.processedEvents.length).toBeGreaterThan(0)

      desStore.reset()

      expect(desStore.processedEvents).toHaveLength(0)
    })

    it('resets currentEventIndex to -1', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)
      desStore.runToCompletion()

      desStore.reset()

      expect(desStore.currentEventIndex).toBe(-1)
    })

    it('resets metrics to zero values', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)
      desStore.runToCompletion()
      expect(desStore.metrics.totalMessagesSent).toBeGreaterThan(0)

      desStore.reset()

      expect(desStore.metrics.totalMessagesSent).toBe(0)
      expect(desStore.metrics.totalMessagesDelivered).toBe(0)
    })
  })

  // ---------------------------------------------------------------------------
  // metrics update after step
  // ---------------------------------------------------------------------------

  describe('metrics update after step', () => {
    it('totalMessagesSent > 0 after stepping through a broadcast', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      // Step until the queue is empty or we process several events
      let safety = 0
      while (desStore.engine?.hasPendingEvents && safety < 100) {
        desStore.step()
        safety++
      }

      expect(desStore.metrics.totalMessagesSent).toBeGreaterThan(0)
    })

    it('metrics are updated after runToCompletion', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)
      desStore.runToCompletion()

      expect(desStore.metrics.totalMessagesSent).toBeGreaterThan(0)
    })
  })

  // ---------------------------------------------------------------------------
  // Getters
  // ---------------------------------------------------------------------------

  describe('getters', () => {
    it('eventCount returns the number of processed events', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)
      desStore.runToCompletion()

      expect(desStore.eventCount).toBe(desStore.processedEvents.length)
    })

    it('currentEvent returns undefined before any steps', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()

      expect(desStore.currentEvent).toBeUndefined()
    })

    it('currentEvent returns the last processed event after stepping', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      const event = desStore.step()

      expect(desStore.currentEvent).toBeDefined()
      expect(desStore.currentEvent?.id).toBe(event?.id)
    })

    it('hasPendingEvents is false before any messages are queued', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()

      expect(desStore.hasPendingEvents).toBe(false)
    })

    it('hasPendingEvents is true after sending a broadcast', async () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      await addTestNodes(nodesStore)
      await desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      expect(desStore.hasPendingEvents).toBe(true)
    })
  })
})
