<template>
  <div v-if="show" class="modal d-block" tabindex="-1" role="dialog" aria-modal="true" @click.self="onClose">
    <div class="modal-backdrop fade show"></div>
    <div class="modal-dialog modal-dialog-centered" style="z-index: 1056;">
      <div class="modal-content shadow-lg">
        <div class="modal-header">
          <h5 class="modal-title">High-Resolution Export</h5>
          <button type="button" class="btn-close" :disabled="loading" @click="onClose" aria-label="Close"></button>
        </div>
        <div class="modal-body">
          <!-- Format selector -->
          <div class="mb-3">
            <label class="form-label fw-semibold">Format</label>
            <div class="btn-group w-100" role="group">
              <input id="fmt-png" type="radio" class="btn-check" name="fmt" value="png" v-model="format" :disabled="loading">
              <label for="fmt-png" class="btn btn-outline-secondary">PNG</label>
              <input id="fmt-pdf" type="radio" class="btn-check" name="fmt" value="pdf" v-model="format" :disabled="loading">
              <label for="fmt-pdf" class="btn btn-outline-secondary">PDF</label>
              <input id="fmt-zip" type="radio" class="btn-check" name="fmt" value="png-zip" v-model="format" :disabled="loading">
              <label for="fmt-zip" class="btn btn-outline-secondary">PNG ZIP</label>
            </div>
            <div v-if="format === 'png-zip'" class="form-text">
              Tiled PNG chunks + manifest.json, useful for QGIS or large prints.
            </div>
            <div v-if="format === 'pdf'" class="form-text">
              Single PDF with JPEG-compressed image (default quality 90%).
            </div>
          </div>

          <!-- Resolution -->
          <div class="mb-3">
            <label class="form-label fw-semibold">Resolution</label>
            <div class="form-check">
              <input id="res-street" type="radio" class="form-check-input" v-model="resolutionMode" value="street-readable" :disabled="loading">
              <label for="res-street" class="form-check-label">
                <strong>Street-readable</strong> — recommended
                <div class="text-muted small">Basemap zoomed so street names are legible (zoom ≥ {{ streetReadableZoom }}).</div>
              </label>
            </div>
            <div class="form-check">
              <input id="res-fit" type="radio" class="form-check-input" v-model="resolutionMode" value="fit-overlay" :disabled="loading">
              <label for="res-fit" class="form-check-label">
                Fit overlay native resolution
                <div class="text-muted small">Matches raster pixel size. Smaller output but no street labels in low-density areas.</div>
              </label>
            </div>
            <div class="form-check">
              <input id="res-width" type="radio" class="form-check-input" v-model="resolutionMode" value="manual-width" :disabled="loading">
              <label for="res-width" class="form-check-label">Manual width:</label>
              <input type="number" class="form-control form-control-sm d-inline-block ms-2" style="width:120px" min="500" max="32768" step="500"
                     v-model.number="manualWidth" :disabled="loading || resolutionMode !== 'manual-width'">
              <span class="text-muted small ms-1">px</span>
            </div>
            <div class="form-check">
              <input id="res-zoom" type="radio" class="form-check-input" v-model="resolutionMode" value="manual-zoom" :disabled="loading">
              <label for="res-zoom" class="form-check-label">Manual zoom:</label>
              <select class="form-select form-select-sm d-inline-block ms-2" style="width:90px"
                      v-model.number="manualZoom" :disabled="loading || resolutionMode !== 'manual-zoom'">
                <option v-for="z in zoomChoices" :key="z" :value="z">{{ z }}</option>
              </select>
            </div>

            <!-- Live estimate panel -->
            <div v-if="estimate" class="mt-2 p-2 bg-light border rounded small">
              <div><strong>Output:</strong> {{ estimate.width.toLocaleString() }} × {{ estimate.height.toLocaleString() }} px (~{{ estimate.sizeMB }} MB raw)</div>
              <div><strong>Zoom {{ estimate.zoom }}</strong> — {{ estimate.tierLabel }} (~{{ estimate.metresPerPixel }} m/px)</div>
              <div v-if="estimate.tiles" class="text-muted">Basemap: ~{{ estimate.tiles.toLocaleString() }} tiles to fetch</div>
            </div>
          </div>

          <!-- Content toggles -->
          <div class="mb-3">
            <label class="form-label fw-semibold">Include</label>
            <div class="form-check">
              <input id="inc-base" type="checkbox" class="form-check-input" v-model="includeBasemap" :disabled="loading">
              <label for="inc-base" class="form-check-label">
                Basemap
                <select class="form-select form-select-sm d-inline-block ms-2" style="width:140px"
                        v-model="baseLayer" :disabled="loading || !includeBasemap">
                  <option value="OSM">OSM</option>
                  <option value="Carto Light">Carto Light</option>
                </select>
              </label>
            </div>
            <div class="form-check">
              <input id="inc-markers" type="checkbox" class="form-check-input" v-model="includeMarkers" :disabled="loading">
              <label for="inc-markers" class="form-check-label">Node markers</label>
            </div>
            <div class="form-check">
              <input id="inc-cbar" type="checkbox" class="form-check-input" v-model="includeColorbar" :disabled="loading">
              <label for="inc-cbar" class="form-check-label">Colorbar / dBm legend</label>
            </div>
            <div class="form-check">
              <input id="inc-attr" type="checkbox" class="form-check-input" v-model="includeAttribution" :disabled="loading">
              <label for="inc-attr" class="form-check-label">Attribution</label>
            </div>
          </div>

          <!-- Advanced -->
          <details class="mb-2">
            <summary class="text-muted small">Advanced</summary>
            <div class="mt-2">
              <div class="row g-2 align-items-center">
                <div class="col-auto">
                  <label class="form-label small mb-0">Resample:</label>
                </div>
                <div class="col-auto">
                  <select class="form-select form-select-sm" v-model="resample" :disabled="loading">
                    <option value="lanczos">Lanczos (sharp)</option>
                    <option value="bilinear">Bilinear (smooth)</option>
                    <option value="nearest">Nearest (pixelated)</option>
                  </select>
                </div>
                <div class="col-auto form-check">
                  <input id="adv-retina" type="checkbox" class="form-check-input" v-model="retina" :disabled="loading">
                  <label for="adv-retina" class="form-check-label small">Retina tiles (@2x)</label>
                </div>
              </div>
              <div v-if="format === 'pdf'" class="mt-2">
                <label class="form-label small mb-0">JPEG quality inside PDF:</label>
                <input type="range" class="form-range" min="0.5" max="0.98" step="0.02"
                       v-model.number="jpegQuality" :disabled="loading">
                <span class="text-muted small">{{ Math.round(jpegQuality * 100) }}%</span>
              </div>
            </div>
          </details>

          <!-- Status / progress -->
          <div v-if="loading || progress.stage !== 'idle'" class="mt-3">
            <div class="d-flex justify-content-between small">
              <span>{{ stageLabel }}</span>
              <span>{{ progress.pct }}%</span>
            </div>
            <div class="progress" style="height: 8px;">
              <div class="progress-bar" :class="progressClass" role="progressbar"
                   :style="{ width: progress.pct + '%' }"></div>
            </div>
            <div v-if="progress.message" class="text-muted small mt-1">{{ progress.message }}</div>
          </div>

          <div v-if="error" class="alert alert-danger small mt-3 mb-0">{{ error }}</div>

          <div v-if="warning" class="alert alert-warning small mt-3 mb-0">{{ warning }}</div>
        </div>

        <div class="modal-footer">
          <button v-if="loading" type="button" class="btn btn-outline-danger" @click="onCancel">Cancel</button>
          <template v-else>
            <button type="button" class="btn btn-secondary" @click="onClose">Close</button>
            <button type="button" class="btn btn-primary" :disabled="!canExport" @click="onExport">
              Export
            </button>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useExportHiRes, type HiResFormat, type ResolutionMode } from '../composables/useExportHiRes'
