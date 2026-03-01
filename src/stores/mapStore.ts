import { defineStore } from 'pinia'
import { markRaw } from 'vue'
import L from 'leaflet'
import { redPinMarker } from '../layers'

export const useMapStore = defineStore('map', {
  state: () => ({
    map: undefined as undefined | L.Map,
    mapContainer: undefined as undefined | HTMLElement,
    currentBaseLayer: 'OSM' as string,
    currentMarker: undefined as undefined | L.Marker,
  }),
  actions: {
    initMap(container: HTMLElement, position: [number, number]) {
      this.mapContainer = container
      this.map = markRaw(L.map(container, {
        zoom: 10,
        zoomControl: false,
      }))
      this.map.setView(position, 10)

      L.control.zoom({ position: 'bottomleft' }).addTo(this.map as L.Map)

      const cartoLight = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '© OpenStreetMap contributors © CARTO',
        crossOrigin: 'anonymous',
      })

      const streetLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        crossOrigin: 'anonymous',
      })

      const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles © Esri — Source: Esri, USGS, NOAA',
      })

      const topoLayer = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
        attribution: 'Map data: © OpenStreetMap contributors, SRTM | OpenTopoMap',
      })

      streetLayer.addTo(this.map as L.Map)

      // Base Layers
      const baseLayers: Record<string, L.TileLayer> = {
        'OSM': streetLayer,
        'Carto Light': cartoLight,
        'Satellite': satelliteLayer,
        'Topo Map': topoLayer,
      }

      L.control.layers(baseLayers, {}, {
        position: 'bottomleft',
      }).addTo(this.map as L.Map)

      this.map.on('baselayerchange', (e: L.LayersControlEvent) => {
        this.currentBaseLayer = e.name
        // Import sitesStore lazily inside the action body to avoid circular dependency
        import('./sitesStore').then(({ useSitesStore }) => {
          useSitesStore().redrawSites()
        })
      })

      this.currentMarker = markRaw(
        L.marker(position, { icon: redPinMarker })
          .addTo(this.map as L.Map)
          .bindPopup('Transmitter site')
      )

      // Lazily call redrawSites to render any existing coverage layers
      import('./sitesStore').then(({ useSitesStore }) => {
        useSitesStore().redrawSites()
      })
    },
  },
})
