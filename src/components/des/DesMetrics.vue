<template>
  <div v-if="desStore.eventCount > 0">
    <h6 class="text-light mb-2">Metrics</h6>
    <div class="row g-1 small">
      <div class="col-6">
        <div class="card text-bg-dark border-secondary">
          <div class="card-body py-1 px-2">
            <div class="text-white-50">Delivery Ratio</div>
            <div class="fw-bold">{{ (metrics.deliveryRatio * 100).toFixed(1) }}%</div>
          </div>
        </div>
      </div>
      <div class="col-6">
        <div class="card text-bg-dark border-secondary">
          <div class="card-body py-1 px-2">
            <div class="text-white-50">Avg Latency</div>
            <div class="fw-bold">{{ metrics.averageLatencyMs.toFixed(0) }} ms</div>
          </div>
        </div>
      </div>
      <div class="col-6">
        <div class="card text-bg-dark border-secondary">
          <div class="card-body py-1 px-2">
            <div class="text-white-50">Max Latency</div>
            <div class="fw-bold">{{ metrics.maxLatencyMs.toFixed(0) }} ms</div>
          </div>
        </div>
      </div>
      <div class="col-6">
        <div class="card text-bg-dark border-secondary">
          <div class="card-body py-1 px-2">
            <div class="text-white-50">Avg Hops</div>
            <div class="fw-bold">{{ metrics.averageHopCount.toFixed(1) }}</div>
          </div>
        </div>
      </div>
      <div class="col-6">
        <div class="card text-bg-dark border-secondary">
          <div class="card-body py-1 px-2">
            <div class="text-white-50">Collisions</div>
            <div class="fw-bold">{{ metrics.totalCollisions }}</div>
          </div>
        </div>
      </div>
      <div class="col-6">
        <div class="card text-bg-dark border-secondary">
          <div class="card-body py-1 px-2">
            <div class="text-white-50">Messages</div>
            <div class="fw-bold">{{ metrics.totalMessagesDelivered }}/{{ metrics.totalMessagesSent }}</div>
          </div>
        </div>
      </div>
      <div class="col-6">
        <div class="card text-bg-dark border-secondary">
          <div class="card-body py-1 px-2">
            <div class="text-white-50">Avg RSSI</div>
            <div class="fw-bold">{{ avgRssi !== null ? avgRssi.toFixed(0) + ' dBm' : 'N/A' }}</div>
          </div>
        </div>
      </div>
      <div class="col-6">
        <div class="card text-bg-dark border-secondary">
          <div class="card-body py-1 px-2">
            <div class="text-white-50">Timeouts</div>
            <div class="fw-bold">{{ timeoutCount }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDesStore } from '../../stores/desStore'

const desStore = useDesStore()
const metrics = computed(() => desStore.metrics)

const avgRssi = computed(() => {
  const events = desStore.processedEvents.filter(
    e => e.type === 'message_receive' && e.packet.rssiAtReceiver !== undefined
  )
  if (events.length === 0) return null
  const sum = events.reduce((acc, e) => acc + (e.packet.rssiAtReceiver ?? 0), 0)
  return sum / events.length
})

const timeoutCount = computed(() => {
  return desStore.processedEvents.filter(e => e.type === 'timeout').length
})
</script>
