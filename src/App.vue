<template>
  <div>
    <nav class="navbar navbar-dark bg-dark fixed-top">
      <div class="container-fluid">
        <a class="navbar-brand" href="#">
          <img src="/logo.svg" alt="Meshtastic Logo" width="30" height="30" class="d-inline">
          Meshtastic Site Planner
        </a>
        <button class="navbar-toggler" type="button" data-bs-toggle="offcanvas" data-bs-target="#offcanvasDarkNavbar" aria-controls="offcanvasDarkNavbar" aria-label="Toggle navigation">
          <span class="navbar-toggler-icon"></span>
        </button>
        <div class="offcanvas offcanvas-end text-bg-dark show" tabindex="-1" id="offcanvasDarkNavbar" aria-labelledby="offcanvasDarkNavbarLabel" data-bs-backdrop="false">
          <div class="offcanvas-header">
            <h5 class="offcanvas-title" id="offcanvasDarkNavbarLabel">Site Parameters</h5>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="offcanvas" aria-label="Close"></button>
          </div>
          <div class="offcanvas-body">
            <ul class="navbar-nav">
              <!-- 1. Mesh Nodes -->
              <li class="nav-item">
                <a class="nav-link dropdown-toggle" href="#" role="button"
                   @click.prevent="togglePanel('meshNodes')"
                   :aria-expanded="openPanels.has('meshNodes')">Mesh Nodes</a>
                <ul :class="['dropdown-menu', 'dropdown-menu-dark', 'p-3', { show: openPanels.has('meshNodes') }]"
                    style="position:static">
                  <li>
                    <!-- Add Node button -->
                    <button
                      type="button"
                      class="btn btn-sm mb-3 w-100"
                      :class="nodesStore.isPlacingNode ? 'btn-warning' : 'btn-primary'"
                      @click="toggleNodePlacement"
                    >
                      {{ nodesStore.isPlacingNode ? 'Click map to place node...' : 'Add Node' }}
                    </button>

                    <!-- Node list -->
                    <NodeList />

                    <!-- Settings stale alert -->
                    <div v-if="settingsStale" class="alert alert-warning alert-dismissible py-1 px-2 small mt-2">
                      Settings changed since last coverage run. Rerun coverage to update results.
                      <button type="button" class="btn-close btn-sm" @click="settingsStale = false" aria-label="Close"></button>
                    </div>

                    <!-- Run All Coverage button -->
                    <button
                      v-if="nodesStore.nodes.length > 0"
                      class="btn btn-sm btn-success w-100 mt-2"
                      :disabled="nodesStore.nodes.length === 0 || runAllState === 'running'"
                      @click="onRunAllCoverage"
                    >
                      <span v-if="runAllState === 'running'" class="spinner-border spinner-border-sm me-1"></span>
                      {{ runAllState === 'running' ? `Coverage ${runAllProgress.current}/${runAllProgress.total}...` : 'Run All Coverage' }}
                    </button>

                    <!-- Per-task progress during Run All -->
                    <div v-if="taskProgressMap.size > 0" class="mt-2">
                      <div v-for="[taskId, tp] in taskProgressMap" :key="taskId" class="mb-1">
                        <div class="d-flex justify-content-between align-items-center">
                          <span class="small text-truncate" style="max-width: 120px;" :title="tp.nodeName">{{ tp.nodeName }}</span>
                          <span class="small text-muted d-flex gap-1 align-items-center">
                            <span>{{ taskStatusLabel(tp) }}</span>
                            <span v-if="estimatedEta(tp)" class="text-info">{{ estimatedEta(tp) }}</span>
                          </span>
                        </div>
                        <div class="progress" style="height: 3px;">
                          <div class="progress-bar"
                               :class="{
                                 'bg-success': tp.status === 'completed',
                                 'bg-danger': tp.status === 'failed',
                                 'progress-bar-striped progress-bar-animated': tp.status === 'processing',
                               }"
                               :style="{ width: (tp.status === 'completed' ? 100 : tp.status === 'failed' ? 100 : displayProgress(tp) * 100) + '%' }">
                          </div>
                        </div>
                      </div>

                      <!-- Inline system debug during simulation -->
                      <div class="mt-2 border-top border-secondary pt-2">
                        <button class="btn btn-link btn-sm text-muted p-0 small text-decoration-none"
                                @click="togglePanel('debug-inline')">
                          Sistema {{ openPanels.has('debug-inline') ? '▲' : '▼' }}
                        </button>
                        <div v-if="openPanels.has('debug-inline') || runAllState === 'running'">
                          <DebugPanel :auto-start="runAllState === 'running'" />
                        </div>
                      </div>
                    </div>

                    <!-- Coverage overlays list -->
                    <div v-if="sitesStore.localSites.length > 0" class="mt-2">
                      <div class="d-flex gap-1 mb-2">
                        <button class="btn btn-outline-light btn-sm flex-fill" @click="sitesStore.hideAllOverlays()">
                          Hide All
                        </button>
                        <button class="btn btn-outline-light btn-sm flex-fill" @click="sitesStore.showAllOverlays()">
                          Show All
                        </button>
                        <button class="btn btn-outline-danger btn-sm flex-fill" @click="onResetAllCoverage">
                          Reset All
                        </button>
                      </div>
                      <ul class="list-group">
                        <li class="list-group-item d-flex justify-content-between align-items-center py-1 px-2"
                            v-for="(site, index) in sitesStore.localSites" :key="site.taskId"
                            :style="{ opacity: site.visible ? 1 : 0.5 }">
                          <button class="btn btn-sm p-0 me-2"
                                  :class="site.visible ? 'btn-outline-success' : 'btn-outline-secondary'"
                                  @click="sitesStore.toggleSiteVisibility(index)"
                                  :title="site.visible ? 'Hide overlay' : 'Show overlay'"
                                  style="width: 24px; height: 24px; line-height: 1; font-size: 12px;">
                            {{ site.visible ? 'V' : 'H' }}
                          </button>
                          <span class="flex-fill text-truncate small">
                            {{ site.params.transmitter.name }}
                            <span v-if="site.isPreview" class="badge bg-info ms-1">Preview</span>
                          </span>
                          <button type="button" @click="sitesStore.removeSite(index)" class="btn-close btn-close-white btn-sm" aria-label="Remove"></button>
                        </li>
                      </ul>
                    </div>

                    <div v-if="runAllErrors.length > 0"
                         class="alert alert-warning alert-dismissible mt-2 py-1 px-2 small">
                      <strong>{{ runAllErrors.length }} node(s) failed:</strong>
                      <ul class="mb-0 ps-3">
                        <li v-for="(err, i) in runAllErrors" :key="i">{{ err }}</li>
                      </ul>
                      <button type="button" class="btn-close btn-sm"
                              @click="runAllErrors = []" aria-label="Close"></button>
                    </div>

                    <!-- Node editor (shown when a node is selected) -->
                    <div v-if="nodesStore.selectedNode" class="mt-3 border-top border-secondary pt-3">
                      <NodeEditor @runCoverage="onRunNodeCoverage" />
                    </div>
                  </li>
                </ul>
              </li>

              <!-- 2. Environment -->
              <li class="nav-item">
                <a class="nav-link dropdown-toggle" href="#" role="button"
                   @click.prevent="togglePanel('environment')"
                   :aria-expanded="openPanels.has('environment')">Environment</a>
                <ul :class="['dropdown-menu', 'dropdown-menu-dark', 'p-3', { show: openPanels.has('environment') }]"
                    style="position:static">
                  <li>
                    <Environment />
                  </li>
                </ul>
              </li>

              <!-- 3. Simulation Options -->
              <li class="nav-item">
                <a class="nav-link dropdown-toggle" href="#" role="button"
                   @click.prevent="togglePanel('simulation')"
                   :aria-expanded="openPanels.has('simulation')">Simulation Options</a>
                <ul :class="['dropdown-menu', 'dropdown-menu-dark', 'p-3', { show: openPanels.has('simulation') }]"
                    style="position:static">
                  <li>
                    <Simulation />
                  </li>
                </ul>
              </li>

              <!-- 4. Display -->
              <li class="nav-item">
                <a class="nav-link dropdown-toggle" href="#" role="button"
                   @click.prevent="togglePanel('display')"
                   :aria-expanded="openPanels.has('display')">Display</a>
                <ul :class="['dropdown-menu', 'dropdown-menu-dark', 'p-3', { show: openPanels.has('display') }]"
                    style="position:static">
                  <li>
                    <Display />
                  </li>
                </ul>
              </li>

              <!-- 5. Network Simulation (DES) -->
              <li class="nav-item">
                <a class="nav-link dropdown-toggle" href="#" role="button"
                   @click.prevent="togglePanel('des')"
                   :aria-expanded="openPanels.has('des')">Network Simulation (DES)</a>
                <ul :class="['dropdown-menu', 'dropdown-menu-dark', 'p-3', { show: openPanels.has('des') }]"
                    style="position:static">
                  <li>
                    <DesControls />
                    <div class="mt-3"><DesLinkOverlay /></div>
                    <div class="mt-3"><DesTraceroute /></div>
                    <div class="mt-3"><DesMetrics /></div>
                    <div class="mt-3"><DesEventLog /></div>
                  </li>
                </ul>
              </li>

            </ul>

            <!-- Project & Export buttons -->
            <div class="mt-3 d-flex flex-wrap gap-2">
              <button :disabled="exportLoading" @click="exportMap" type="button" class="btn btn-secondary btn-sm">
                <span :class="{ 'd-none': !exportLoading }" class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                Export PDF
              </button>
              <button @click="exportProject" :disabled="exporting" type="button" class="btn btn-outline-light btn-sm">
                <span v-if="exporting" class="spinner-border spinner-border-sm me-1"></span>
                Export Project
              </button>
              <label class="btn btn-outline-light btn-sm mb-0" :class="{ disabled: importing }">
                <span v-if="importing" class="spinner-border spinner-border-sm me-1"></span>
                Import Project
                <input type="file" accept=".json" class="d-none" @change="onImportFile" :disabled="importing">
              </label>
            </div>

            <div v-if="exportError" class="alert alert-warning alert-dismissible mt-2 py-1 px-2 small" role="alert">
              {{ exportError }}
              <button type="button" class="btn-close btn-sm" @click="exportError = ''" aria-label="Close"></button>
            </div>

            <div v-if="projectExportError" class="alert alert-warning alert-dismissible mt-2 py-1 px-2 small" role="alert">
              {{ projectExportError }}
              <button type="button" class="btn-close btn-sm" @click="projectExportError = ''" aria-label="Close"></button>
            </div>

            <div v-if="importError" class="alert alert-warning alert-dismissible mt-2 py-1 px-2 small" role="alert">
              {{ importError }}
              <button type="button" class="btn-close btn-sm" @click="importError = ''" aria-label="Close"></button>
            </div>

          </div>
        </div>
      </div>
    </nav>
    <div id="map" ref="map">
    </div>
  </div>
