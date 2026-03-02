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
              <!-- 1. Site / Transmitter -->
              <li class="nav-item">
                <a class="nav-link dropdown-toggle" href="#" role="button"
                   @click.prevent="togglePanel('transmitter')"
                   :aria-expanded="openPanels.has('transmitter')">Site / Transmitter</a>
                <ul :class="['dropdown-menu', 'dropdown-menu-dark', 'p-3', { show: openPanels.has('transmitter') }]"
                    style="position:static">
                  <li>
                    <Transmitter />
                  </li>
                </ul>
              </li>

              <!-- 2. Receiver -->
              <li class="nav-item">
                <a class="nav-link dropdown-toggle" href="#" role="button"
                   @click.prevent="togglePanel('receiver')"
                   :aria-expanded="openPanels.has('receiver')">Receiver</a>
                <ul :class="['dropdown-menu', 'dropdown-menu-dark', 'p-3', { show: openPanels.has('receiver') }]"
                    style="position:static">
                  <li>
                    <Receiver />
                  </li>
                </ul>
              </li>

              <!-- 3. Environment -->
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

              <!-- 4. Simulation Options -->
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

              <!-- 5. Display -->
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

              <!-- 6. Mesh Nodes -->
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

              <!-- 7. Network Simulation (DES) -->
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

            <!-- Run Simulation + Export buttons -->
            <div class="mt-3 d-flex gap-2">
              <button :disabled="sitesStore.simulationState === 'running'" @click="sitesStore.runSimulation" type="button" class="btn btn-success btn-sm" id="runSimulation">
                <span :class="{ 'd-none': sitesStore.simulationState !== 'running' }" class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                <span class="button-text">{{ buttonText() }}</span>
              </button>
              <button :disabled="exportLoading" @click="exportMap" type="button" class="btn btn-secondary btn-sm">
                <span :class="{ 'd-none': !exportLoading }" class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                Export PDF
              </button>
            </div>

            <div v-if="exportError" class="alert alert-warning alert-dismissible mt-2 py-1 px-2 small" role="alert">
              {{ exportError }}
              <button type="button" class="btn-close btn-sm" @click="exportError = ''" aria-label="Close"></button>
            </div>

            <!-- Legacy site list (SPLAT! results from the main transmitter panel) -->
            <ul class="list-group mt-3">
              <li class="list-group-item d-flex justify-content-between align-items-center" v-for="(site, index) in sitesStore.localSites" :key="site.taskId">
                <span>{{ site.params.transmitter.name }}</span>
                <button type="button" @click="sitesStore.removeSite(index)" class="btn-close" aria-label="Close"></button>
              </li>
            </ul>
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
import { markRaw, ref, watch } from 'vue'
import { reactive } from 'vue'

import Transmitter from "./components/Transmitter.vue"
import Receiver from "./components/Receiver.vue"
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

import { useSitesStore } from './stores/sitesStore'
import { useMapStore } from './stores/mapStore'
import { useNodesStore } from './stores/nodesStore'
import { useExport } from './composables/useExport'
import { useDesVisualization } from './composables/useDesVisualization'
import { meshNodeMarker } from './layers'
import { nodeToSplatParams } from './utils/nodeToSplatParams'
import { cloneObject } from './utils'
import parseGeoraster from 'georaster'

const sitesStore = useSitesStore()
const mapStore = useMapStore()
const nodesStore = useNodesStore()
const { exportLoading, exportError, exportMap } = useExport()
useDesVisualization()

// Track Leaflet markers for each mesh node by node ID
const nodeMarkers = new Map<string, L.Marker>()

// Run All Coverage state
const runAllState = ref<'idle' | 'running'>('idle')
const runAllProgress = ref({ current: 0, total: 0 })
const runAllErrors = ref<string[]>([])

const buttonText = () => {
  if ('running' === sitesStore.simulationState) {
    return 'Running'
  } else if ('failed' === sitesStore.simulationState) {
    return 'Failed'
  } else {
    return 'Run Simulation'
  }
}

// Which panels are currently expanded (transmitter + display open by default)
const openPanels = reactive(new Set(['transmitter', 'display']))
const togglePanel = (name: string) => {
  openPanels.has(name) ? openPanels.delete(name) : openPanels.add(name)
}

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

// --- Restore markers for persisted nodes after map init ---

