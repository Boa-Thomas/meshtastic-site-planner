import type { SimEvent } from './types'

/**
 * Binary min-heap priority queue ordered by SimEvent.time.
 * Provides O(log n) insert and extractMin operations.
 */
export class EventQueue {
  private heap: SimEvent[] = []

  /** Insert an event into the priority queue. O(log n). */
  insert(event: SimEvent): void {
    this.heap.push(event)
    this.bubbleUp(this.heap.length - 1)
  }

  /** Remove and return the event with the smallest time. O(log n). */
  extractMin(): SimEvent | undefined {
    if (this.heap.length === 0) return undefined
    if (this.heap.length === 1) return this.heap.pop()

    const min = this.heap[0]
    // Move the last element to the root and restore heap property
    this.heap[0] = this.heap.pop()!
    this.bubbleDown(0)
    return min
  }

  /** Return the event with the smallest time without removing it. O(1). */
  peek(): SimEvent | undefined {
    return this.heap[0]
  }

  /** Number of events in the queue. */
  get size(): number {
    return this.heap.length
  }

  /** True when no events are queued. */
  get isEmpty(): boolean {
    return this.heap.length === 0
  }

  /** Remove all events from the queue. */
  clear(): void {
    this.heap = []
  }

  // ---------------------------------------------------------------------------
  // Heap internals
  // ---------------------------------------------------------------------------

  private parentIndex(i: number): number {
    return Math.floor((i - 1) / 2)
  }

  private leftChildIndex(i: number): number {
    return 2 * i + 1
  }

  private rightChildIndex(i: number): number {
    return 2 * i + 2
  }

  /** Move element at index i up until the heap property is satisfied. */
  private bubbleUp(i: number): void {
    while (i > 0) {
      const parent = this.parentIndex(i)
      if (this.heap[parent].time <= this.heap[i].time) break
      // Swap with parent
      ;[this.heap[parent], this.heap[i]] = [this.heap[i], this.heap[parent]]
      i = parent
    }
  }

  /** Move element at index i down until the heap property is satisfied. */
  private bubbleDown(i: number): void {
    const n = this.heap.length

    while (true) {
      let smallest = i
      const left = this.leftChildIndex(i)
      const right = this.rightChildIndex(i)

      if (left < n && this.heap[left].time < this.heap[smallest].time) {
        smallest = left
      }
      if (right < n && this.heap[right].time < this.heap[smallest].time) {
        smallest = right
      }

      if (smallest === i) break

      ;[this.heap[smallest], this.heap[i]] = [this.heap[i], this.heap[smallest]]
      i = smallest
    }
  }
}
