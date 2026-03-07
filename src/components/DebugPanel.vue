<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-2">
      <span class="small text-muted">Auto-refresh: {{ polling ? 'ON' : 'OFF' }}</span>
      <button class="btn btn-outline-light btn-sm" @click="togglePolling">
        {{ polling ? 'Stop' : 'Start' }}
      </button>
    </div>

    <div v-if="error" class="alert alert-danger py-1 px-2 small">{{ error }}</div>

    <div v-if="data" class="small font-monospace">
      <div class="mb-2">
        <strong>Queues</strong>
        <div>default: {{ data.queues.default }} &nbsp; heavy: {{ data.queues.heavy }}</div>
      </div>

      <div class="mb-2">
        <strong>Workers</strong>
        <div>
          light: {{ data.workers.light }}/{{ data.config.max_light }}
          &nbsp; heavy: {{ data.workers.heavy }}/{{ data.config.max_heavy }}
        </div>
      </div>

      <div class="mb-2">
        <strong>Active Tasks</strong> ({{ data.active_tasks.length }})
        <div v-for="task in data.active_tasks" :key="task.task_id" class="ms-2">
          <span class="text-truncate d-inline-block" style="max-width: 120px;" :title="task.task_id">
            {{ task.task_id.slice(0, 8) }}...
          </span>
          <span v-if="task.progress" class="text-info ms-1">
            {{ stageLabel(task.progress.stage) }} {{ Math.round((task.progress.progress || 0) * 100) }}%
          </span>
        </div>
        <div v-if="data.active_tasks.length === 0" class="text-muted ms-2">None</div>
      </div>

      <div class="text-muted" style="font-size: 0.7rem;">
        Threshold: {{ data.config.heavy_threshold_km }}km
        &middot; Updated: {{ lastUpdate }}
      </div>
    </div>

    <div v-else-if="!error" class="text-muted small">Click Start to begin monitoring.</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from 'vue'

interface DebugData {
  queues: { default: number; heavy: number }
  active_tasks: Array<{
    task_id: string
    progress?: { stage: string; progress: number; detail: string }
  }>
  workers: { light: number; heavy: number }
  config: { max_light: number; max_heavy: number; heavy_threshold_km: number }
  timestamp: number
}

const data = ref<DebugData | null>(null)
const error = ref('')
const polling = ref(false)
const lastUpdate = ref('')
let intervalId: ReturnType<typeof setInterval> | null = null

const stageLabel = (stage: string): string => {
  const labels: Record<string, string> = {
    downloading_tiles: 'Downloading terrain...',
    configuring: 'Configuring model...',
    running_splat: 'Running simulation...',
    converting: 'Generating result...',
    completed: 'Done',
  }
  return labels[stage] || stage
}

async function fetchStatus() {
  try {
    const res = await fetch('/api/debug/status')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    data.value = await res.json()
    error.value = ''
    lastUpdate.value = new Date().toLocaleTimeString()
  } catch (e: any) {
    error.value = e.message || 'Failed to fetch'
  }
}

function togglePolling() {
  if (polling.value) {
    if (intervalId) clearInterval(intervalId)
    intervalId = null
    polling.value = false
  } else {
    polling.value = true
    fetchStatus()
    intervalId = setInterval(fetchStatus, 5000)
  }
}

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId)
})
</script>
