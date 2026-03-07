import { ref } from 'vue'
import { useSitesStore } from '../stores/sitesStore'
import { useNodesStore } from '../stores/nodesStore'
import { useDesStore } from '../stores/desStore'
import { useMapStore } from '../stores/mapStore'
import type { MeshNode } from '../types/index'
import type { SimEvent, SimulationConfig } from '../des/types'
import type { SharedSettings } from '../utils/nodeToSplatParams'
import type { SplatParams } from '../types/index'
import L from 'leaflet'
import {
  exportProjectFromServer,
  importProjectToServer,
} from '../services/api'

// ---------------------------------------------------------------------------
// Project file format
// ---------------------------------------------------------------------------

interface ProjectSite {
  taskId: string
  params: SplatParams
  nodeId?: string
  rasterBase64: string
}

interface ProjectFile {
  version: number
  exportedAt: string
  appName: 'meshtastic-site-planner'
  nodes: Omit<MeshNode, 'siteId'>[]
  splatParams: SharedSettings
  desConfig: SimulationConfig
  map: { center: [number, number]; zoom: number; baseLayer: string }
  sites: ProjectSite[]
  desEvents?: SimEvent[]
}

// ---------------------------------------------------------------------------
// Gzip compression helpers (native CompressionStream API)
// ---------------------------------------------------------------------------

async function compressBlob(blob: Blob): Promise<Blob> {
  const stream = blob.stream().pipeThrough(new CompressionStream('gzip'))
  return new Response(stream).blob()
}

async function decompressBlob(blob: Blob): Promise<Blob> {
  const stream = blob.stream().pipeThrough(new DecompressionStream('gzip'))
  return new Response(stream).blob()
}

// ---------------------------------------------------------------------------
// Base64 helpers
// ---------------------------------------------------------------------------

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  const CHUNK = 0x8000 // 32KB — safe for call stack
  const parts: string[] = []
  for (let i = 0; i < bytes.length; i += CHUNK) {
    parts.push(String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK) as unknown as number[]))
  }
  return btoa(parts.join(''))
}

