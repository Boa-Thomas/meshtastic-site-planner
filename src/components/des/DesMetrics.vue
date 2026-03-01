<template>
  <div v-if="desStore.eventCount > 0">
    <h6 class="text-light mb-2">Metrics</h6>
    <div class="row g-1 small">
      <div class="col-6">
        <div class="card bg-dark border-secondary">
          <div class="card-body py-1 px-2">
            <div class="text-muted">Delivery Ratio</div>
            <div class="fw-bold">{{ (metrics.deliveryRatio * 100).toFixed(1) }}%</div>
          </div>
        </div>
      </div>
      <div class="col-6">
        <div class="card bg-dark border-secondary">
          <div class="card-body py-1 px-2">
            <div class="text-muted">Avg Latency</div>
            <div class="fw-bold">{{ metrics.averageLatencyMs.toFixed(0) }} ms</div>
          </div>
        </div>
      </div>
      <div class="col-6">
        <div class="card bg-dark border-secondary">
          <div class="card-body py-1 px-2">
            <div class="text-muted">Max Latency</div>
            <div class="fw-bold">{{ metrics.maxLatencyMs.toFixed(0) }} ms</div>
          </div>
        </div>
      </div>
      <div class="col-6">
        <div class="card bg-dark border-secondary">
          <div class="card-body py-1 px-2">
            <div class="text-muted">Avg Hops</div>
            <div class="fw-bold">{{ metrics.averageHopCount.toFixed(1) }}</div>
          </div>
        </div>
      </div>
      <div class="col-6">
        <div class="card bg-dark border-secondary">
          <div class="card-body py-1 px-2">
            <div class="text-muted">Collisions</div>
            <div class="fw-bold">{{ metrics.totalCollisions }}</div>
          </div>
        </div>
      </div>
      <div class="col-6">
        <div class="card bg-dark border-secondary">
          <div class="card-body py-1 px-2">
            <div class="text-muted">Messages</div>
            <div class="fw-bold">{{ metrics.totalMessagesDelivered }}/{{ metrics.totalMessagesSent }}</div>
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
</script>
