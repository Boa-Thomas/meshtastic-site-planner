<template>
  <div>
    <label class="form-label">Channel</label>
    <select
      class="form-select form-select-sm"
      :value="modelValue"
      @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value as ChannelPresetId)"
    >
      <option v-for="preset in channelPresets" :key="preset.id" :value="preset.id">
        {{ preset.name }} (SF{{ preset.sf }}/BW{{ preset.bw }}, {{ preset.sensitivityDbm }}dBm)
      </option>
    </select>
  </div>
</template>

<script setup lang="ts">
import { channelPresets } from '../data/channelPresets'
import type { ChannelPresetId } from '../types/index'

defineProps<{ modelValue: ChannelPresetId }>()
defineEmits<{ 'update:modelValue': [value: ChannelPresetId] }>()
</script>
