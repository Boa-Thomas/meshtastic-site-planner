<template>
  <div>
    <div class="row g-2">
      <div class="col-6">
        <label class="form-label">Antenna</label>
        <select
          class="form-select form-select-sm"
          v-model="selectedAntennaId"
          @change="onAntennaChange"
        >
          <option v-for="a in antennaPresets" :key="a.id" :value="a.id">
            {{ a.name }} ({{ a.gainDbi }}dBi)
          </option>
        </select>
      </div>
      <div class="col-6">
        <label class="form-label">Orientation</label>
        <select
          class="form-select form-select-sm"
          :value="orientation"
          @change="$emit('update:orientation', ($event.target as HTMLSelectElement).value as AntennaOrientation)"
        >
          <option value="omnidirectional">Omni</option>
          <option value="directional">Directional</option>
        </select>
      </div>
    </div>
    <div v-if="orientation === 'directional'" class="row g-2 mt-2">
      <div class="col-6">
        <label class="form-label">Azimuth (deg)</label>
        <input
          type="number"
          class="form-control form-control-sm"
          :value="azimuth"
          min="0"
          max="360"
          step="1"
          @input="$emit('update:azimuth', parseFloat(($event.target as HTMLInputElement).value))"
        />
      </div>
      <div class="col-6">
        <label class="form-label">Beamwidth (deg)</label>
        <input
          type="number"
          class="form-control form-control-sm"
          :value="beamwidth"
          min="5"
          max="180"
          step="1"
          @input="$emit('update:beamwidth', parseFloat(($event.target as HTMLInputElement).value))"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { antennaPresets } from '../data/antennaPresets'
import type { AntennaOrientation } from '../types/index'

defineProps<{
  orientation: AntennaOrientation
  gainDbi: number
  azimuth: number
  beamwidth: number
}>()

const emit = defineEmits<{
  'update:orientation': [value: AntennaOrientation]
  'update:gainDbi': [value: number]
  'update:azimuth': [value: number]
  'update:beamwidth': [value: number]
}>()

// Default to the first antenna preset
const selectedAntennaId = ref(antennaPresets[0].id)

function onAntennaChange() {
  const preset = antennaPresets.find(a => a.id === selectedAntennaId.value)
  if (!preset) return
  emit('update:gainDbi', preset.gainDbi)
  emit('update:orientation', preset.type)
  if (preset.beamwidthDeg !== undefined) {
    emit('update:beamwidth', preset.beamwidthDeg)
  }
}
</script>
