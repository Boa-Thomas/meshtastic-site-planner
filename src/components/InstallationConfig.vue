<template>
  <div class="row g-2">
    <div class="col-6">
      <label class="form-label">Installation</label>
      <select
        class="form-select form-select-sm"
        :value="installationType"
        @change="$emit('update:installationType', ($event.target as HTMLSelectElement).value as InstallationType)"
      >
        <option value="portable">Portable</option>
        <option value="window">Window</option>
        <option value="rooftop">Rooftop</option>
        <option value="mast">Mast</option>
        <option value="tower">Tower</option>
      </select>
    </div>
    <div class="col-6">
      <label class="form-label">Obstruction</label>
      <select
        class="form-select form-select-sm"
        :value="obstructionLevel"
        @change="$emit('update:obstructionLevel', ($event.target as HTMLSelectElement).value as ObstructionLevel)"
      >
        <option value="clear">Clear</option>
        <option value="partial">Partial</option>
        <option value="heavy">Heavy</option>
      </select>
    </div>
    <div v-if="installationType === 'window'" class="col-6">
      <label class="form-label">Window Azimuth (°)</label>
      <input
        type="number"
        class="form-control form-control-sm"
        :value="windowAzimuth ?? 0"
        min="0"
        max="360"
        step="1"
        @input="$emit('update:windowAzimuth', parseFloat(($event.target as HTMLInputElement).value))"
      />
      <small class="text-muted">0=N, 90=E, 180=S, 270=W</small>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { InstallationType, ObstructionLevel } from '../types/index'

defineProps<{
  installationType: InstallationType
  obstructionLevel: ObstructionLevel
  windowAzimuth?: number
}>()

defineEmits<{
  'update:installationType': [value: InstallationType]
  'update:obstructionLevel': [value: ObstructionLevel]
  'update:windowAzimuth': [value: number]
}>()
</script>
