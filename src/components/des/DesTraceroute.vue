<template>
  <div>
    <div class="form-check form-switch mb-2">
      <input class="form-check-input" type="checkbox" id="showTraceroute" v-model="showTrace">
      <label class="form-check-label" for="showTraceroute">Show Traceroute</label>
    </div>
    <div v-if="showTrace && routePath.length > 0" class="small text-light mt-1">
      Path: {{ routeLabel }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, onUnmounted } from 'vue'
import { markRaw } from 'vue'
import L from 'leaflet'
import { useDesStore } from '../../stores/desStore'
import { useMapStore } from '../../stores/mapStore'
import { useNodesStore } from '../../stores/nodesStore'

const desStore = useDesStore()
const mapStore = useMapStore()
const nodesStore = useNodesStore()

const showTrace = ref(false)
const traceLayers: L.Layer[] = []

const routePath = computed<string[]>(() => {
  const event = desStore.currentEvent
  if (!event?.packet?.routePath) return []
  return event.packet.routePath
})

const routeLabel = computed(() => {
  return routePath.value
    .map(id => nodesStore.nodeById(id)?.name ?? id)
    .join(' → ')
})

function drawTrace() {
  clearTrace()
  if (!showTrace.value || !mapStore.map || routePath.value.length === 0) return

  const path = routePath.value
  const coords: L.LatLngExpression[] = []

  for (const nodeId of path) {
    const node = nodesStore.nodeById(nodeId)
    if (!node) return
    coords.push([node.lat, node.lon])
  }

  if (coords.length < 2) return

  // Draw polyline for the route
  const line = markRaw(L.polyline(coords, {
    color: '#9b59b6',
    weight: 3,
    opacity: 0.8,
    dashArray: '8 4',
  }).addTo(mapStore.map as L.Map))
  traceLayers.push(line)

  // Draw hop markers
  for (let i = 0; i < path.length; i++) {
    const node = nodesStore.nodeById(path[i])
    if (!node) continue

    let color: string
    if (i === 0) color = '#3498db'                 // origin: blue
    else if (i === path.length - 1) color = '#2ecc71' // last hop: green
    else color = '#9b59b6'                           // relay: purple

    const marker = markRaw(L.circleMarker([node.lat, node.lon], {
      radius: 6,
      color,
      fillColor: color,
      fillOpacity: 0.9,
      weight: 2,
    }).addTo(mapStore.map as L.Map))

    marker.bindTooltip(`Hop ${i}: ${node.name}`, { sticky: true })
    traceLayers.push(marker)
  }
}

function clearTrace() {
  for (const layer of traceLayers) {
    layer.remove()
  }
  traceLayers.length = 0
}

watch(showTrace, drawTrace)
watch(routePath, () => { if (showTrace.value) drawTrace() })

onUnmounted(clearTrace)
</script>