</template>

<script setup lang="ts">
import "leaflet/dist/leaflet.css"
import "bootstrap/dist/css/bootstrap.min.css"
import "bootstrap/dist/js/bootstrap.bundle.min.js"
import L from 'leaflet'
import { computed, markRaw, onMounted, onUnmounted, ref, watch } from 'vue'
import { reactive } from 'vue'

import Environment from "./components/Environment.vue"
import Simulation from "./components/Simulation.vue"
import Display from "./components/Display.vue"
import NodeList from "./components/NodeList.vue"
import NodeEditor from "./components/NodeEditor.vue"
import DesControls from "./components/des/DesControls.vue"
import DesLinkOverlay from "./components/des/DesLinkOverlay.vue"
import DesTraceroute from "./components/des/DesTraceroute.vue"
import DesMetrics from "./components/des/DesMetrics.vue"
import DesEventLog from "./components/des/DesEventLog.vue"
import DebugPanel from "./components/DebugPanel.vue"

import { useSitesStore } from './stores/sitesStore'
import { useMapStore } from './stores/mapStore'
import { useNodesStore } from './stores/nodesStore'
import { useExport } from './composables/useExport'
import { useProjectIO } from './composables/useProjectIO'
import { useDesVisualization } from './composables/useDesVisualization'
import { meshNodeMarker } from './layers'
import { nodeToSplatParams } from './utils/nodeToSplatParams'
import type { MeshNode } from './types/index'

