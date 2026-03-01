<template>
  <div>
    <label class="form-label">Device</label>
    <select
      class="form-select form-select-sm"
      :value="modelValue"
      @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
    >
      <option value="">Custom</option>
      <option v-for="preset in devicePresets" :key="preset.id" :value="preset.id">
        {{ preset.name }} ({{ preset.txPowerDbm }}dBm, {{ preset.chipset }})
      </option>
    </select>
  </div>
</template>

<script setup lang="ts">
import { devicePresets } from '../data/devicePresets'

defineProps<{ modelValue: string }>()
defineEmits<{ 'update:modelValue': [value: string] }>()
</script>
