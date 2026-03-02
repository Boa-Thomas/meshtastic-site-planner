<template>
  <div>
    <!-- Status bar -->
    <div class="d-flex justify-content-between align-items-center mb-2">
      <span class="badge" :class="statusBadgeClass">{{ desStore.status }}</span>
      <small class="text-muted">{{ desStore.eventCount }} events | {{ (desStore.currentTimeMs / 1000).toFixed(1) }}s</small>
    </div>

    <!-- Config (only when idle) -->
    <div v-if="desStore.status === 'idle'" class="mb-3">
      <div class="row g-2">
        <div class="col-6">
          <label class="form-label">Region</label>
          <select class="form-select form-select-sm" v-model="desStore.config.region" @change="onRegionChange">
            <option value="BR_915">BR 915 MHz</option>
            <option value="US_902">US 902 MHz</option>
            <option value="EU_868">EU 868 MHz</option>
            <option value="EU_433">EU 433 MHz</option>
          </select>
        </div>
        <div class="col-6">
          <label class="form-label">Duration (s)</label>
          <input type="number" class="form-control form-control-sm" v-model.number="durationSec" min="1" max="3600" step="1" />
        </div>
      </div>
      <div class="mt-2">
        <label class="form-label">Propagation Environment</label>
        <select class="form-select form-select-sm" v-model="desStore.pathLossProfileId">
          <option v-for="profile in pathLossProfiles" :key="profile.id" :value="profile.id">
            {{ profile.name }}
          </option>
        </select>
      </div>
      <button class="btn btn-primary btn-sm w-100 mt-2" :disabled="nodesStore.nodes.length < 2" @click="onInit">
        Initialize DES ({{ nodesStore.nodes.length }} nodes)
      </button>
    </div>

    <!-- Message injection -->
    <div v-if="desStore.status !== 'idle'" class="mb-3">
      <div class="row g-2 mb-2">
        <div class="col-6">
          <label class="form-label">Source</label>
          <select class="form-select form-select-sm" v-model="sourceNodeId">
            <option v-for="node in nodesStore.nodes" :key="node.id" :value="node.id">{{ node.name }}</option>
          </select>
        </div>
        <div class="col-6">
          <label class="form-label">Destination</label>
          <select class="form-select form-select-sm" v-model="destNodeId">
            <option value="">Broadcast</option>
            <option v-for="node in nodesStore.nodes" :key="node.id" :value="node.id" :disabled="node.id === sourceNodeId">{{ node.name }}</option>
          </select>
        </div>
      </div>
      <button class="btn btn-outline-success btn-sm w-100" @click="onSendMessage" :disabled="!sourceNodeId">
        {{ destNodeId ? 'Send Direct' : 'Send Broadcast' }}
      </button>
    </div>

    <!-- Playback controls -->
    <div v-if="desStore.status !== 'idle'" class="d-flex gap-1 mb-2">
      <button class="btn btn-sm btn-outline-light" @click="desStore.step()" :disabled="desStore.status === 'completed'" title="Step">
        Step
      </button>
      <button v-if="desStore.status !== 'running'" class="btn btn-sm btn-outline-success" @click="desStore.play()" :disabled="desStore.status === 'completed'" title="Play">
        Play
      </button>
      <button v-else class="btn btn-sm btn-outline-warning" @click="desStore.pause()" title="Pause">
        Pause
      </button>
      <button class="btn btn-sm btn-outline-info" @click="desStore.runToCompletion()" :disabled="desStore.status === 'completed'" title="Run All">
        Run All
      </button>
      <button class="btn btn-sm btn-outline-danger" @click="desStore.reset()" title="Reset">
        Reset
      </button>
    </div>

    <!-- Speed slider -->
    <div v-if="desStore.status !== 'idle'" class="mb-2">
      <label class="form-label d-flex justify-content-between">
        <span>Speed</span>
        <span class="text-muted">{{ desStore.playbackSpeed }}x</span>
      </label>
      <input type="range" class="form-range" v-model.number="desStore.playbackSpeed" min="0.5" max="10" step="0.5" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useDesStore } from '../../stores/desStore'
import { useNodesStore } from '../../stores/nodesStore'
import { useSitesStore } from '../../stores/sitesStore'
import { REGION_DEFAULTS, PATH_LOSS_PROFILES } from '../../des/types'

const desStore = useDesStore()
const nodesStore = useNodesStore()
const sitesStore = useSitesStore()

const pathLossProfiles = PATH_LOSS_PROFILES

const sourceNodeId = ref('')
const destNodeId = ref('')

const durationSec = computed({
  get: () => desStore.config.durationMs / 1000,
  set: (v: number) => { desStore.config.durationMs = v * 1000 },
})

const statusBadgeClass = computed(() => ({
  'bg-secondary': desStore.status === 'idle',
  'bg-success': desStore.status === 'running',
  'bg-warning text-dark': desStore.status === 'paused',
  'bg-info': desStore.status === 'completed',
}))

function onRegionChange() {
  const defaults = REGION_DEFAULTS[desStore.config.region]
  if (defaults) {
    desStore.config.dutyCyclePercent = defaults.dutyCyclePercent
  }
}

function onInit() {
  desStore.initialize(undefined, sitesStore.localSites)
  // Auto-select first node as source
  if (nodesStore.nodes.length > 0) {
    sourceNodeId.value = nodesStore.nodes[0].id
  }
}

function onSendMessage() {
  if (!sourceNodeId.value) return
  if (destNodeId.value) {
    desStore.sendDirect(sourceNodeId.value, destNodeId.value)
  } else {
    desStore.sendBroadcast(sourceNodeId.value)
  }
}
</script>