const sitesStore = useSitesStore()
const mapStore = useMapStore()
const nodesStore = useNodesStore()
const { exportLoading, exportError, exportMap } = useExport()
const { exportProject, importProject, importing, importError, exporting, exportError: projectExportError } = useProjectIO()
useDesVisualization()

async function onImportFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await importProject(file)
  input.value = ''
}

// --- Window cone overlay ---

let coneLayer: L.Polygon | null = null

function destPoint(lat: number, lon: number, bearingDeg: number, distKm: number): [number, number] {
  const bearingRad = (bearingDeg * Math.PI) / 180
  const dLat = (distKm * Math.cos(bearingRad)) / 111.32
  const dLon = (distKm * Math.sin(bearingRad)) / (111.32 * Math.cos((lat * Math.PI) / 180))
  return [lat + dLat, lon + dLon]
}

function computeConePoints(
  lat: number, lon: number,
  startDeg: number, endDeg: number,
  radiusKm: number,
): [number, number][] {
  const norm = (v: number) => ((v % 360) + 360) % 360
  const s = norm(startDeg)
  const e = norm(endDeg)

  // Zero-width cone — nothing to render
  if (s === e) return []

  const arcPoints: [number, number][] = []
  const step = 3
  if (e > s) {
    for (let a = s; a < e; a += step) {
      arcPoints.push(destPoint(lat, lon, a, radiusKm))
    }
    arcPoints.push(destPoint(lat, lon, e, radiusKm))
  } else {
    // Wrap-around (e.g. 270° → 90° passing through North)
    for (let a = s; a < 360; a += step) {
      arcPoints.push(destPoint(lat, lon, a, radiusKm))
    }
    for (let a = 0; a < e; a += step) {
      arcPoints.push(destPoint(lat, lon, a, radiusKm))
    }
    arcPoints.push(destPoint(lat, lon, e, radiusKm))
  }
  return [[lat, lon], ...arcPoints]
}

