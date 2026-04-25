import { ref } from 'vue'
import { useMapStore } from '../stores/mapStore'
import { useSitesStore } from '../stores/sitesStore'
import L from 'leaflet'

export function useExport() {
  const exportLoading = ref(false)
  const exportError = ref('')

  async function exportMap() {
    const mapStore = useMapStore()
    const sitesStore = useSitesStore()

    if (!mapStore.mapContainer || !mapStore.map) return

    const corsLayers = ['OSM', 'Carto Light']
    if (!corsLayers.includes(mapStore.currentBaseLayer)) {
      exportError.value = 'Export only works on OSM and Carto Light layers.'
      return
    }
    exportError.value = ''
    exportLoading.value = true

    const savedCenter = mapStore.map.getCenter()
    const savedZoom = mapStore.map.getZoom()

    try {
      const { default: html2canvas } = await import('html2canvas')

      const vw = mapStore.mapContainer.clientWidth
      const vh = mapStore.mapContainer.clientHeight

      // Collect tight coverage bounds by scanning non-noData pixels
      const bounds = L.latLngBounds([])
      sitesStore.localSites.forEach(site => {
        const raster = site.raster as any
        if (raster?.values?.[0]) {
          const vals = raster.values[0] as number[][]
          const H = raster.height as number, W = raster.width as number
          let minR = H, maxR = -1, minC = W, maxC = -1
          for (let r = 0; r < H; r++) {
            for (let c = 0; c < W; c++) {
              if (vals[r][c] !== 255) {
                if (r < minR) minR = r
                if (r > maxR) maxR = r
                if (c < minC) minC = c
                if (c > maxC) maxC = c
              }
            }
          }
          if (maxR >= 0) {
            const latMax = (raster.ymax as number) - minR * (raster.pixelHeight as number)
            const latMin = (raster.ymax as number) - (maxR + 1) * (raster.pixelHeight as number)
            const lngMin = (raster.xmin as number) + minC * (raster.pixelWidth as number)
            const lngMax = (raster.xmin as number) + (maxC + 1) * (raster.pixelWidth as number)
            bounds.extend([[latMin, lngMin], [latMax, lngMax]])
          }
        } else {
          // Fallback for rasters not yet loaded into memory
          const b = (site.rasterLayer as any)?.getBounds?.()
          if (b) bounds.extend(b)
        }
      })

      let captures: Array<{ canvas: HTMLCanvasElement; col: number; row: number }> = []
      let cols = 1, rows = 1

      if (bounds.isValid()) {
        // Auto-select highest zoom where grid <= 81 captures (9x9 max)
        let targetZoom = 18
        for (; targetZoom >= 10; targetZoom--) {
          const sw = mapStore.map.project(bounds.getSouthWest(), targetZoom)
          const ne = mapStore.map.project(bounds.getNorthEast(), targetZoom)
          cols = Math.max(1, Math.ceil((ne.x - sw.x) / vw))
          rows = Math.max(1, Math.ceil((sw.y - ne.y) / vh))
          if (cols * rows <= 81) break
        }

        const sw = mapStore.map.project(bounds.getSouthWest(), targetZoom)
        const ne = mapStore.map.project(bounds.getNorthEast(), targetZoom)

        for (let row = 0; row < rows; row++) {
          for (let col = 0; col < cols; col++) {
            const cellCentre = mapStore.map.unproject(
              L.point(sw.x + (col + 0.5) * vw, ne.y + (row + 0.5) * vh),
              targetZoom
            )

            // 1. Move map to target cell at target zoom
            mapStore.map.setView(cellCentre, targetZoom, { animate: false })

            // 2. One rAF — lets Leaflet synchronously queue new tile requests
            await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))

            // 3. Register load listeners after tile requests are in-flight
            await new Promise<void>(resolve => {
              let done = false
              const finish = () => { if (!done) { done = true; resolve() } }
              const layers: any[] = []
              mapStore.map!.eachLayer((layer: any) => { if (layer._url) layers.push(layer) })
              if (layers.length === 0) { setTimeout(finish, 1000); return }
              layers.forEach(layer => layer.once('load', finish))
              setTimeout(finish, 5000) // fallback
            })

            // 4. One more rAF + paint delay — ensures browser decoded & painted tiles
            await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
            await new Promise(r => setTimeout(r, 300))

            const canvas = await html2canvas(mapStore.mapContainer!, { scale: 1, useCORS: true, allowTaint: false })
            captures.push({ canvas, col, row })
          }
        }
      } else {
        // No overlays — single capture at current view
        const waitForTiles = () => new Promise<void>(resolve => {
          const perLayer: Promise<void>[] = []
          mapStore.map!.eachLayer((layer: any) => {
            if (layer._url) {
              perLayer.push(new Promise<void>(res => layer.once('load', res)))
            }
          })
          if (perLayer.length === 0) { setTimeout(resolve, 1000); return }
          Promise.race([Promise.all(perLayer), new Promise<void>(r => setTimeout(r, 4000))]).then(() => resolve())
        })
        await waitForTiles()
        await new Promise(r => setTimeout(r, 500))
        const canvas = await html2canvas(mapStore.mapContainer!, { scale: 1, useCORS: true, allowTaint: false })
        captures.push({ canvas, col: 0, row: 0 })
      }

      // Stitch all cell captures into one canvas
      const out = document.createElement('canvas')
      out.width = cols * vw
      out.height = rows * vh
      const ctx = out.getContext('2d')!
      for (const { canvas, col, row } of captures) {
        ctx.drawImage(canvas, col * vw, row * vh)
      }

      // Embed in PDF and save
      const { jsPDF } = await import('jspdf')
      const w = out.width, h = out.height
      const pdf = new jsPDF({ orientation: w >= h ? 'l' : 'p', unit: 'px', format: [w, h] })
      pdf.addImage(out.toDataURL('image/jpeg', 0.92), 'JPEG', 0, 0, w, h)
      pdf.save('coverage-map.pdf')

    } catch (err) {
      exportError.value = 'Export failed. Try switching to OSM or Carto Light.'
      console.error('Export error:', err)
    } finally {
      mapStore.map!.setView(savedCenter, savedZoom, { animate: false })
      exportLoading.value = false
    }
  }

  return { exportLoading, exportError, exportMap }
}