watch(
  () => mapStore.map,
  (map) => {
    if (!map) return
    for (const node of nodesStore.nodes) {
      if (nodeMarkers.has(node.id)) continue
      const marker = markRaw(
        L.marker([node.lat, node.lon], { icon: meshNodeMarker })
          .addTo(map as L.Map)
          .bindPopup(node.name)
      )
      marker.on('click', () => {
        nodesStore.selectedNodeId = node.id
      })
      nodeMarkers.set(node.id, marker)
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

  // Place a marker on the map for this node
  if (mapStore.map) {
    const marker = markRaw(
      L.marker([lat, lon], { icon: meshNodeMarker })
        .addTo(mapStore.map as L.Map)
        .bindPopup(node.name)
    )
    marker.on('click', () => {
      nodesStore.selectedNodeId = node.id
    })
    nodeMarkers.set(node.id, marker)
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

async function onRunNodeCoverage(nodeId: string): Promise<void> {
  const node = nodesStore.nodeById(nodeId)
  if (!node) {
    console.warn(`[NodeCoverage] Node not found: ${nodeId}`)
    return
  }

  try {
    // Cleanup inside try so exceptions don't kill the caller
    if (node.siteId) {
      const oldIndex = sitesStore.localSites.findIndex(s => s.taskId === node.siteId)
      if (oldIndex >= 0) {
        sitesStore.removeSite(oldIndex)
      }
      nodesStore.updateNode(nodeId, { siteId: undefined })
    }

    const splatParams = nodeToSplatParams(node, {
      environment: sitesStore.splatParams.environment,
      simulation: sitesStore.splatParams.simulation,
      display: sitesStore.splatParams.display,
    })

    const payload = {
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
      radius: splatParams.simulation.simulation_extent * 1000,
      situation_fraction: splatParams.simulation.situation_fraction,
      time_fraction: splatParams.simulation.time_fraction,
      high_resolution: splatParams.simulation.high_resolution,
      colormap: splatParams.display.color_scale,
      min_dbm: splatParams.display.min_dbm,
      max_dbm: splatParams.display.max_dbm,
    }

    console.log(`[NodeCoverage] POST /predict for "${node.name}"`)
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
    console.log(`[NodeCoverage] Task ${taskId} started for "${node.name}"`)

    // Await-based polling loop
    while (true) {
      await sleep(1000)

      const statusResponse = await fetch(`/status/${taskId}`)
      if (!statusResponse.ok) {
        throw new Error(`Status check failed (${statusResponse.status})`)
      }
      const { status } = await statusResponse.json()

      if (status === 'completed') {
        const resultResponse = await fetch(`/result/${taskId}`)
        if (!resultResponse.ok) {
          throw new Error(`Result fetch failed (${resultResponse.status})`)
        }

        const arrayBuffer = await resultResponse.arrayBuffer()
        const geoRaster = await parseGeoraster(arrayBuffer)

        sitesStore.localSites.push({
          params: cloneObject(splatParams),
          taskId,
          raster: geoRaster,
        })
        sitesStore.redrawSites()
        nodesStore.updateNode(nodeId, { siteId: taskId })
        console.log(`[NodeCoverage] Completed for "${node.name}"`)
        return
      } else if (status === 'failed') {
        throw new Error('SPLAT! simulation failed on backend')
      }
    }
  } catch (err) {
    console.error(`[NodeCoverage] Error for node ${nodeId}:`, err)
    throw err // Re-throw so onRunAllCoverage can catch it
  }
}

// --- Run All Coverage ---

async function onRunAllCoverage() {
  runAllErrors.value = []
  // Snapshot IDs as plain strings — decoupled from Pinia reactivity
  const nodeIds = nodesStore.nodes.map(n => n.id)
  if (nodeIds.length === 0) return

  runAllState.value = 'running'
  runAllProgress.value = { current: 0, total: nodeIds.length }

  try {
    for (const nodeId of nodeIds) {
      runAllProgress.value.current++
      try {
        await onRunNodeCoverage(nodeId)
      } catch (err) {
        const name = nodesStore.nodeById(nodeId)?.name ?? nodeId
        runAllErrors.value.push(`"${name}": ${err instanceof Error ? err.message : String(err)}`)
        // Continue to next node
      }
    }
  } finally {
    runAllState.value = 'idle' // ALWAYS reset, even if everything fails
  }
}
</script>

<style>
.leaflet-div-icon {
  background: transparent;
  border: none !important;
}
</style>