function updateConeOverlay() {
  if (coneLayer) {
    coneLayer.remove()
    coneLayer = null
  }

  const map = mapStore.map
  if (!map) return

  const node = nodesStore.selectedNode
  if (
    !node ||
    node.installationType !== 'window' ||
    !node.windowCone
  ) return

  const points = computeConePoints(
    node.lat, node.lon,
    node.windowCone.startDeg, node.windowCone.endDeg,
    0.3, // 300 meters
  )

  coneLayer = markRaw(
    L.polygon(points, {
      color: '#3b82f6',
      weight: 2,
      opacity: 0.6,
      fillColor: '#3b82f6',
      fillOpacity: 0.15,
      interactive: false,
    }).addTo(map as L.Map)
  )
}

const coneWatchSource = computed(() => {
  const node = nodesStore.selectedNode
  if (!node) return null
  return {
    id: node.id,
    lat: node.lat,
    lon: node.lon,
    installationType: node.installationType,
    windowCone: node.windowCone,
  }
})

watch(coneWatchSource, updateConeOverlay, { deep: true })

onUnmounted(() => {
  if (coneLayer) {
    coneLayer.remove()
    coneLayer = null
  }
})

// Initialize the map (moved from Transmitter.vue)
onMounted(async () => {
  // Load nodes from server before initializing the map
  await nodesStore.initialize()

  const mapEl = document.getElementById('map') as HTMLElement
  let center: [number, number] = [-26.82, -49.27]
  if (nodesStore.nodes.length > 0) {
    const lats = nodesStore.nodes.map(n => n.lat)
    const lons = nodesStore.nodes.map(n => n.lon)
    center = [
      lats.reduce((a, b) => a + b, 0) / lats.length,
      lons.reduce((a, b) => a + b, 0) / lons.length,
    ]
  }
  mapStore.initMap(mapEl, center)
  if (nodesStore.nodes.length > 0 && mapStore.map) {
    const bounds = L.latLngBounds(
      nodesStore.nodes.map(n => [n.lat, n.lon] as [number, number])
    )
    mapStore.map.fitBounds(bounds.pad(0.2))
  }
})

// Track Leaflet markers for each mesh node by node ID
const nodeMarkers = new Map<string, L.Marker>()

// Run All Coverage state
const runAllState = ref<'idle' | 'running'>('idle')
const runAllProgress = ref({ current: 0, total: 0 })
const runAllErrors = ref<string[]>([])

// Per-task progress tracking (populated by SSE events)
interface TaskProgress {
  nodeName: string
  stage: string
  progress: number
  status: 'queued' | 'processing' | 'completed' | 'failed'
  startedAt?: number       // timestamp when first real progress arrived
  splatStartedAt?: number  // timestamp when running_splat began
}
const taskProgressMap = ref<Map<string, TaskProgress>>(new Map())

// Reactive clock for ETA calculation (ticks every second)
const now = ref(Date.now())
const _clockInterval = setInterval(() => { now.value = Date.now() }, 1000)
onUnmounted(() => clearInterval(_clockInterval))

const SPLAT_ESTIMATED_MS = 90_000 // estimated SPLAT! execution time

function displayProgress(tp: TaskProgress): number {
  if (tp.stage === 'running_splat' && tp.splatStartedAt) {
    const elapsed = now.value - tp.splatStartedAt
    const fraction = Math.min(elapsed / SPLAT_ESTIMATED_MS, 0.97)
    return 0.40 + fraction * 0.48 // animates 40% → ~88% over ~90s
  }
  return tp.progress
}

function estimatedEta(tp: TaskProgress): string | null {
  const dp = displayProgress(tp)
  if (!tp.startedAt || dp <= 0.05 || tp.status !== 'processing') return null
  const elapsed = now.value - tp.startedAt
  const remaining = elapsed * (1 - dp) / dp
  if (remaining < 5000) return null
  const secs = Math.round(remaining / 1000)
  return secs >= 60 ? `~${Math.floor(secs / 60)}m ${secs % 60}s` : `~${secs}s`
}

function stageLabel(stage: string): string {
  const labels: Record<string, string> = {
    downloading_tiles: 'Downloading terrain...',
    configuring: 'Configuring model...',
    running_splat: 'Running simulation...',
    converting: 'Generating result...',
  }
  return labels[stage] ?? (stage || 'Queued...')
}

