<template>
  <div v-if="desStore.eventCount > 0">
    <h6 class="text-light mb-2">Event Log ({{ desStore.eventCount }})</h6>
    <div class="des-event-log" ref="logContainer">
      <div
        v-for="(event, i) in recentEvents"
        :key="event.id"
        class="des-event-item small"
        :class="{ 'des-event-current': i === recentEvents.length - 1 }"
      >
        <span class="badge me-1" :class="eventBadgeClass(event.type)">{{ eventTypeLabel(event.type) }}</span>
        <span class="text-muted">{{ event.time.toFixed(0) }}ms</span>
        <span class="ms-1">{{ eventDescription(event) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { useDesStore } from '../../stores/desStore'
import type { SimEvent, EventType } from '../../des/types'
import { useNodesStore } from '../../stores/nodesStore'

const desStore = useDesStore()
const nodesStore = useNodesStore()
const logContainer = ref<HTMLElement>()

// Show last 50 events
const recentEvents = computed(() => {
  const events = desStore.processedEvents
  return events.slice(Math.max(0, events.length - 50))
})

// Auto-scroll to bottom on new events
watch(() => desStore.eventCount, async () => {
  await nextTick()
  if (logContainer.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
})

function nodeName(id: string | undefined): string {
  if (!id) return '?'
  return nodesStore.nodeById(id)?.name ?? id.slice(0, 6)
}

function eventTypeLabel(type: EventType): string {
  const labels: Record<EventType, string> = {
    message_send: 'TX',
    message_receive: 'RX',
    message_rebroadcast: 'FWD',
    ack_send: 'ACK-TX',
    ack_receive: 'ACK-RX',
    collision: 'COL',
    timeout: 'TMO',
    channel_busy: 'BUSY',
    lbt_defer: 'LBT',
  }
  return labels[type] ?? type
}

function eventBadgeClass(type: EventType): string {
  const classes: Record<string, string> = {
    message_send: 'bg-primary',
    message_receive: 'bg-success',
    message_rebroadcast: 'bg-info',
    ack_send: 'bg-secondary',
    ack_receive: 'bg-secondary',
    collision: 'bg-danger',
    timeout: 'bg-warning text-dark',
    channel_busy: 'bg-warning text-dark',
    lbt_defer: 'bg-warning text-dark',
  }
  return classes[type] ?? 'bg-dark'
}

function eventDescription(event: SimEvent): string {
  const src = nodeName(event.sourceNodeId)
  const tgt = nodeName(event.targetNodeId)
  switch (event.type) {
    case 'message_send': return `${src} sends (hop ${event.packet.currentHopCount})`
    case 'message_receive': return `${tgt} receives from ${src}`
    case 'message_rebroadcast': return `${src} rebroadcasts (hop ${event.packet.currentHopCount})`
    case 'ack_send': return `${src} sends ACK`
    case 'ack_receive': return `${tgt} receives ACK`
    case 'collision': return `Collision at ${tgt}`
    case 'timeout': return `${src} ACK timeout`
    default: return ''
  }
}
</script>
