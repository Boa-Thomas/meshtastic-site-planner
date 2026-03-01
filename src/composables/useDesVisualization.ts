import { watch, onUnmounted, markRaw } from 'vue'
import L from 'leaflet'
import { useDesStore } from '../stores/desStore'
import { useMapStore } from '../stores/mapStore'
import { useNodesStore } from '../stores/nodesStore'
import type { SimEvent } from '../des/types'

export function useDesVisualization() {
  const desStore = useDesStore()
  const mapStore = useMapStore()
  const nodesStore = useNodesStore()

  // Track temporary visual elements for cleanup
  const tempLayers: L.Layer[] = []

  function cleanupOldLayers() {
    // Remove layers when buffer exceeds 100 to prevent memory growth
    while (tempLayers.length > 100) {
      const layer = tempLayers.shift()
      layer?.remove()
    }
  }

  function getNodeCoords(nodeId: string): [number, number] | null {
    const node = nodesStore.nodeById(nodeId)
    if (!node) return null
    return [node.lat, node.lon]
  }

  function visualizeEvent(event: SimEvent) {
    if (!mapStore.map) return

    const map = mapStore.map as L.Map

    switch (event.type) {
      case 'message_send':
      case 'message_rebroadcast': {
        // Pulsing circle at sender
        const coords = getNodeCoords(event.sourceNodeId)
        if (!coords) break

        const circle = markRaw(L.circleMarker(coords, {
          radius: 15,
          color: event.type === 'message_send' ? '#0d6efd' : '#0dcaf0',
          fillColor: event.type === 'message_send' ? '#0d6efd' : '#0dcaf0',
          fillOpacity: 0.3,
          weight: 2,
          className: 'des-pulse',
        }).addTo(map))

        tempLayers.push(circle)

        // Auto-remove after animation
        setTimeout(() => circle.remove(), 1500)
        break
      }

      case 'message_receive':
      case 'ack_receive': {
        // Animated line from sender to receiver
        const fromCoords = getNodeCoords(event.sourceNodeId)
        const toCoords = event.targetNodeId ? getNodeCoords(event.targetNodeId) : null
        if (!fromCoords || !toCoords) break

        // Color by RSSI: green = good, yellow = marginal, red = weak
        let color = '#28a745'
        if (event.packet.rssiAtReceiver !== undefined) {
          if (event.packet.rssiAtReceiver < -110) color = '#dc3545'
          else if (event.packet.rssiAtReceiver < -90) color = '#ffc107'
        }

        const line = markRaw(L.polyline([fromCoords, toCoords], {
          color,
          weight: 2.5,
          opacity: 0.8,
          className: 'des-line-animate',
        }).addTo(map))

        tempLayers.push(line)
        setTimeout(() => line.remove(), 2000)
        break
      }

      case 'collision': {
        // Red pulsing marker at receiver
        const coords = event.targetNodeId ? getNodeCoords(event.targetNodeId) : null
        if (!coords) break

        const marker = markRaw(L.circleMarker(coords, {
          radius: 12,
          color: '#dc3545',
          fillColor: '#dc3545',
          fillOpacity: 0.5,
          weight: 3,
          className: 'des-collision',
        }).addTo(map))

        tempLayers.push(marker)
        setTimeout(() => marker.remove(), 2000)
        break
      }
    }

    cleanupOldLayers()
  }

  // Watch for new events and visualize them
  const stopWatch = watch(
    () => desStore.currentEventIndex,
    (newIdx) => {
      if (newIdx >= 0 && newIdx < desStore.processedEvents.length) {
        visualizeEvent(desStore.processedEvents[newIdx])
      }
    }
  )

  function cleanup() {
    stopWatch()
    for (const layer of tempLayers) {
      layer.remove()
    }
    tempLayers.length = 0
  }

  onUnmounted(cleanup)

  return { cleanup }
}