function taskStatusLabel(tp: TaskProgress): string {
  if (tp.status === 'completed') return 'Done'
  if (tp.status === 'failed') return 'Failed'
  if (tp.status === 'queued') return 'Aguardando...'
  if (tp.status === 'processing' && !tp.stage) return 'Iniciando...'
  return stageLabel(tp.stage)
}

// Settings stale detection (only for RF-affecting params, not display)
const settingsStale = ref(false)
let skipInitialWatch = true
watch(
  () => ({
    env: sitesStore.splatParams.environment,
    sim: sitesStore.splatParams.simulation,
  }),
  () => {
    if (skipInitialWatch) {
      skipInitialWatch = false
      return
    }
    if (sitesStore.localSites.length > 0) {
      settingsStale.value = true
    }
  },
  { deep: true }
)

// Instant redraw when display settings change (colormap, min/max dBm, transparency)
// 4C.3 — Use updateDisplaySettings() to avoid destroying/recreating layers
watch(
  () => sitesStore.splatParams.display,
  () => {
    if (sitesStore.localSites.length > 0) {
      sitesStore.updateDisplaySettings()
    }
  },
  { deep: true }
)

// Which panels are currently expanded (meshNodes + display open by default)
const openPanels = reactive(new Set(['meshNodes', 'display']))
const togglePanel = (name: string) => {
  openPanels.has(name) ? openPanels.delete(name) : openPanels.add(name)
}

// --- Helper to create a draggable node marker ---

function createNodeMarker(node: MeshNode, map: L.Map): L.Marker {
  const marker = markRaw(
    L.marker([node.lat, node.lon], { icon: meshNodeMarker, draggable: true })
      .addTo(map)
      .bindPopup(node.name)
  )
  marker.on('click', () => { nodesStore.selectedNodeId = node.id })
  marker.on('dragend', () => {
    const pos = marker.getLatLng()
    const lat = parseFloat(pos.lat.toFixed(6))
    const lon = parseFloat(((((pos.lng + 180) % 360) + 360) % 360 - 180).toFixed(6))
    nodesStore.updateNode(node.id, { lat, lon })
  })
  nodeMarkers.set(node.id, marker)
  return marker
}

// --- Cleanup markers when nodes are removed ---

watch(
  () => new Set(nodesStore.nodes.map(n => n.id)),
  (currentIds) => {
    for (const [id, marker] of nodeMarkers) {
      if (!currentIds.has(id)) {
        marker.remove()
        nodeMarkers.delete(id)
      }
    }
  },
)

// --- Sync marker popups when node names change ---

watch(
  () => nodesStore.nodes.map(n => ({ id: n.id, name: n.name })),
  (nodeNames) => {
    for (const { id, name } of nodeNames) {
      const marker = nodeMarkers.get(id)
      if (marker) {
        marker.setPopupContent(name)
      }
    }
  },
  { deep: true }
)

// --- Sync marker positions when lat/lon change via form ---

watch(
  () => nodesStore.nodes.map(n => ({ id: n.id, lat: n.lat, lon: n.lon })),
  (nodePositions) => {
    for (const { id, lat, lon } of nodePositions) {
      const marker = nodeMarkers.get(id)
      if (marker) {
        const current = marker.getLatLng()
        if (Math.abs(current.lat - lat) > 0.000001 || Math.abs(current.lng - lon) > 0.000001) {
          marker.setLatLng([lat, lon])
        }
      }
    }
  },
  { deep: true }
)

// --- Restore markers for persisted nodes after map init ---

watch(
  () => [mapStore.map, nodesStore.nodes.length] as const,
  ([map]) => {
    if (!map) return
    for (const node of nodesStore.nodes) {
      if (nodeMarkers.has(node.id)) continue
      createNodeMarker(node, map as L.Map)
    }
  },
  { immediate: true }
)

// --- Mesh Node placement logic ---

function toggleNodePlacement() {
  if (nodesStore.isPlacingNode) {
    nodesStore.stopPlacingNode()
    if (mapStore.map) {
      mapStore.map.getContainer().style.cursor = ''
    }
  } else {
    nodesStore.startPlacingNode()
    if (mapStore.map) {
      mapStore.map.getContainer().style.cursor = 'crosshair'
      mapStore.map.once('click', onMapClickForNode)
    }
  }
}

