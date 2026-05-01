<template>
  <form novalidate>
    <div v-if="loadError" class="alert alert-warning small py-1 px-2 mb-2">
      Failed to load server terrain settings. Falling back to defaults.
    </div>

    <div class="row g-2">
      <div class="col-12">
        <label for="dem_source" class="form-label">
          DEM Source
          <span v-if="settings && terrain.dem_source === ''" class="text-muted small">
            (server default: {{ settings.defaults.dem_source }})
          </span>
        </label>
        <select v-model="terrain.dem_source" id="dem_source" class="form-select form-select-sm">
          <option value="">— server default —</option>
          <option v-for="src in settings?.dem_sources ?? []"
                  :key="src.id"
                  :value="src.id"
                  :disabled="!src.ready">
            {{ src.id }}{{ src.ready ? '' : ' (not configured)' }}
          </option>
        </select>
        <div v-if="demSourceNote" class="form-text text-warning">{{ demSourceNote }}</div>
      </div>

      <div class="col-12">
        <label for="clutter_source" class="form-label">
          Clutter Source
          <span v-if="settings && terrain.clutter_source === ''" class="text-muted small">
            (server default: {{ settings.defaults.clutter_source }})
          </span>
        </label>
        <select v-model="terrain.clutter_source" id="clutter_source" class="form-select form-select-sm">
          <option value="">— server default —</option>
          <option v-for="src in settings?.clutter_sources ?? []"
                  :key="src.id"
                  :value="src.id"
                  :disabled="!src.ready">
            {{ src.id }}{{ src.ready ? '' : ' (not configured)' }}
          </option>
        </select>
        <div v-if="clutterSourceNote" class="form-text text-warning">{{ clutterSourceNote }}</div>
      </div>

      <div class="col-12" v-if="terrain.clutter_source !== '' && terrain.clutter_source !== 'none'">
        <label for="clutter_penetration_factor" class="form-label">
          Penetration Factor
          <span class="text-muted small">
            ({{ terrain.clutter_penetration_factor === null
                ? `server default: ${settings?.defaults.clutter_penetration_factor ?? 0.6}`
                : terrain.clutter_penetration_factor.toFixed(2) }})
          </span>
        </label>
        <input v-model.number="penetrationModel"
               type="range" min="0" max="1" step="0.05"
               id="clutter_penetration_factor"
               class="form-range" />
        <div class="d-flex justify-content-between small text-muted">
          <span>0.0 invisible</span>
          <span>0.5</span>
          <span>1.0 solid</span>
        </div>
        <button type="button"
                class="btn btn-link btn-sm p-0"
                v-if="terrain.clutter_penetration_factor !== null"
                @click="terrain.clutter_penetration_factor = null">
          Reset to server default
        </button>
      </div>

      <div v-if="settings && !settings.calibration.factor_calibrated" class="col-12">
        <div class="alert alert-warning small py-1 px-2 mb-0">
          <strong>Uncalibrated.</strong>
          The penetration factor on this server is a placeholder
          ({{ settings.defaults.clutter_penetration_factor }}) — calibration
          against field RSSI measurements is still pending.
          <span v-if="settings.calibration.calibration_notes">
            {{ settings.calibration.calibration_notes }}
          </span>
        </div>
      </div>
    </div>
  </form>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useSitesStore } from '../stores/sitesStore'
import type { TerrainSettings } from '../types'

const store = useSitesStore()
// Initialize lazily — older state shapes might not have a terrain block.
if (!store.splatParams.terrain) {
  store.splatParams.terrain = {
    dem_source: '',
    clutter_source: '',
    clutter_penetration_factor: null,
  }
}
const terrain = store.splatParams.terrain!

const settings = ref<TerrainSettings | null>(null)
const loadError = ref(false)

// `null` is the "use server default" sentinel; v-model.number can't bind it
// directly to a range input. This intermediate prop lets the slider write a
// concrete number while a Reset button restores the null sentinel.
const penetrationModel = computed<number>({
  get() {
    return terrain.clutter_penetration_factor ?? (settings.value?.defaults.clutter_penetration_factor ?? 0.6)
  },
  set(val) {
    terrain.clutter_penetration_factor = val
  },
})

const demSourceNote = computed(() => {
  if (!settings.value || terrain.dem_source === '') return null
  const src = settings.value.dem_sources.find(s => s.id === terrain.dem_source)
  return src?.note ?? null
})

const clutterSourceNote = computed(() => {
  if (!settings.value || terrain.clutter_source === '') return null
  const src = settings.value.clutter_sources.find(s => s.id === terrain.clutter_source)
  return src?.note ?? null
})

onMounted(async () => {
  try {
    const response = await fetch('/api/settings/terrain')
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    settings.value = await response.json()
  } catch (err) {
    console.warn('[TerrainConfig] failed to load /api/settings/terrain', err)
    loadError.value = true
  }
})
</script>