import { useSitesStore } from '../stores/sitesStore'
import { useMapStore } from '../stores/mapStore'
import { CORS_FRIENDLY_LAYERS } from '../utils/tileFetch'
import {
  autoFitZoom,
  detailTierForZoom,
  DETAIL_TIER_LABEL,
  STREET_READABLE_ZOOM,
  tightBoundsForSites,
  tileMetresPerPixel,
  worldRectForBounds,
} from '../services/hiResRenderer'
import type { RenderResample } from '../services/api'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const sitesStore = useSitesStore()
const mapStore = useMapStore()
const { loading, error, progress, exportHiRes, cancel } = useExportHiRes()

const format = ref<HiResFormat>('png')
const resolutionMode = ref<ResolutionMode>('street-readable')
const manualWidth = ref(8000)
const manualZoom = ref(15)
const includeBasemap = ref(true)
const includeMarkers = ref(true)
const includeColorbar = ref(true)
const includeAttribution = ref(true)
const baseLayer = ref<string>('OSM')
const resample = ref<RenderResample>('lanczos')
const retina = ref(false)
const jpegQuality = ref(0.9)

interface Estimate {
  width: number
  height: number
  sizeMB: string
  zoom: number
  metresPerPixel: string
  tierLabel: string
  tiles: number
}
const estimate = ref<Estimate | null>(null)
const warning = ref<string>('')

const streetReadableZoom = STREET_READABLE_ZOOM
const zoomChoices = [10, 11, 12, 13, 14, 15, 16, 17, 18]

const canExport = computed(() => {
  const hasSites = sitesStore.localSites.some((s) => s.visible && !s.isPreview && s.taskId && s.raster)
  return hasSites && !loading.value
})

