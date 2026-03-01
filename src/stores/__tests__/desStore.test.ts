import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useDesStore } from '../desStore'
import { useNodesStore } from '../nodesStore'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Add two nearby nodes to the nodesStore.
 * Placing them ~1.4 km apart ensures FSPL at 915 MHz is well within the
 * default LONG_FAST sensitivity of -136 dBm, so canHear = true for both.
 */
function addTestNodes(nodesStore: ReturnType<typeof useNodesStore>) {
  const node1 = nodesStore.createDefaultNode(-23.55, -46.63, 'Node A')
  const node2 = nodesStore.createDefaultNode(-23.56, -46.64, 'Node B')
  nodesStore.addNode(node1)
  nodesStore.addNode(node2)
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
    it('sets status to idle and creates the engine when >= 2 nodes exist', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()

      expect(desStore.status).toBe('idle')
      expect(desStore.engine).not.toBeNull()
    })

    it('computes links after initialization', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()

      // 2 nodes → 2 directed links (A→B and B→A)
      expect(desStore.links.length).toBeGreaterThan(0)
    })

    it('resets processedEvents and metrics on re-initialize', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)
      desStore.runToCompletion()
      expect(desStore.processedEvents.length).toBeGreaterThan(0)

      // Re-initialize — state should be cleared
      desStore.initialize()
      expect(desStore.processedEvents.length).toBe(0)
      expect(desStore.currentEventIndex).toBe(-1)
      expect(desStore.metrics.totalMessagesSent).toBe(0)
    })

    it('does NOT create an engine when fewer than 2 nodes exist', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      // Add only one node
      const node = nodesStore.createDefaultNode(-23.55, -46.63, 'Lone Node')
      nodesStore.addNode(node)

      desStore.initialize()

      expect(desStore.engine).toBeNull()
    })

    it('does NOT create an engine when no nodes exist', () => {
      const desStore = useDesStore()
      desStore.initialize()
      expect(desStore.engine).toBeNull()
    })
  })

  // ---------------------------------------------------------------------------
  // sendBroadcast + step
  // ---------------------------------------------------------------------------

  describe('sendBroadcast + step', () => {
    it('step returns an event after sendBroadcast', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      const event = desStore.step()

      expect(event).toBeDefined()
      expect(event?.type).toBe('message_send')
    })

    it('step appends the event to processedEvents', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      desStore.step()

      expect(desStore.processedEvents.length).toBeGreaterThan(0)
    })

    it('step updates currentEventIndex', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      desStore.step()

      expect(desStore.currentEventIndex).toBe(0)
    })

    it('step returns undefined when the queue is empty', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()

      // No broadcast sent — queue is empty
      const result = desStore.step()
      expect(result).toBeUndefined()
    })
  })

  // ---------------------------------------------------------------------------
  // play + pause
  // ---------------------------------------------------------------------------

  describe('play + pause', () => {
    it('play sets status to running', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      desStore.play()

      expect(desStore.status).toBe('running')

      // Clean up: pause to stop any timers
      desStore.pause()
    })

    it('pause sets status to paused', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      desStore.play()
      desStore.pause()

      expect(desStore.status).toBe('paused')
    })

    it('pause clears the animation timer', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
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
    it('sets status to completed', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      desStore.runToCompletion()

      expect(desStore.status).toBe('completed')
    })

    it('populates processedEvents after running to completion', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      desStore.runToCompletion()

      expect(desStore.processedEvents.length).toBeGreaterThan(0)
    })

    it('sets currentEventIndex to the last event index', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
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
    it('sets status back to idle', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)
      desStore.runToCompletion()

      desStore.reset()

      expect(desStore.status).toBe('idle')
    })

    it('clears processedEvents after reset', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)
      desStore.runToCompletion()
      expect(desStore.processedEvents.length).toBeGreaterThan(0)

      desStore.reset()

      expect(desStore.processedEvents).toHaveLength(0)
    })

    it('resets currentEventIndex to -1', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)
      desStore.runToCompletion()

      desStore.reset()

      expect(desStore.currentEventIndex).toBe(-1)
    })

    it('resets metrics to zero values', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
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
    it('totalMessagesSent > 0 after stepping through a broadcast', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      // Step until the queue is empty or we process several events
      let safety = 0
      while (desStore.engine?.hasPendingEvents && safety < 100) {
        desStore.step()
        safety++
      }

      expect(desStore.metrics.totalMessagesSent).toBeGreaterThan(0)
    })

    it('metrics are updated after runToCompletion', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)
      desStore.runToCompletion()

      expect(desStore.metrics.totalMessagesSent).toBeGreaterThan(0)
    })
  })

  // ---------------------------------------------------------------------------
  // Getters
  // ---------------------------------------------------------------------------

  describe('getters', () => {
    it('eventCount returns the number of processed events', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)
      desStore.runToCompletion()

      expect(desStore.eventCount).toBe(desStore.processedEvents.length)
    })

    it('currentEvent returns undefined before any steps', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()

      expect(desStore.currentEvent).toBeUndefined()
    })

    it('currentEvent returns the last processed event after stepping', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      const event = desStore.step()

      expect(desStore.currentEvent).toBeDefined()
      expect(desStore.currentEvent?.id).toBe(event?.id)
    })

    it('hasPendingEvents is false before any messages are queued', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()

      expect(desStore.hasPendingEvents).toBe(false)
    })

    it('hasPendingEvents is true after sending a broadcast', () => {
      const nodesStore = useNodesStore()
      const desStore = useDesStore()

      addTestNodes(nodesStore)
      desStore.initialize()
      desStore.sendBroadcast(nodesStore.nodes[0].id)

      expect(desStore.hasPendingEvents).toBe(true)
    })
  })
})
