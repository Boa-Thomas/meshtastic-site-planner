<template>
  <div v-if="node">
    <!-- Editable node name -->
    <div class="mb-2">
      <label class="form-label">Node Name</label>
      <input
        type="text"
        class="form-control form-control-sm"
        :value="node.name"
        @input="nodesStore.updateNode(node!.id, { name: ($event.target as HTMLInputElement).value })"
      />
    </div>

    <!-- Device preset -->
    <DevicePresetSelector
      :modelValue="node.devicePresetId ?? ''"
      @update:modelValue="onDeviceChange"
    />

    <!-- Channel preset -->
    <div class="mt-2">
      <ChannelPresetSelector
        :modelValue="node.channelPresetId"
        @update:modelValue="onChannelChange"
      />
    </div>

    <!-- Coordinates + Altitude -->
    <div class="row g-2 mt-2">
      <div class="col-6">
        <label class="form-label">Latitude</label>
        <input
          type="number"
          class="form-control form-control-sm"
          :value="node.lat"
          step="0.000001"
          @input="nodesStore.updateNode(node!.id, { lat: parseFloat(($event.target as HTMLInputElement).value) })"
        />
      </div>
      <div class="col-6">
        <label class="form-label">Longitude</label>
        <input
          type="number"
          class="form-control form-control-sm"
          :value="node.lon"
          step="0.000001"
          @input="nodesStore.updateNode(node!.id, { lon: parseFloat(($event.target as HTMLInputElement).value) })"
        />
      </div>
      <div class="col-12">
        <div class="d-flex align-items-center gap-2">
          <button
            type="button"
            class="btn btn-outline-info btn-sm"
            :disabled="fetchingAltitude"
            @click="fetchAltitude"
          >
            <span v-if="fetchingAltitude" class="spinner-border spinner-border-sm me-1"></span>
            Fetch Altitude
          </button>
          <span v-if="node.elevationM !== undefined" class="small text-muted">
            {{ node.elevationM }}m MSL
          </span>
        </div>
      </div>
    </div>

    <!-- Essential parameters (always visible) -->
    <div class="row g-2 mt-2">
      <div class="col-6">
        <label class="form-label">Antenna Height (m)</label>
        <input
          type="number"
          class="form-control form-control-sm"
          :value="node.antennaHeight"
          min="0.5"
          step="0.5"
          @input="nodesStore.updateNode(node!.id, { antennaHeight: parseFloat(($event.target as HTMLInputElement).value) })"
        />
      </div>
      <div class="col-6">
        <label class="form-label">Hop Limit</label>
        <input
          type="number"
          class="form-control form-control-sm"
          :value="node.hopLimit"
          min="0"
          max="7"
          step="1"
          @input="nodesStore.updateNode(node!.id, { hopLimit: parseInt(($event.target as HTMLInputElement).value, 10) })"
        />
      </div>
    </div>

    <!-- Advanced toggle -->
    <a
      href="#"
      class="small text-info d-block mt-2"
      @click.prevent="showAdvanced = !showAdvanced"
    >
      {{ showAdvanced ? 'Hide Advanced' : 'Show Advanced' }}
    </a>

    <!-- Advanced parameters (collapsible) -->
    <div v-if="showAdvanced">
      <div class="row g-2 mt-1">
        <div class="col-6">
          <label class="form-label">TX Power (W)</label>
          <input
            type="number"
            class="form-control form-control-sm"
            :value="node.txPowerW"
            min="0.001"
            step="0.01"
            @input="nodesStore.updateNode(node!.id, { txPowerW: parseFloat(($event.target as HTMLInputElement).value) })"
          />
        </div>
        <div class="col-6">
          <label class="form-label">Frequency (MHz)</label>
          <input
            type="number"
            class="form-control form-control-sm"
            :value="node.frequencyMhz"
            min="100"
            max="1000"
            step="0.1"
            @input="nodesStore.updateNode(node!.id, { frequencyMhz: parseFloat(($event.target as HTMLInputElement).value) })"
          />
        </div>
      </div>

      <div class="row g-2 mt-2">
        <div class="col-6">
          <label class="form-label">RX Sensitivity (dBm)</label>
          <input
            type="number"
            class="form-control form-control-sm"
            :value="node.rxSensitivityDbm"
            max="0"
            step="1"
            @input="nodesStore.updateNode(node!.id, { rxSensitivityDbm: parseFloat(($event.target as HTMLInputElement).value) })"
          />
        </div>
        <div class="col-6">
          <label class="form-label">RX Gain (dBi)</label>
          <input
            type="number"
            class="form-control form-control-sm"
            :value="node.rxGainDbi"
            step="0.5"
            @input="nodesStore.updateNode(node!.id, { rxGainDbi: parseFloat(($event.target as HTMLInputElement).value) })"
          />
        </div>
      </div>

      <div class="row g-2 mt-2">
        <div class="col-6">
          <label class="form-label">RX Loss (dB)</label>
          <input
            type="number"
            class="form-control form-control-sm"
            :value="node.rxLossDb"
            min="0"
            step="0.5"
            @input="nodesStore.updateNode(node!.id, { rxLossDb: parseFloat(($event.target as HTMLInputElement).value) })"
          />
        </div>
      </div>

      <!-- Installation type + obstruction + window cone -->
      <div class="mt-2">
        <InstallationConfig
          :installationType="node.installationType"
          :obstructionLevel="node.obstructionLevel"
          :windowCone="node.windowCone"
          @update:installationType="v => nodesStore.updateNode(node!.id, { installationType: v })"
          @update:obstructionLevel="v => nodesStore.updateNode(node!.id, { obstructionLevel: v })"
          @update:windowCone="v => nodesStore.updateNode(node!.id, { windowCone: v })"
        />
      </div>

      <!-- Antenna preset + orientation + directional params -->
      <div class="mt-2">
        <AntennaConfig
          :orientation="node.antennaOrientation"
          :gainDbi="node.txGainDbi"
          :azimuth="node.directionalParams?.azimuth ?? 0"
          :beamwidth="node.directionalParams?.beamwidth ?? 60"
          @update:orientation="v => nodesStore.updateNode(node!.id, { antennaOrientation: v })"
          @update:gainDbi="v => nodesStore.updateNode(node!.id, { txGainDbi: v })"
          @update:azimuth="v => nodesStore.updateNode(node!.id, {
            directionalParams: { azimuth: v, beamwidth: node!.directionalParams?.beamwidth ?? 60 }
          })"
          @update:beamwidth="v => nodesStore.updateNode(node!.id, {
            directionalParams: { azimuth: node!.directionalParams?.azimuth ?? 0, beamwidth: v }
          })"
        />
      </div>
    </div>

    <!-- Action buttons (always visible) -->
    <div class="mt-3 d-flex gap-2">
      <button class="btn btn-success btn-sm" @click="$emit('runCoverage', node!.id)">
        Run Coverage
      </button>
      <button class="btn btn-danger btn-sm" @click="nodesStore.removeNode(node!.id)">
        Delete Node
      </button>
    </div>
  </div>

  <div v-else class="text-muted small">
    Select a node to edit its parameters.
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useNodesStore } from '../stores/nodesStore'
import DevicePresetSelector from './DevicePresetSelector.vue'
import ChannelPresetSelector from './ChannelPresetSelector.vue'
import InstallationConfig from './InstallationConfig.vue'
import AntennaConfig from './AntennaConfig.vue'
import type { ChannelPresetId } from '../types/index'

defineEmits<{ runCoverage: [nodeId: string] }>()

const nodesStore = useNodesStore()
const node = computed(() => nodesStore.selectedNode)
const showAdvanced = ref(false)
const fetchingAltitude = ref(false)

async function fetchAltitude() {
  if (!node.value) return
  fetchingAltitude.value = true
  try {
    const res = await fetch(
      `https://api.open-meteo.com/v1/elevation?latitude=${node.value.lat}&longitude=${node.value.lon}`
    )
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    const elevation = data.elevation?.[0]
    if (typeof elevation === 'number') {
      nodesStore.updateNode(node.value.id, { elevationM: Math.round(elevation) })
    }
  } catch (err) {
    console.error('[NodeEditor] Failed to fetch altitude:', err)
  } finally {
    fetchingAltitude.value = false
  }
}

function onDeviceChange(presetId: string) {
  if (!node.value) return
  if (presetId) {
    nodesStore.applyDevicePreset(node.value.id, presetId)
  } else {
    nodesStore.updateNode(node.value.id, { devicePresetId: undefined })
  }
}

function onChannelChange(presetId: string) {
  if (!node.value) return
  nodesStore.applyChannelPreset(node.value.id, presetId as ChannelPresetId)
}
</script>
