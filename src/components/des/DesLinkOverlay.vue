<template>
  <div>
    <div class="form-check form-switch mb-2">
      <input class="form-check-input" type="checkbox" id="showLinks" v-model="showLinks">
      <label class="form-check-label" for="showLinks">Show Links</label>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { markRaw } from 'vue'
import L from 'leaflet'
import { useDesStore } from '../../stores/desStore'
import { useMapStore } from '../../stores/mapStore'
import { useNodesStore } from '../../stores/nodesStore'

const desStore = useDesStore()
const mapStore = useMapStore()
const nodesStore = useNodesStore()

const showLinks = ref(false)
const linkLines: L.Polyline[] = []

function drawLinks() {
  clearLinks()
  if (!showLinks.value || !mapStore.map) return

  for (const link of desStore.links) {
    if (!link.canHear) continue

    const fromNode = nodesStore.nodeById(link.fromNodeId)
    const toNode = nodesStore.nodeById(link.toNodeId)
    if (!fromNode || !toNode) continue

    // Color by RSSI: green (> -90), yellow (-90 to -110), red (< -110)
    let color = '#28a745'
    if (link.rssiDbm < -110) color = '#dc3545'
    else if (link.rssiDbm < -90) color = '#ffc107'

    const line = markRaw(L.polyline(
      [[fromNode.lat, fromNode.lon], [toNode.lat, toNode.lon]],
      { color, weight: 1.5, opacity: 0.6, dashArray: '4 4' }
    ).addTo(mapStore.map as L.Map))

    line.bindTooltip(`${link.rssiDbm.toFixed(0)} dBm / ${link.distanceKm.toFixed(1)} km`, { sticky: true })
    linkLines.push(line)
  }
}

function clearLinks() {
  for (const line of linkLines) {
    line.remove()
  }
  linkLines.length = 0
}

watch(showLinks, drawLinks)
watch(() => desStore.links.length, () => { if (showLinks.value) drawLinks() })

onUnmounted(clearLinks)
</script>