function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes.buffer.slice(0)
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useProjectIO() {
  const importing = ref(false)
  const importError = ref('')
  const exporting = ref(false)
  const exportError = ref('')

  async function exportProject() {
    exporting.value = true
    exportError.value = ''

    try {
      // Yield to let the browser paint the spinner
      await new Promise(r => setTimeout(r, 0))

      // Try server-side export first
      try {
        const blob = await exportProjectFromServer()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        const date = new Date().toISOString().slice(0, 10)
        a.download = `meshtastic-project-${date}.json.gz`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
        return
      } catch (serverErr) {
        console.warn('[ProjectIO] Server export failed, falling back to client-side:', serverErr)
      }

      // Fallback: client-side export
      const sitesStore = useSitesStore()
      const nodesStore = useNodesStore()
      const desStore = useDesStore()
      const mapStore = useMapStore()

      // Collect nodes without siteId (will be reconstructed on import)
      const nodes = nodesStore.nodes.map(n => {
        const { siteId, ...rest } = n
        return rest
      })

      // Collect sites with raster data encoded as base64
      const sites: ProjectSite[] = sitesStore.localSites
        .filter(s => s.rasterData)
        .map(s => {
          // Find the node that references this site
          const linkedNode = nodesStore.nodes.find(n => n.siteId === s.taskId)
          return {
            taskId: s.taskId,
            params: JSON.parse(JSON.stringify(s.params)),
            nodeId: linkedNode?.id,
            rasterBase64: arrayBufferToBase64(s.rasterData!),
          }
        })

      // Map viewport
      const map = mapStore.map
      const center: [number, number] = map
        ? [map.getCenter().lat, map.getCenter().lng]
        : [-26.82, -49.27]
      const zoom = map ? map.getZoom() : 10

      // DES events (only if simulation has run)
      const desEvents = desStore.processedEvents.length > 0
        ? JSON.parse(JSON.stringify(desStore.processedEvents))
        : undefined

      const project: ProjectFile = {
        version: 1,
        exportedAt: new Date().toISOString(),
        appName: 'meshtastic-site-planner',
        nodes,
        splatParams: JSON.parse(JSON.stringify(sitesStore.splatParams)),
        desConfig: JSON.parse(JSON.stringify(desStore.config)),
        map: { center, zoom, baseLayer: mapStore.currentBaseLayer },
        sites,
        desEvents,
      }

      // Compress and trigger download
      const json = JSON.stringify(project)
      const jsonBlob = new Blob([json], { type: 'application/json' })
      const compressed = await compressBlob(jsonBlob)
      const url = URL.createObjectURL(compressed)
      const a = document.createElement('a')
      a.href = url
      const date = new Date().toISOString().slice(0, 10)
      a.download = `meshtastic-project-${date}.json.gz`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      exportError.value = err instanceof Error ? err.message : 'Failed to export project.'
      console.error('[ProjectIO] Export error:', err)
    } finally {
      exporting.value = false
    }
  }

  async function importProject(file: File) {
    const sitesStore = useSitesStore()
    const nodesStore = useNodesStore()
    const desStore = useDesStore()
    const mapStore = useMapStore()

    importing.value = true
    importError.value = ''

    try {
      // Try server-side import first
      try {
        await importProjectToServer(file)
        // Refresh local state from server
        nodesStore.initialized = false
        await nodesStore.initialize()
        await sitesStore.restoreFromServer()

        // Parse the file locally for map viewport and DES config
        let text: string
        if (file.name.endsWith('.gz')) {
          const decompressed = await decompressBlob(file)
          text = await decompressed.text()
        } else {
          text = await file.text()
        }
        const data: ProjectFile = JSON.parse(text)

        // Restore shared splatParams
        if (data.splatParams) {
          Object.assign(sitesStore.splatParams, data.splatParams)
        }

        // Restore DES config
        if (data.desConfig) {
          desStore.updateConfig(data.desConfig)
        }

        // Restore map viewport
        if (data.map && mapStore.map) {
          mapStore.map.setView(
            L.latLng(data.map.center[0], data.map.center[1]),
            data.map.zoom,
            { animate: false },
          )
        }

        // Restore DES events (optional)
        if (Array.isArray(data.desEvents) && data.desEvents.length > 0) {
          desStore.processedEvents = data.desEvents
          desStore.currentEventIndex = data.desEvents.length - 1
        }

        return
      } catch (serverErr) {
        console.warn('[ProjectIO] Server import failed, falling back to client-side:', serverErr)
      }

      // Fallback: client-side import
      let text: string
      if (file.name.endsWith('.gz')) {
        const decompressed = await decompressBlob(file)
        text = await decompressed.text()
      } else {
        text = await file.text()
      }
      const data: ProjectFile = JSON.parse(text)

      // Validate
      if (data.version !== 1 || data.appName !== 'meshtastic-site-planner') {
        throw new Error('Invalid project file format or unsupported version.')
      }

      // 1. Clear current state
      await sitesStore.removeAllSites()
      await nodesStore.clearAllNodes()
      desStore.reset()

      // 2. Restore nodes
      if (Array.isArray(data.nodes)) {
        for (const nodeData of data.nodes) {
          await nodesStore.addNode(nodeData as MeshNode)
        }
      }

      // 3. Restore shared splatParams
      if (data.splatParams) {
        Object.assign(sitesStore.splatParams, data.splatParams)
      }

      // 4. Restore DES config
      if (data.desConfig) {
        desStore.updateConfig(data.desConfig)
      }

      // 5. Restore sites (SPLAT! rasters)
      if (Array.isArray(data.sites)) {
        for (const site of data.sites) {
          try {
            const arrayBuffer = base64ToArrayBuffer(site.rasterBase64)
            await sitesStore.addSiteFromBuffer(site.taskId, arrayBuffer, site.params)
            // Re-link node → site
            if (site.nodeId) {
              await nodesStore.updateNode(site.nodeId, { siteId: site.taskId })
            }
          } catch (err) {
            console.warn(`[ProjectIO] Failed to restore site ${site.taskId}:`, err)
          }
        }
      }

      // 6. Restore map viewport
      if (data.map && mapStore.map) {
        mapStore.map.setView(
          L.latLng(data.map.center[0], data.map.center[1]),
          data.map.zoom,
          { animate: false },
        )
      }

      // 7. Restore DES events (optional)
      if (Array.isArray(data.desEvents) && data.desEvents.length > 0) {
        desStore.processedEvents = data.desEvents
        desStore.currentEventIndex = data.desEvents.length - 1
      }
    } catch (err) {
      importError.value = err instanceof Error ? err.message : 'Failed to import project.'
      console.error('[ProjectIO] Import error:', err)
    } finally {
      importing.value = false
    }
  }

  return { exportProject, importProject, importing, importError, exporting, exportError }
}