function onMapClickForNode(e: L.LeafletMouseEvent) {
  if (!nodesStore.isPlacingNode) return

  const lat = parseFloat(e.latlng.lat.toFixed(6))
  let lon = e.latlng.lng
  // Normalise longitude to [-180, 180]
  lon = ((((lon + 180) % 360) + 360) % 360) - 180
  lon = parseFloat(lon.toFixed(6))

  const nodeCount = nodesStore.nodes.length + 1
  const node = nodesStore.createDefaultNode(lat, lon, `Node ${nodeCount}`)
  nodesStore.addNode(node)

  // Place a draggable marker on the map for this node
  if (mapStore.map) {
    createNodeMarker(node, mapStore.map as L.Map)
  }

  nodesStore.stopPlacingNode()
  if (mapStore.map) {
    mapStore.map.getContainer().style.cursor = ''
  }

  // Auto-open Mesh Nodes panel so the editor is immediately visible
  openPanels.add('meshNodes')
}

// --- Coverage simulation for a specific mesh node ---

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

/** Wait for a backend task to complete via SSE, with polling fallback. */
function waitForTaskCompletion(taskId: string): Promise<void> {
  return new Promise((resolve, reject) => {
    try {
      const es = new EventSource(`/events/${taskId}`)
      es.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (data.status === 'completed') {
          es.close()
          resolve()
        } else if (data.status === 'failed' || data.status === 'not_found') {
          es.close()
          reject(new Error(`SPLAT! simulation ${data.status}`))
        }
      }
      es.onerror = () => {
        es.close()
        console.warn('[SSE] Connection failed, falling back to polling')
        pollForCompletion(taskId).then(resolve, reject)
      }
    } catch {
      // EventSource not supported — fall back to polling
      pollForCompletion(taskId).then(resolve, reject)
    }
  })
}

async function pollForCompletion(taskId: string): Promise<void> {
  while (true) {
    await sleep(1000)
    const statusResponse = await fetch(`/status/${taskId}`)
    if (!statusResponse.ok) {
      if (statusResponse.status === 404) {
        throw new Error('Task expired — result not found (try re-running)')
      }
      throw new Error(`Status check failed (${statusResponse.status})`)
    }
    const { status } = await statusResponse.json()
    if (status === 'completed') return
    if (status === 'failed') throw new Error('SPLAT! simulation failed on backend')
  }
}

function buildPayload(node: MeshNode, radiusM: number, highRes: boolean) {
  const splatParams = nodeToSplatParams(node, {
    environment: sitesStore.splatParams.environment,
    simulation: sitesStore.splatParams.simulation,
    display: sitesStore.splatParams.display,
  })

  return {
    splatParams,
    payload: {
      lat: splatParams.transmitter.tx_lat,
      lon: splatParams.transmitter.tx_lon,
      tx_height: splatParams.transmitter.tx_height,
      tx_power: 10 * Math.log10(splatParams.transmitter.tx_power) + 30,
      tx_gain: splatParams.transmitter.tx_gain,
      frequency_mhz: splatParams.transmitter.tx_freq,
      rx_height: splatParams.receiver.rx_height,
      rx_gain: splatParams.receiver.rx_gain,
      signal_threshold: splatParams.receiver.rx_sensitivity,
      system_loss: splatParams.receiver.rx_loss,
      clutter_height: splatParams.environment.clutter_height,
      ground_dielectric: splatParams.environment.ground_dielectric,
      ground_conductivity: splatParams.environment.ground_conductivity,
      atmosphere_bending: splatParams.environment.atmosphere_bending,
      radio_climate: splatParams.environment.radio_climate,
      polarization: splatParams.environment.polarization,
      radius: radiusM,
      situation_fraction: splatParams.simulation.situation_fraction,
      time_fraction: splatParams.simulation.time_fraction,
      high_resolution: highRes,
    },
  }
}

async function runSinglePrediction(payload: Record<string, unknown>): Promise<{ taskId: string; arrayBuffer: ArrayBuffer }> {
  const predictResponse = await fetch('/predict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!predictResponse.ok) {
    const detail = await predictResponse.text()
    throw new Error(`Prediction failed (${predictResponse.status}): ${detail}`)
  }
  const { task_id: taskId } = await predictResponse.json()
  await waitForTaskCompletion(taskId)
  const resultResponse = await fetch(`/result/${taskId}`)
  if (!resultResponse.ok) {
    throw new Error(`Result fetch failed (${resultResponse.status})`)
  }
  const arrayBuffer = await resultResponse.arrayBuffer()
  return { taskId, arrayBuffer }
}

