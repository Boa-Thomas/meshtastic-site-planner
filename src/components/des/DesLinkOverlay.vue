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
const linkLayers: L.Layer[] = []

function drawLinks() {
  clearLinks()
  if (!showLinks.value || !mapStore.map) return

  // Group links by unordered node pair
  const pairMap = new Map<string, { ab?: typeof desStore.links[0]; ba?: typeof desStore.links[0] }>()

  for (const link of desStore.links) {
    if (!link.canHear) continue

    const [a, b] = [link.fromNodeId, link.toNodeId].sort()
    const key = `${a}::${b}`
    const entry = pairMap.get(key) ?? {}

    if (link.fromNodeId === a) {
      entry.ab = link
    } else {
      entry.ba = link
    }
    pairMap.set(key, entry)
  }

  // Also check non-hearing links for the reverse direction
  for (const link of desStore.links) {
    if (link.canHear) continue
    const [a, b] = [link.fromNodeId, link.toNodeId].sort()
    const key = `${a}::${b}`
    if (!pairMap.has(key)) continue // neither direction can hear — skip
    // pair already exists, the missing direction is simply absent
  }

  for (const [, pair] of pairMap) {
    const linkRef = pair.ab ?? pair.ba!
    const fromId = pair.ab ? linkRef.fromNodeId : linkRef.fromNodeId
    const toId = pair.ab ? linkRef.toNodeId : linkRef.toNodeId

    const fromNode = nodesStore.nodeById(pair.ab?.fromNodeId ?? pair.ba!.fromNodeId)
    const toNode = nodesStore.nodeById(pair.ab?.toNodeId ?? pair.ba!.toNodeId)
    if (!fromNode || !toNode) continue

    const isBidirectional = !!(pair.ab && pair.ba)
    const bestRssi = Math.max(pair.ab?.rssiDbm ?? -Infinity, pair.ba?.rssiDbm ?? -Infinity)

    // Color by best RSSI: green (> -90), yellow (-90 to -110), red (< -110)
    let color = '#28a745'
    if (bestRssi < -110) color = '#dc3545'
    else if (bestRssi < -90) color = '#ffc107'

    const coords: L.LatLngExpression[] = [[fromNode.lat, fromNode.lon], [toNode.lat, toNode.lon]]

    if (isBidirectional) {
      // Solid line for bidirectional
      const line = markRaw(L.polyline(coords, {
        color,
        weight: 2,
        opacity: 0.7,
      }).addTo(mapStore.map as L.Map))

      const abRssi = pair.ab!.rssiDbm.toFixed(0)
      const baRssi = pair.ba!.rssiDbm.toFixed(0)
      line.bindTooltip(
        `A→B: ${abRssi} dBm / B→A: ${baRssi} dBm (${linkRef.distanceKm.toFixed(1)} km)`,
        { sticky: true },
      )
      linkLayers.push(line)
    } else {
      // Dashed line for one-way
      const oneWay = pair.ab ?? pair.ba!
      const line = markRaw(L.polyline(coords, {
        color,
        weight: 1.5,
        opacity: 0.6,
        dashArray: '6 4',
      }).addTo(mapStore.map as L.Map))

      line.bindTooltip(
        `${oneWay.rssiDbm.toFixed(0)} dBm / ${oneWay.distanceKm.toFixed(1)} km (one-way)`,
        { sticky: true },
      )
      linkLayers.push(line)

      // Direction indicator: small circle at midpoint
      const midLat = (fromNode.lat + toNode.lat) / 2
      const midLon = (fromNode.lon + toNode.lon) / 2
      const indicator = markRaw(L.circleMarker([midLat, midLon], {
        radius: 4,
        color,
        fillColor: color,
        fillOpacity: 0.8,
        weight: 1,
      }).addTo(mapStore.map as L.Map))
      indicator.bindTooltip(
        `${oneWay.fromNodeId} → ${oneWay.toNodeId}`,
        { sticky: true },
      )
      linkLayers.push(indicator)
    }
  }
}

function clearLinks() {
  for (const layer of linkLayers) {
    layer.remove()
  }
  linkLayers.length = 0
}

watch(showLinks, drawLinks)
watch(() => desStore.links.length, () => { if (showLinks.value) drawLinks() })

onUnmounted(clearLinks)
</script>
