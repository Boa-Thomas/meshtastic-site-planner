<template>
  <div v-if="desStore.eventCount > 0">
    <div class="d-flex justify-content-between align-items-center mb-2">
      <h6 class="text-light mb-0">Event Log ({{ desStore.eventCount }})</h6>
      <button class="btn btn-outline-secondary btn-sm" @click="exportCsv">Export CSV</button>
    </div>
    <div class="des-event-log" ref="logContainer">
      <div
        v-for="(event, i) in recentEvents"
        :key="event.id"
        class="des-event-item small"
        :class="{ 'des-event-current': i === recentEvents.length - 1 }"
        @click="toggleDetails(event.id)"
        style="cursor: pointer"
      >
        <span class="badge me-1" :class="eventBadgeClass(event.type)">{{ eventTypeLabel(event.type) }}</span>
        <span class="text-muted">{{ event.time.toFixed(0) }}ms</span>
        <span class="ms-1">{{ eventDescription(event) }}</span>

        <!-- Expandable details -->
        <div v-if="selectedEventId === event.id" class="mt-1 ps-2 border-start border-info small text-muted" @click.stop>
          <div>Packet ID: {{ event.packet.id.slice(0, 8) }}</div>
          <div>Hop: {{ event.packet.currentHopCount }}/{{ event.packet.maxHopLimit }}</div>
          <div v-if="event.packet.rssiAtReceiver !== undefined">RSSI: {{ event.packet.rssiAtReceiver.toFixed(1) }} dBm</div>
          <div v-if="event.packet.snrAtReceiver !== undefined">SNR: {{ event.packet.snrAtReceiver.toFixed(1) }} dB</div>
          <div>Payload: {{ event.packet.payloadSizeBytes }} bytes</div>
          <div v-if="event.packet.retryCount > 0">Retries: {{ event.packet.retryCount }}</div>
          <div v-if="event.packet.destinationNodeId">Dest: {{ nodeName(event.packet.destinationNodeId) }}</div>
        </div>
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
const selectedEventId = ref<number | null>(null)

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

function toggleDetails(eventId: number) {
  selectedEventId.value = selectedEventId.value === eventId ? null : eventId
}

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

function exportCsv() {
  const events = desStore.processedEvents
  const header = 'event_id,time_ms,type,source_node,target_node,packet_id,hop,max_hop,payload_bytes,rssi_dbm,snr_db,is_ack,retry_count,route_path'
  const rows = events.map(e => {
    const src = nodeName(e.sourceNodeId)
    const tgt = nodeName(e.targetNodeId)
    const p = e.packet
    return [
      e.id,
      e.time.toFixed(1),
      e.type,
      src,
      tgt,
      p.id.slice(0, 8),
      p.currentHopCount,
      p.maxHopLimit,
      p.payloadSizeBytes,
      p.rssiAtReceiver?.toFixed(1) ?? '',
      p.snrAtReceiver?.toFixed(1) ?? '',
      p.isAck,
      p.retryCount,
      p.routePath.map(id => nodeName(id)).join(' > '),
    ].join(',')
  })
  const csv = [header, ...rows].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'des-event-log.csv'
  a.click()
  URL.revokeObjectURL(url)
}

function eventDescription(event: SimEvent): string {
  const src = nodeName(event.sourceNodeId)
  const tgt = nodeName(event.targetNodeId)
  const rssi = event.packet.rssiAtReceiver
  const snr = event.packet.snrAtReceiver
  switch (event.type) {
    case 'message_send':
      return `${src} sends (hop ${event.packet.currentHopCount}, ${event.packet.payloadSizeBytes}B)`
    case 'message_receive': {
      const parts = [`${tgt} \u2190 ${src}`]
      if (rssi !== undefined) parts.push(`RSSI ${rssi.toFixed(0)} dBm`)
      if (snr !== undefined) parts.push(`SNR ${snr.toFixed(0)} dB`)
      return parts.join(', ')
    }
    case 'message_rebroadcast':
      return `${src} rebroadcasts (hop ${event.packet.currentHopCount})`
    case 'ack_send':
      return `${src} sends ACK`
    case 'ack_receive': {
      const parts = [`${tgt} ACK \u2190 ${src}`]
      if (rssi !== undefined) parts.push(`RSSI ${rssi.toFixed(0)} dBm`)
      return parts.join(', ')
    }
    case 'collision':
      return `Collision at ${tgt} (from ${src})`
    case 'timeout':
      return `${src} ACK timeout (retry ${event.packet.retryCount})`
    default:
      return ''
  }
}
</script>