async function onRunNodeCoverage(nodeId: string, skipPreview = false): Promise<void> {
  const node = nodesStore.nodeById(nodeId)
  if (!node) {
    console.warn(`[NodeCoverage] Node not found: ${nodeId}`)
    return
  }

  try {
    // Cleanup previous coverage
    if (node.siteId) {
      const oldIndex = sitesStore.localSites.findIndex(s => s.taskId === node.siteId)
      if (oldIndex >= 0) {
        sitesStore.removeSite(oldIndex)
      }
      nodesStore.updateNode(nodeId, { siteId: undefined })
    }

    const fullRadiusM = sitesStore.splatParams.simulation.simulation_extent * 1000
    const usePreview = !skipPreview && fullRadiusM > 15000

    const { splatParams, payload: fullPayload } = buildPayload(node, fullRadiusM, sitesStore.splatParams.simulation.high_resolution)

    let previewTaskId: string | undefined

    if (usePreview) {
      // Launch preview (small radius, low resolution) in parallel with full
      const previewRadiusM = Math.min(fullRadiusM, 15000)
      const { payload: previewPayload } = buildPayload(node, previewRadiusM, false)

      console.log(`[NodeCoverage] Starting preview + full for "${node.name}"`)

      // Preview runs fire-and-forget alongside the full run
      const previewPromise = runSinglePrediction(previewPayload).then(async ({ taskId, arrayBuffer }) => {
        previewTaskId = taskId
        await sitesStore.addSiteFromBuffer(taskId, arrayBuffer, splatParams, true)
        console.log(`[NodeCoverage] Preview ready for "${node.name}"`)
      }).catch(err => {
        console.warn(`[NodeCoverage] Preview failed (non-blocking):`, err)
      })

      // Full run
      const fullResult = await runSinglePrediction(fullPayload)

      // Wait for preview to fully settle (parseGeoraster + localSites.push) before removing.
      // Without this await, findIndex returns -1 if the preview's addSiteFromBuffer is still
      // processing when the full result arrives, leaving an orphaned preview layer on the map.
      await previewPromise

      // Remove preview layer before adding full
      if (previewTaskId) {
        const previewIndex = sitesStore.localSites.findIndex(s => s.taskId === previewTaskId)
        if (previewIndex >= 0) {
          sitesStore.removeSite(previewIndex)
        }
      }

      await sitesStore.addSiteFromBuffer(fullResult.taskId, fullResult.arrayBuffer, splatParams)
      nodesStore.updateNode(nodeId, { siteId: fullResult.taskId })
      console.log(`[NodeCoverage] Full coverage completed for "${node.name}")`)
    } else {
      // No preview — direct full run
      console.log(`[NodeCoverage] POST /predict for "${node.name}" (no preview, radius=${fullRadiusM}m)`)
      const { taskId, arrayBuffer } = await runSinglePrediction(fullPayload)
      await sitesStore.addSiteFromBuffer(taskId, arrayBuffer, splatParams)
      nodesStore.updateNode(nodeId, { siteId: taskId })
      console.log(`[NodeCoverage] Completed for "${node.name}"`)
    }
  } catch (err) {
    console.error(`[NodeCoverage] Error for node ${nodeId}:`, err)
    throw err
  }
}

// --- Reset All Coverage ---

function onResetAllCoverage() {
  sitesStore.removeAllSites()
  nodesStore.clearAllSiteIds()
}

// --- Run All Coverage (Parallel Batch Submission) ---

