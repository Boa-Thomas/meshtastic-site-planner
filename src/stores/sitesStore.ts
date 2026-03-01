import { defineStore } from 'pinia'
import { markRaw } from 'vue'
import { randanimalSync } from 'randanimal'
import GeoRasterLayer from 'georaster-layer-for-leaflet'
import parseGeoraster from 'georaster'
import L from 'leaflet'
import { type Site, type SplatParams } from '../types'
import { cloneObject } from '../utils'
import { useMapStore } from './mapStore'

export const useSitesStore = defineStore('sites', {
  state: () => ({
    localSites: [] as Site[],
    simulationState: 'idle' as string,
    splatParams: <SplatParams>{
      transmitter: {
        name: randanimalSync(),
        tx_lat: 51.102167,
        tx_lon: -114.098667,
        tx_power: 0.1,
        tx_freq: 907.0,
        tx_height: 2.0,
        tx_gain: 2.0,
      },
      receiver: {
        rx_sensitivity: -130.0,
        rx_height: 1.0,
        rx_gain: 2.0,
        rx_loss: 2.0,
      },
      environment: {
        radio_climate: 'continental_temperate',
        polarization: 'vertical',
        clutter_height: 1.0,
        ground_dielectric: 15.0,
        ground_conductivity: 0.005,
        atmosphere_bending: 301.0,
      },
      simulation: {
        situation_fraction: 95.0,
        time_fraction: 95.0,
        simulation_extent: 30.0,
        high_resolution: false,
      },
      display: {
        color_scale: 'plasma',
        min_dbm: -130.0,
        max_dbm: -80.0,
        overlay_transparency: 50,
      },
    },
  }),
  actions: {
    setTxCoords(lat: number, lon: number) {
      this.splatParams.transmitter.tx_lat = lat
      this.splatParams.transmitter.tx_lon = lon
    },
    removeSite(index: number) {
      const mapStore = useMapStore()
      if (!mapStore.map) return
      const site = this.localSites[index]
      if (site.rasterLayer) {
        mapStore.map.removeLayer(site.rasterLayer)
      }
      this.localSites.splice(index, 1)
    },
    redrawSites() {
      const mapStore = useMapStore()
      if (!mapStore.map) return
      this.localSites.forEach((site: Site) => {
        if (!site.rasterLayer) {
          // Pre-extract palette to avoid Vue Proxy wrapping in the rendering hot path.
          // geotiff-palette hardcodes alpha=255 for all entries so we handle noData (index 255)
          // explicitly by returning null.
          const palette = (site.raster as any).palette as Array<[number, number, number, number]>
          site.rasterLayer = markRaw(new GeoRasterLayer({
            georaster: site.raster,
            opacity: 0.7,
            resolution: 128,
            pixelValuesToColorFn: (values: number[]) => {
              const idx = values[0]
              if (idx === 255 || !palette) return null // noData → transparent
              const [r, g, b] = palette[idx]
              return `rgba(${r},${g},${b},1)`
            },
          }))
          site.rasterLayer.addTo(mapStore.map as L.Map)
        }
        site.rasterLayer.bringToFront()
      })
    },
    async runSimulation() {
      const mapStore = useMapStore()
      console.log('Simulation running...')
      try {
        // Collect input values
        const payload = {
          // Transmitter parameters
          lat: this.splatParams.transmitter.tx_lat,
          lon: this.splatParams.transmitter.tx_lon,
          tx_height: this.splatParams.transmitter.tx_height,
          tx_power: 10 * Math.log10(this.splatParams.transmitter.tx_power) + 30,
          tx_gain: this.splatParams.transmitter.tx_gain,
          frequency_mhz: this.splatParams.transmitter.tx_freq,

          // Receiver parameters
          rx_height: this.splatParams.receiver.rx_height,
          rx_gain: this.splatParams.receiver.rx_gain,
          signal_threshold: this.splatParams.receiver.rx_sensitivity,
          system_loss: this.splatParams.receiver.rx_loss,

          // Environment parameters
          clutter_height: this.splatParams.environment.clutter_height,
          ground_dielectric: this.splatParams.environment.ground_dielectric,
          ground_conductivity: this.splatParams.environment.ground_conductivity,
          atmosphere_bending: this.splatParams.environment.atmosphere_bending,
          radio_climate: this.splatParams.environment.radio_climate,
          polarization: this.splatParams.environment.polarization,

          // Simulation parameters
          radius: this.splatParams.simulation.simulation_extent * 1000,
          situation_fraction: this.splatParams.simulation.situation_fraction,
          time_fraction: this.splatParams.simulation.time_fraction,
          high_resolution: this.splatParams.simulation.high_resolution,

          // Display parameters
          colormap: this.splatParams.display.color_scale,
          min_dbm: this.splatParams.display.min_dbm,
          max_dbm: this.splatParams.display.max_dbm,
        }

        console.log('Payload:', payload)
        this.simulationState = 'running'

        // Send the request to the backend's /predict endpoint
        const predictResponse = await fetch('/predict', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        })

        if (!predictResponse.ok) {
          this.simulationState = 'failed'
          const errorDetails = await predictResponse.text()
          throw new Error(`Failed to start prediction: ${errorDetails}`)
        }

        const predictData = await predictResponse.json()
        const taskId = predictData.task_id

        console.log(`Prediction started with task ID: ${taskId}`)

        // Poll for task status and result
        const pollInterval = 1000 // 1 second
        const pollStatus = async () => {
          const statusResponse = await fetch(`/status/${taskId}`)
          if (!statusResponse.ok) {
            throw new Error('Failed to fetch task status.')
          }

          const statusData = await statusResponse.json()
          console.log('Task status:', statusData)

          if (statusData.status === 'completed') {
            this.simulationState = 'completed'
            console.log('Simulation completed! Adding result to the map...')

            // Fetch the GeoTIFF data
            const resultResponse = await fetch(`/result/${taskId}`)
            if (!resultResponse.ok) {
              throw new Error('Failed to fetch simulation result.')
            } else {
              const arrayBuffer = await resultResponse.arrayBuffer()
              const geoRaster = await parseGeoraster(arrayBuffer)
              this.localSites.push({
                params: cloneObject(this.splatParams),
                taskId,
                raster: geoRaster,
              })
              if (mapStore.currentMarker && mapStore.map) {
                mapStore.currentMarker.removeFrom(mapStore.map as L.Map)
              }
              this.splatParams.transmitter.name = await randanimalSync()
              this.redrawSites()
            }
          } else if (statusData.status === 'failed') {
            this.simulationState = 'failed'
          } else {
            setTimeout(pollStatus, pollInterval) // Retry after interval
          }
        }

        pollStatus() // Start polling
      } catch (error) {
        console.error('Error:', error)
      }
    },
  },
})
