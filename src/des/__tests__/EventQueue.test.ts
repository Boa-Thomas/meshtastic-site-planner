import { describe, it, expect, beforeEach } from 'vitest'
import { EventQueue } from '../EventQueue'
import type { SimEvent, Packet } from '../types'

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function makePacket(id: string | number): Packet {
  return {
    id: `pkt-${id}`,
    originNodeId: 'node-a',
    currentHopCount: 0,
    maxHopLimit: 3,
    payloadSizeBytes: 32,
    isAck: false,
    retryCount: 0,
    routePath: [],
  }
}

function makeEvent(time: number, id: number = time): SimEvent {
  return {
    id,
    time,
    type: 'message_send',
    sourceNodeId: 'node-a',
    packet: makePacket(id),
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('EventQueue', () => {
  let queue: EventQueue

  beforeEach(() => {
    queue = new EventQueue()
  })

  // -------------------------------------------------------------------------
  // Basic extraction order
  // -------------------------------------------------------------------------

  it('extractMin returns events in ascending time order', () => {
    queue.insert(makeEvent(30, 3))
    queue.insert(makeEvent(10, 1))
    queue.insert(makeEvent(20, 2))

    expect(queue.extractMin()!.time).toBe(10)
    expect(queue.extractMin()!.time).toBe(20)
    expect(queue.extractMin()!.time).toBe(30)
  })

  it('extractMin returns undefined from an empty queue', () => {
    expect(queue.extractMin()).toBeUndefined()
  })

  it('returns undefined again after all elements are extracted', () => {
    queue.insert(makeEvent(5))
    queue.extractMin()
    expect(queue.extractMin()).toBeUndefined()
  })

  // -------------------------------------------------------------------------
  // Peek
  // -------------------------------------------------------------------------

  it('peek returns the minimum time event without removing it', () => {
    queue.insert(makeEvent(100, 1))
    queue.insert(makeEvent(50, 2))
    queue.insert(makeEvent(75, 3))

    const peeked = queue.peek()
    expect(peeked).toBeDefined()
    expect(peeked!.time).toBe(50)

    // Size must not have changed
    expect(queue.size).toBe(3)
  })

  it('peek on empty queue returns undefined', () => {
    expect(queue.peek()).toBeUndefined()
  })

  it('peek and extractMin agree on the minimum element', () => {
    queue.insert(makeEvent(200, 1))
    queue.insert(makeEvent(100, 2))

    const peeked = queue.peek()
    const extracted = queue.extractMin()
    expect(peeked).toBe(extracted)
  })

  // -------------------------------------------------------------------------
  // Interleaved insert / extractMin
  // -------------------------------------------------------------------------

  it('maintains heap order across interleaved insertions and extractions', () => {
    queue.insert(makeEvent(50, 1))
    queue.insert(makeEvent(10, 2))

    expect(queue.extractMin()!.time).toBe(10)

    queue.insert(makeEvent(30, 3))
    queue.insert(makeEvent(5, 4))

    expect(queue.extractMin()!.time).toBe(5)
    expect(queue.extractMin()!.time).toBe(30)
    expect(queue.extractMin()!.time).toBe(50)
    expect(queue.extractMin()).toBeUndefined()
  })

  it('handles many elements in random order and extracts them sorted', () => {
    const times = [42, 7, 99, 1, 56, 23, 88, 3, 61, 15]
    times.forEach((t, i) => queue.insert(makeEvent(t, i)))

    const extracted: number[] = []
    let event: SimEvent | undefined
    while ((event = queue.extractMin()) !== undefined) {
      extracted.push(event.time)
    }

    const sorted = [...times].sort((a, b) => a - b)
    expect(extracted).toEqual(sorted)
  })

  it('handles duplicate time values without losing events', () => {
    queue.insert(makeEvent(10, 1))
    queue.insert(makeEvent(10, 2))
    queue.insert(makeEvent(10, 3))

    const results = [queue.extractMin(), queue.extractMin(), queue.extractMin()]
    expect(results.every((e) => e !== undefined)).toBe(true)
    expect(results.every((e) => e!.time === 10)).toBe(true)
    expect(queue.isEmpty).toBe(true)
  })

  // -------------------------------------------------------------------------
  // size and isEmpty
  // -------------------------------------------------------------------------

  it('size starts at 0 for a new queue', () => {
    expect(queue.size).toBe(0)
  })

  it('isEmpty is true for a new queue', () => {
    expect(queue.isEmpty).toBe(true)
  })

  it('size increments with each insert', () => {
    queue.insert(makeEvent(1))
    expect(queue.size).toBe(1)
    queue.insert(makeEvent(2))
    expect(queue.size).toBe(2)
    queue.insert(makeEvent(3))
    expect(queue.size).toBe(3)
  })

  it('isEmpty becomes false after first insert', () => {
    queue.insert(makeEvent(1))
    expect(queue.isEmpty).toBe(false)
  })

  it('size decrements with each extractMin', () => {
    queue.insert(makeEvent(1))
    queue.insert(makeEvent(2))
    queue.extractMin()
    expect(queue.size).toBe(1)
    queue.extractMin()
    expect(queue.size).toBe(0)
  })

  it('isEmpty becomes true after last extraction', () => {
    queue.insert(makeEvent(1))
    queue.extractMin()
    expect(queue.isEmpty).toBe(true)
  })

  // -------------------------------------------------------------------------
  // clear
  // -------------------------------------------------------------------------

  it('clear empties the queue', () => {
    queue.insert(makeEvent(1))
    queue.insert(makeEvent(2))
    queue.insert(makeEvent(3))

    queue.clear()

    expect(queue.size).toBe(0)
    expect(queue.isEmpty).toBe(true)
    expect(queue.extractMin()).toBeUndefined()
    expect(queue.peek()).toBeUndefined()
  })

  it('clear on an already-empty queue is a no-op', () => {
    queue.clear()
    expect(queue.size).toBe(0)
    expect(queue.isEmpty).toBe(true)
  })

  it('queue is usable after clear', () => {
    queue.insert(makeEvent(5))
    queue.clear()
    queue.insert(makeEvent(3))
    queue.insert(makeEvent(1))

    expect(queue.extractMin()!.time).toBe(1)
    expect(queue.extractMin()!.time).toBe(3)
  })

  // -------------------------------------------------------------------------
  // Single element edge case
  // -------------------------------------------------------------------------

  it('extractMin on a single-element queue works correctly', () => {
    queue.insert(makeEvent(42))
    expect(queue.extractMin()!.time).toBe(42)
    expect(queue.size).toBe(0)
  })
})