async function onRunAllCoverage() {
  runAllErrors.value = []
  taskProgressMap.value.clear()
  const nodes = nodesStore.nodes
  if (nodes.length === 0) return

  runAllState.value = 'running'
  runAllProgress.value = { current: 0, total: nodes.length }

  try {
    const fullRadiusM = sitesStore.splatParams.simulation.simulation_extent * 1000
    const highRes = sitesStore.splatParams.simulation.high_resolution

    // 1. Build all payloads and cleanup previous coverage
    const nodePayloads: { nodeId: string; splatParams: ReturnType<typeof nodeToSplatParams>; payload: Record<string, unknown> }[] = []
    for (const node of nodes) {
      if (node.siteId) {
        const oldIndex = sitesStore.localSites.findIndex(s => s.taskId === node.siteId)
        if (oldIndex >= 0) sitesStore.removeSite(oldIndex)
        nodesStore.updateNode(node.id, { siteId: undefined })
      }
      const { splatParams, payload } = buildPayload(node, fullRadiusM, highRes)
      nodePayloads.push({ nodeId: node.id, splatParams, payload })
    }

    // 2. Submit all predictions in one batch
    const batchResponse = await fetch('/predict/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(nodePayloads.map(np => np.payload)),
    })
    if (!batchResponse.ok) {
      const detail = await batchResponse.text()
      throw new Error(`Batch submit failed (${batchResponse.status}): ${detail}`)
    }
    const { tasks } = await batchResponse.json() as { tasks: { task_id: string; cached: boolean }[] }

    // 3. Map task_ids to node info
    const taskToNode = new Map<string, { nodeId: string; nodeName: string; splatParams: ReturnType<typeof nodeToSplatParams> }>()
    for (let i = 0; i < tasks.length; i++) {
      const np = nodePayloads[i]
      const node = nodesStore.nodeById(np.nodeId)
      const name = node?.name ?? np.nodeId
      taskToNode.set(tasks[i].task_id, { nodeId: np.nodeId, nodeName: name, splatParams: np.splatParams })
      taskProgressMap.value.set(tasks[i].task_id, {
        nodeName: name,
        stage: '',
        progress: 0,
        status: tasks[i].cached ? 'processing' : 'queued',
      })
    }

    // 4. Open multi-task SSE stream and display results incrementally
    const allTaskIds = tasks.map(t => t.task_id)
    const pending = new Set(allTaskIds)

    await new Promise<void>((resolve, reject) => {
      const handleCompleted = async (taskId: string) => {
        try {
          const resultResponse = await fetch(`/result/${taskId}`)
          if (!resultResponse.ok) throw new Error(`Result fetch failed (${resultResponse.status})`)
          const arrayBuffer = await resultResponse.arrayBuffer()

          const entry = taskToNode.get(taskId)
          if (entry) {
            await sitesStore.addSiteFromBuffer(taskId, arrayBuffer, entry.splatParams)
            nodesStore.updateNode(entry.nodeId, { siteId: taskId })
          }
        } catch (err) {
          const entry = taskToNode.get(taskId)
          const name = entry?.nodeName ?? taskId
          runAllErrors.value.push(`"${name}": ${err instanceof Error ? err.message : String(err)}`)
        }
      }

      try {
        const es = new EventSource(`/events/multi?task_ids=${allTaskIds.join(',')}`)

        es.onmessage = async (event) => {
          const data = JSON.parse(event.data)
          const { task_id, status, stage, progress } = data

          // Update progress map
          const tp = taskProgressMap.value.get(task_id)
          if (tp) {
            if (progress !== undefined && progress > 0 && !tp.startedAt) {
              tp.startedAt = Date.now()
            }
            if (stage === 'running_splat' && tp.stage !== 'running_splat') {
              tp.splatStartedAt = Date.now()
            }
            if (stage !== undefined) tp.stage = stage
            if (progress !== undefined) tp.progress = progress
            if (status === 'completed') tp.status = 'completed'
            else if (status === 'failed') tp.status = 'failed'
            else if (status === 'processing') tp.status = 'processing'
          }

          if (status === 'completed' && pending.has(task_id)) {
            pending.delete(task_id)
            runAllProgress.value.current++
            await handleCompleted(task_id)
          } else if ((status === 'failed' || status === 'not_found') && pending.has(task_id)) {
            pending.delete(task_id)
            runAllProgress.value.current++
            const entry = taskToNode.get(task_id)
            const name = entry?.nodeName ?? task_id
            runAllErrors.value.push(`"${name}": simulation ${status}`)
            if (tp) tp.status = 'failed'
          }

          if (pending.size === 0) {
            es.close()
            resolve()
          }
        }

        es.onerror = () => {
          es.close()
          console.warn('[SSE Multi] Connection failed, falling back to individual polling')
          pollRemainingTasks(pending, taskToNode, handleCompleted).then(resolve, reject)
        }
      } catch {
        pollRemainingTasks(pending, taskToNode, handleCompleted).then(resolve, reject)
      }
    })
  } finally {
    runAllState.value = 'idle'
    settingsStale.value = false
    // Clear progress map after a brief delay so the user sees final state
    setTimeout(() => taskProgressMap.value.clear(), 2000)
  }
}

/** Fallback: poll remaining tasks individually when SSE fails. */
async function pollRemainingTasks(
  pending: Set<string>,
  taskToNode: Map<string, { nodeId: string; nodeName: string; splatParams: ReturnType<typeof nodeToSplatParams> }>,
  handleCompleted: (taskId: string) => Promise<void>,
) {
  const promises = [...pending].map(async (taskId) => {
    try {
      await pollForCompletion(taskId)
      pending.delete(taskId)
      runAllProgress.value.current++
      await handleCompleted(taskId)
      const tp = taskProgressMap.value.get(taskId)
      if (tp) tp.status = 'completed'
    } catch (err) {
      pending.delete(taskId)
      runAllProgress.value.current++
      const entry = taskToNode.get(taskId)
      const name = entry?.nodeName ?? taskId
      runAllErrors.value.push(`"${name}": ${err instanceof Error ? err.message : String(err)}`)
      const tp = taskProgressMap.value.get(taskId)
      if (tp) tp.status = 'failed'
    }
  })
  await Promise.allSettled(promises)
}
</script>

<style>
.leaflet-div-icon {
  background: transparent;
  border: none !important;
}
</style>
