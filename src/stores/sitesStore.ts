import { defineStore } from 'pinia'
import { markRaw } from 'vue'
import GeoRasterLayer from 'georaster-layer-for-leaflet'
import parseGeoraster from 'georaster'
import L from 'leaflet'
import { type Site, type SplatParams } from '../types'
import { cloneObject } from '../utils'
import { useMapStore } from './mapStore'
import { colormapLookup } from '../utils/colormaps'
import type { SharedSettings } from '../utils/nodeToSplatParams'

// ---------------------------------------------------------------------------
// IndexedDB helpers (module-level, no Vue dependency)
// ---------------------------------------------------------------------------

const DB_NAME = 'meshtastic-planner'
const STORE_NAME = 'splat-coverage'
const DB_VERSION = 1

function openCoverageDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'taskId' })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function saveSiteToDb(taskId: string, params: SplatParams, rasterBuffer: ArrayBuffer): Promise<void> {
  const db = await openCoverageDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    tx.objectStore(STORE_NAME).put({ taskId, params, rasterBuffer })
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

async function deleteSiteFromDb(taskId: string): Promise<void> {
  const db = await openCoverageDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    tx.objectStore(STORE_NAME).delete(taskId)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

async function loadAllSitesFromDb(): Promise<Array<{ taskId: string; params: SplatParams; rasterBuffer: ArrayBuffer }>> {
  const db = await openCoverageDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly')
    const request = tx.objectStore(STORE_NAME).getAll()
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useSitesStore = defineStore('sites', {
  state: () => ({
    localSites: [] as Site[],
    splatParams: <SharedSettings>{
      environment: {
        radio_climate: 'continental_subtropical',
        polarization: 'vertical',
        clutter_height: 10.0,
        ground_dielectric: 15.0,
        ground_conductivity: 0.005,
        atmosphere_bending: 301.0,
      },
      simulation: {
        situation_fraction: 95.0,
        time_fraction: 95.0,
        simulation_extent: 90.0,
        high_resolution: true,
      },
      display: {
        color_scale: 'plasma',
        min_dbm: -140.0,
        max_dbm: -60.0,
        overlay_transparency: 50,
      },
    },
  }),
  actions: {
    // -----------------------------------------------------------------------
    // Centralized site creation from an ArrayBuffer
    // -----------------------------------------------------------------------

    async addSiteFromBuffer(taskId: string, arrayBuffer: ArrayBuffer, params: SplatParams, isPreview = false) {
      // Keep an independent copy — parseGeoraster may detach the original buffer
      const rasterCopy = arrayBuffer.slice(0)
      const geoRaster = await parseGeoraster(rasterCopy)
      this.localSites.push({
        params: cloneObject(params),
        taskId,
        raster: markRaw(geoRaster),
        visible: true,
        rasterData: arrayBuffer,
        isPreview,
      })
      this.redrawSites()
      if (!isPreview) {
        saveSiteToDb(taskId, cloneObject(params), arrayBuffer).catch((err) =>
          console.warn('[IndexedDB] Failed to save site:', err),
        )
      }
    },

    // -----------------------------------------------------------------------
    // Remove
    // -----------------------------------------------------------------------

    removeAllSites() {
      const mapStore = useMapStore()
      for (const site of this.localSites) {
        if (site.rasterLayer && mapStore.map) {
          mapStore.map.removeLayer(site.rasterLayer)
        }
        deleteSiteFromDb(site.taskId).catch(err =>
          console.warn('[IndexedDB] Failed to delete site:', err)
        )
      }
      this.localSites = []
    },

    removeSite(index: number) {
      const mapStore = useMapStore()
      if (!mapStore.map) return
      const site = this.localSites[index]
      if (site.rasterLayer) {
        mapStore.map.removeLayer(site.rasterLayer)
      }
      deleteSiteFromDb(site.taskId).catch((err) =>
        console.warn('[IndexedDB] Failed to delete site:', err),
      )
      this.localSites.splice(index, 1)
    },

    // -----------------------------------------------------------------------
    // Visibility toggles
    // -----------------------------------------------------------------------

    toggleSiteVisibility(index: number) {
      const mapStore = useMapStore()
      if (!mapStore.map) return
      const site = this.localSites[index]
      if (!site.rasterLayer) return
      if (site.visible) {
        mapStore.map.removeLayer(site.rasterLayer)
        site.visible = false
      } else {
        site.rasterLayer.addTo(mapStore.map as L.Map)
        site.rasterLayer.bringToFront()
        site.visible = true
      }
    },

    hideAllOverlays() {
      const mapStore = useMapStore()
      if (!mapStore.map) return
      this.localSites.forEach((site: Site) => {
        if (site.visible && site.rasterLayer) {
          mapStore.map!.removeLayer(site.rasterLayer)
          site.visible = false
        }
      })
    },

    showAllOverlays() {
      const mapStore = useMapStore()
      if (!mapStore.map) return
      this.localSites.forEach((site: Site) => {
        if (!site.visible && site.rasterLayer) {
          site.rasterLayer.addTo(mapStore.map as L.Map)
          site.rasterLayer.bringToFront()
          site.visible = true
        }
      })
    },

    // -----------------------------------------------------------------------
    // Redraw (creates GeoRasterLayer for new sites)
    // -----------------------------------------------------------------------

    redrawSites(forceRecreate = false) {
      const mapStore = useMapStore()
      if (!mapStore.map) return
      const colormap = this.splatParams.display.color_scale
      const opacity = this.splatParams.display.overlay_transparency / 100

      // 4C.2 — Pre-compute 256-entry color cache once per colormap invocation
      const colorCache: (string | null)[] = new Array(256)
      for (let i = 0; i < 255; i++) {
        const [r, g, b] = colormapLookup(colormap, i / 254)
        colorCache[i] = `rgba(${r},${g},${b},1)`
      }
      colorCache[255] = null // noData → transparent

      this.localSites.forEach((site: Site) => {
        const siteOpacity = site.isPreview ? opacity * 0.6 : opacity
        if (!site.rasterLayer || forceRecreate) {
          // Remove old layer if force-recreating
          if (site.rasterLayer && mapStore.map) {
            mapStore.map.removeLayer(site.rasterLayer)
          }
          // Client-side colormap: pixel values are grayscale (0-254 = signal, 255 = noData)
          site.rasterLayer = markRaw(new GeoRasterLayer({
            georaster: site.raster,
            opacity: siteOpacity,
            // 4C.1 — Adaptive resolution by zoom level (object form is valid per GeoRasterLayer docs)
            resolution: { 0: 16, 5: 32, 8: 64, 12: 128, 15: 256 } as unknown as number,
            // 4C.4 — Prevent rendering at very low zoom levels
            minZoom: 3,
            pixelValuesToColorFn: (values: number[]) => colorCache[values[0]],
          }))
          if (site.visible !== false) {
            site.rasterLayer.addTo(mapStore.map as L.Map)
            site.rasterLayer.bringToFront()
          }
        } else if (site.visible) {
          site.rasterLayer.bringToFront()
        }
      })
    },

    // -----------------------------------------------------------------------
    // 4C.3 — Update display settings in-place via updateColors() + setOpacity()
    // -----------------------------------------------------------------------

    updateDisplaySettings() {
      const mapStore = useMapStore()
      if (!mapStore.map) return
      const colormap = this.splatParams.display.color_scale
      const opacity = this.splatParams.display.overlay_transparency / 100

      // Pre-compute color cache (same approach as redrawSites)
      const colorCache: (string | null)[] = new Array(256)
      for (let i = 0; i < 255; i++) {
        const [r, g, b] = colormapLookup(colormap, i / 254)
        colorCache[i] = `rgba(${r},${g},${b},1)`
      }
      colorCache[255] = null

      const newColorFn = (values: number[]) => colorCache[values[0]]

      for (const site of this.localSites) {
        if (!site.rasterLayer) continue
        // updateColors re-renders only visible tiles without re-parsing the raster
        if (typeof (site.rasterLayer as any).updateColors === 'function') {
          ;(site.rasterLayer as any).updateColors(newColorFn)
        }
        site.rasterLayer.setOpacity(opacity)
      }
    },

    // -----------------------------------------------------------------------
    // Restore from IndexedDB (called on map init)
    // -----------------------------------------------------------------------

    async restoreFromIndexedDB() {
      try {
        const records = await loadAllSitesFromDb()
        const existingTaskIds = new Set(this.localSites.map((s) => s.taskId))

        for (const record of records) {
          if (existingTaskIds.has(record.taskId)) continue
          const copy = record.rasterBuffer.slice(0)
          const geoRaster = await parseGeoraster(copy)
          this.localSites.push({
            params: record.params,
            taskId: record.taskId,
            raster: markRaw(geoRaster),
            visible: true,
            rasterData: record.rasterBuffer,
          })
        }

        this.redrawSites()
      } catch (err) {
        console.warn('[IndexedDB] Failed to restore sites:', err)
        // Fallback: just redraw whatever is in memory
        this.redrawSites()
      }
    },

  },
})