const stageLabel = computed(() => {
  switch (progress.value.stage) {
    case 'preparing': return 'Preparing'
    case 'tiles': return 'Fetching basemap tiles'
    case 'overlay': return 'Rendering coverage overlay'
    case 'composite': return 'Compositing markers / legend'
    case 'encode': return 'Encoding output'
    case 'done': return 'Done'
    case 'error': return 'Failed'
    default: return 'Idle'
  }
})

const progressClass = computed(() => {
  if (progress.value.stage === 'done') return 'bg-success'
  if (progress.value.stage === 'error') return 'bg-danger'
  return ''
})

function recomputeEstimate() {
  warning.value = ''
  const sites = sitesStore.localSites.filter((s) => s.visible && !s.isPreview && s.raster)
  if (sites.length === 0) {
    estimate.value = null
    return
  }
  const bounds = tightBoundsForSites(sites)
  if (!bounds || !bounds.isValid()) {
    estimate.value = null
    return
  }
  let zoom = 14
  let finestPxDeg = Infinity
  for (const s of sites) {
    const px = (s.raster as any)?.pixelWidth
    if (typeof px === 'number' && px > 0 && px < finestPxDeg) finestPxDeg = px
  }
  if (resolutionMode.value === 'manual-zoom') {
    zoom = manualZoom.value
  } else if (resolutionMode.value === 'manual-width') {
    for (let z = 1; z <= 19; z++) {
      const r = worldRectForBounds(bounds, z)
      if (r.width >= manualWidth.value) { zoom = z; break }
      zoom = z
    }
  } else if (resolutionMode.value === 'street-readable') {
    const fromRaster = isFinite(finestPxDeg)
      ? autoFitZoom(bounds, finestPxDeg, 19, STREET_READABLE_ZOOM)
      : STREET_READABLE_ZOOM
    zoom = Math.max(fromRaster, STREET_READABLE_ZOOM)
  } else if (resolutionMode.value === 'fit-overlay') {
    if (isFinite(finestPxDeg)) zoom = autoFitZoom(bounds, finestPxDeg)
  }

  zoom = Math.max(1, Math.min(19, Math.round(zoom)))
  const rect = worldRectForBounds(bounds, zoom)
  const sizeMB = ((rect.width * rect.height * 4) / (1024 * 1024)).toFixed(0)
  const mpx = tileMetresPerPixel(bounds.getCenter().lat, zoom)
  const tier = detailTierForZoom(zoom)
  // Tile count estimate: cols * rows at 256px (or 512px retina)
  const tileSize = retina.value ? 512 : 256
  const tilesEstimate = Math.ceil(rect.width / tileSize) * Math.ceil(rect.height / tileSize)
  estimate.value = {
    width: rect.width,
    height: rect.height,
    sizeMB,
    zoom,
    metresPerPixel: mpx >= 100 ? mpx.toFixed(0) : mpx.toFixed(1),
    tierLabel: DETAIL_TIER_LABEL[tier],
    tiles: tilesEstimate,
  }
  if (rect.width > 8000 || rect.height > 8000) {
    warning.value = `Output is ${rect.width.toLocaleString()}×${rect.height.toLocaleString()} px; will be tiled into chunks. Consider lowering the zoom or selecting "Fit overlay" if street-level detail isn't needed.`
  } else if (tilesEstimate > 2000) {
    warning.value = `Will download ~${tilesEstimate.toLocaleString()} basemap tiles -- may take several minutes and stress the tile provider.`
  }
}

watch(
  () => [
    resolutionMode.value,
    manualWidth.value,
    manualZoom.value,
    sitesStore.localSites.length,
    props.show,
  ],
  () => {
    if (props.show) recomputeEstimate()
  },
  { immediate: true },
)

onMounted(() => {
  // Default basemap = current if CORS-friendly, else OSM
  baseLayer.value = CORS_FRIENDLY_LAYERS.has(mapStore.currentBaseLayer)
    ? mapStore.currentBaseLayer
    : 'OSM'
  // Retina is supported only by Carto Light
  retina.value = false
  recomputeEstimate()
})

watch(baseLayer, (v) => {
  if (v !== 'Carto Light') retina.value = false
})

watch(retina, () => recomputeEstimate())

function onClose() {
  if (loading.value) return
  emit('close')
}

function onCancel() {
  cancel()
}

async function onExport() {
  await exportHiRes({
    format: format.value,
    baseLayer: baseLayer.value,
    includeBasemap: includeBasemap.value,
    includeMarkers: includeMarkers.value,
    includeColorbar: includeColorbar.value,
    includeAttribution: includeAttribution.value,
    resolutionMode: resolutionMode.value,
    manualWidth: manualWidth.value,
    manualZoom: manualZoom.value,
    resample: resample.value,
    retina: retina.value,
    jpegQuality: jpegQuality.value,
  })
}

</script>

<style scoped>
.modal.d-block {
  position: fixed;
  inset: 0;
  z-index: 1055;
  overflow-y: auto;
}
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
}
.modal-dialog {
  margin: 1.75rem auto;
  position: relative;
}
</style>
