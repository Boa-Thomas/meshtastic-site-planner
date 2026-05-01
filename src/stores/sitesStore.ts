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
import {
  getSites,
  getSiteRaster,
  deleteSiteApi,
  deleteAllSites as apiDeleteAllSites,
} from '../services/api'

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
      // Server-side persistence is handled by run_splat() in the backend.
      // No need to upload the raster — it's already saved on the server.
    },

    // -----------------------------------------------------------------------
    // Remove
    // -----------------------------------------------------------------------

    async removeAllSites() {
      const mapStore = useMapStore()
      for (const site of this.localSites) {
        if (site.rasterLayer && mapStore.map) {
          mapStore.map.removeLayer(site.rasterLayer)
        }
      }
      try {
        await apiDeleteAllSites()
      } catch (err) {
        console.warn('[SitesStore] Failed to delete all sites from server:', err)
      }
      this.localSites = []
    },

    async removeSite(index: number) {
      const mapStore = useMapStore()
      if (!mapStore.map) return
      const site = this.localSites[index]
      if (site.rasterLayer) {
        mapStore.map.removeLayer(site.rasterLayer)
      }
      try {
        await deleteSiteApi(site.taskId)
      } catch (err) {
        console.warn('[SitesStore] Failed to delete site from server:', err)
      }
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
            resolution: 256,
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
    // Restore from server (called on map init)
    // -----------------------------------------------------------------------

    async restoreFromServer() {
      try {
        const serverSites = await getSites()
        const existingTaskIds = new Set(this.localSites.map((s) => s.taskId))

        for (const meta of serverSites) {
          if (existingTaskIds.has(meta.taskId)) continue
          try {
            const rasterBuffer = await getSiteRaster(meta.taskId)
            const copy = rasterBuffer.slice(0)
            const geoRaster = await parseGeoraster(copy)
            const rawParams = typeof meta.params === 'string'
              ? JSON.parse(meta.params)
              : meta.params
            // Server persists params in the flat SPLAT request shape (lat,
            // lon, tx_height, ...). Re-wrap into the nested SplatParams the
            // UI expects so older persisted sites keep rendering.
            const params: SplatParams = rawParams && rawParams.transmitter
              ? rawParams as SplatParams
              : {
                  transmitter: {
                    name: `Site ${meta.taskId.slice(0, 8)}`,
                    tx_lat: rawParams?.lat,
                    tx_lon: rawParams?.lon,
                    tx_power: rawParams?.tx_power,
                    tx_gain: rawParams?.tx_gain,
                    frequency_mhz: rawParams?.frequency_mhz,
                  },
                  receiver: {
                    rx_height: rawParams?.rx_height,
                    rx_gain: rawParams?.rx_gain,
                    signal_threshold: rawParams?.signal_threshold,
                    rx_loss: rawParams?.system_loss,
                  },
                  environment: {
                    radio_climate: rawParams?.radio_climate,
                    polarization: rawParams?.polarization,
                    clutter_height: rawParams?.clutter_height,
                    ground_dielectric: rawParams?.ground_dielectric,
                    ground_conductivity: rawParams?.ground_conductivity,
                    atmosphere_bending: rawParams?.atmosphere_bending,
                  },
                  simulation: {
                    situation_fraction: rawParams?.situation_fraction,
                    time_fraction: rawParams?.time_fraction,
                    radius: rawParams?.radius,
                    high_resolution: rawParams?.high_resolution,
                  },
                  display: {
                    color_scale: rawParams?.colormap,
                    min_dbm: rawParams?.min_dbm,
                    max_dbm: rawParams?.max_dbm,
                    overlay_transparency: 50,
                  },
                  // tx_height lives at the top level in the flat shape
                  tx_height: rawParams?.tx_height,
                } as unknown as SplatParams
            this.localSites.push({
              params,
              taskId: meta.taskId,
              raster: markRaw(geoRaster),
              visible: true,
              rasterData: rasterBuffer,
            })
          } catch (err) {
            console.warn(`[SitesStore] Failed to restore site ${meta.taskId}:`, err)
          }
        }

        this.redrawSites()
      } catch (err) {
        console.warn('[SitesStore] Failed to restore sites from server:', err)
        // Fallback: just redraw whatever is in memory
        this.redrawSites()
      }
    },

  },
})
