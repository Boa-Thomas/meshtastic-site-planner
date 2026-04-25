import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useSitesStore } from '../sitesStore'

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

// Mock georaster and georaster-layer-for-leaflet to avoid DOM/canvas bindings
vi.mock('georaster', () => ({ default: vi.fn() }))
vi.mock('georaster-layer-for-leaflet', () => ({ default: vi.fn() }))

// Mock leaflet to avoid JSDOM incompatibilities
vi.mock('leaflet', () => ({
  default: {
    map: vi.fn(() => ({ removeLayer: vi.fn(), addLayer: vi.fn() })),
    tileLayer: vi.fn(() => ({ addTo: vi.fn() })),
    marker: vi.fn(() => ({
      addTo: vi.fn().mockReturnThis(),
      bindPopup: vi.fn().mockReturnThis(),
      removeFrom: vi.fn(),
    })),
    control: {
      zoom: vi.fn(() => ({ addTo: vi.fn() })),
      layers: vi.fn(() => ({ addTo: vi.fn() })),
    },
    icon: vi.fn(),
    divIcon: vi.fn(),
  },
}))

// Mock mapStore to avoid real Leaflet map creation
vi.mock('../mapStore', () => ({
  useMapStore: () => ({
    map: {
      removeLayer: vi.fn(),
      addLayer: vi.fn(),
    },
  }),
}))

// Mock the layers module (custom markers used by mapStore)
vi.mock('../../layers', () => ({
  nodePinMarker: vi.fn(() => ({})),
}))

// Mock cloneObject utility used inside addSiteFromBuffer
vi.mock('../../utils', () => ({
  cloneObject: (obj: unknown) => JSON.parse(JSON.stringify(obj)),
}))

// Mock the API module so tests don't need a running backend
vi.mock('../../services/api', () => ({
  getSites: vi.fn().mockResolvedValue([]),
  getSiteRaster: vi.fn().mockResolvedValue(new ArrayBuffer(0)),
  deleteSiteApi: vi.fn().mockResolvedValue(undefined),
  deleteAllSites: vi.fn().mockResolvedValue(undefined),
}))

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('sitesStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  // ---------------------------------------------------------------------------
  // initial state
  // ---------------------------------------------------------------------------

  describe('initial state', () => {
    it('localSites starts as an empty array', () => {
      const store = useSitesStore()
      expect(store.localSites).toHaveLength(0)
    })

    it('splatParams has correct environment defaults', () => {
      const store = useSitesStore()
      const env = store.splatParams.environment

      expect(env.radio_climate).toBe('continental_subtropical')
      expect(env.polarization).toBe('vertical')
      expect(env.clutter_height).toBe(10.0)
      expect(env.ground_dielectric).toBe(15.0)
      expect(env.ground_conductivity).toBe(0.005)
      expect(env.atmosphere_bending).toBe(301.0)
    })

    it('splatParams has correct simulation defaults', () => {
      const store = useSitesStore()
      const sim = store.splatParams.simulation

      expect(sim.situation_fraction).toBe(95.0)
      expect(sim.time_fraction).toBe(95.0)
      expect(sim.simulation_extent).toBe(90.0)
      expect(sim.high_resolution).toBe(true)
    })

    it('splatParams has correct display defaults', () => {
      const store = useSitesStore()
      const disp = store.splatParams.display

      expect(disp.color_scale).toBe('plasma')
      expect(disp.min_dbm).toBe(-140.0)
      expect(disp.max_dbm).toBe(-60.0)
      expect(disp.overlay_transparency).toBe(50)
    })
  })

  // ---------------------------------------------------------------------------
  // removeSite
  // ---------------------------------------------------------------------------

  describe('removeSite', () => {
    it('removes the site at the given index', async () => {
      const store = useSitesStore()

      // Push a mock site without a rasterLayer so no map interaction is needed
      store.localSites.push({
        params: {} as any,
        taskId: 'task-001',
        raster: {},
        visible: true,
        // rasterLayer deliberately omitted — the action guards with `if (site.rasterLayer)`
      })

      expect(store.localSites.length).toBe(1)

      await store.removeSite(0)

      expect(store.localSites.length).toBe(0)
    })

    it('removes only the site at the specified index when multiple exist', async () => {
      const store = useSitesStore()

      store.localSites.push({
        params: {} as any,
        taskId: 'task-001',
        raster: {},
        visible: true,
      })
      store.localSites.push({
        params: {} as any,
        taskId: 'task-002',
        raster: {},
        visible: true,
      })

      await store.removeSite(0)

      expect(store.localSites.length).toBe(1)
      expect(store.localSites[0].taskId).toBe('task-002')
    })
  })
})
