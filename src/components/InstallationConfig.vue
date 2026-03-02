<template>
  <div class="row g-2">
    <div class="col-6">
      <label class="form-label">Installation</label>
      <select
        class="form-select form-select-sm"
        :value="installationType"
        @change="onInstallationTypeChange(($event.target as HTMLSelectElement).value as InstallationType)"
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
    <template v-if="installationType === 'window'">
      <div class="col-6">
        <label class="form-label">Window Start (°)</label>
        <input
          type="number"
          class="form-control form-control-sm"
          :value="windowCone?.startDeg ?? 0"
          step="5"
          @input="onConeStartChange(parseFloat(($event.target as HTMLInputElement).value))"
        />
      </div>
      <div class="col-6">
        <label class="form-label">Window End (°)</label>
        <input
          type="number"
          class="form-control form-control-sm"
          :value="windowCone?.endDeg ?? 180"
          step="5"
          @input="onConeEndChange(parseFloat(($event.target as HTMLInputElement).value))"
        />
      </div>
      <div class="col-12">
        <small class="text-muted">
          Angular range visible from the window. 0°=North, 90°=East, 180°=South, 270°=West.
        </small>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { InstallationType, ObstructionLevel } from '../types/index'

const props = defineProps<{
  installationType: InstallationType
  obstructionLevel: ObstructionLevel
  windowCone?: { startDeg: number; endDeg: number }
}>()

const emit = defineEmits<{
  'update:installationType': [value: InstallationType]
  'update:obstructionLevel': [value: ObstructionLevel]
  'update:windowCone': [value: { startDeg: number; endDeg: number }]
}>()

function normalizeDeg(val: number): number {
  return ((val % 360) + 360) % 360
}

function onInstallationTypeChange(val: InstallationType) {
  emit('update:installationType', val)
  if (val === 'window' && !props.windowCone) {
    emit('update:windowCone', { startDeg: 0, endDeg: 180 })
  }
}

function onConeStartChange(val: number) {
  const end = props.windowCone?.endDeg ?? 180
  emit('update:windowCone', { startDeg: normalizeDeg(val), endDeg: end })
}

function onConeEndChange(val: number) {
  const start = props.windowCone?.startDeg ?? 0
  emit('update:windowCone', { startDeg: start, endDeg: normalizeDeg(val) })
}
</script>
