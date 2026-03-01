import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useSitesStore } from '../sitesStore'

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

// Mock randanimal — the default export used in sitesStore state initialiser
// produces a synchronous animal name string.
vi.mock('randanimal', () => ({
  randanimalSync: () => 'mock-animal-name',
  default: { randanimalSync: () => 'mock-animal-name' },
}))

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
    currentMarker: null,
  }),
}))

// Mock the layers module (custom markers used by mapStore)
vi.mock('../../layers', () => ({
  redPinMarker: {},
  nodePinMarker: vi.fn(() => ({})),
}))

// Mock cloneObject utility used inside runSimulation
vi.mock('../../utils', () => ({
  cloneObject: (obj: unknown) => JSON.parse(JSON.stringify(obj)),
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
    it('simulationState starts as idle', () => {
      const store = useSitesStore()
      expect(store.simulationState).toBe('idle')
    })

    it('localSites starts as an empty array', () => {
      const store = useSitesStore()
      expect(store.localSites).toHaveLength(0)
    })

    it('splatParams has correct transmitter defaults', () => {
      const store = useSitesStore()
      const tx = store.splatParams.transmitter

      expect(tx.tx_lat).toBe(51.102167)
      expect(tx.tx_lon).toBe(-114.098667)
      expect(tx.tx_power).toBe(0.1)
      expect(tx.tx_freq).toBe(907.0)
      expect(tx.tx_height).toBe(2.0)
      expect(tx.tx_gain).toBe(2.0)
    })

    it('splatParams has correct receiver defaults', () => {
      const store = useSitesStore()
      const rx = store.splatParams.receiver

      expect(rx.rx_sensitivity).toBe(-130.0)
      expect(rx.rx_height).toBe(1.0)
      expect(rx.rx_gain).toBe(2.0)
      expect(rx.rx_loss).toBe(2.0)
    })

    it('splatParams has correct environment defaults', () => {
      const store = useSitesStore()
      const env = store.splatParams.environment

      expect(env.radio_climate).toBe('continental_temperate')
      expect(env.polarization).toBe('vertical')
      expect(env.clutter_height).toBe(1.0)
      expect(env.ground_dielectric).toBe(15.0)
      expect(env.ground_conductivity).toBe(0.005)
      expect(env.atmosphere_bending).toBe(301.0)
    })

    it('splatParams has correct simulation defaults', () => {
      const store = useSitesStore()
      const sim = store.splatParams.simulation

      expect(sim.situation_fraction).toBe(95.0)
      expect(sim.time_fraction).toBe(95.0)
      expect(sim.simulation_extent).toBe(30.0)
      expect(sim.high_resolution).toBe(false)
    })

    it('splatParams has correct display defaults', () => {
      const store = useSitesStore()
      const disp = store.splatParams.display

      expect(disp.color_scale).toBe('plasma')
      expect(disp.min_dbm).toBe(-130.0)
      expect(disp.max_dbm).toBe(-80.0)
      expect(disp.overlay_transparency).toBe(50)
    })
  })

  // ---------------------------------------------------------------------------
  // setTxCoords
  // ---------------------------------------------------------------------------

  describe('setTxCoords', () => {
    it('updates tx_lat in splatParams.transmitter', () => {
      const store = useSitesStore()
      store.setTxCoords(-23.55, -46.63)
      expect(store.splatParams.transmitter.tx_lat).toBe(-23.55)
    })

    it('updates tx_lon in splatParams.transmitter', () => {
      const store = useSitesStore()
      store.setTxCoords(-23.55, -46.63)
      expect(store.splatParams.transmitter.tx_lon).toBe(-46.63)
    })

    it('overwrites previous tx_lat/tx_lon values', () => {
      const store = useSitesStore()
      store.setTxCoords(10.0, 20.0)
      store.setTxCoords(-5.0, 35.0)

      expect(store.splatParams.transmitter.tx_lat).toBe(-5.0)
      expect(store.splatParams.transmitter.tx_lon).toBe(35.0)
    })
  })

  // ---------------------------------------------------------------------------
  // removeSite
  // ---------------------------------------------------------------------------

  describe('removeSite', () => {
    it('removes the site at the given index', () => {
      const store = useSitesStore()

      // Push a mock site without a rasterLayer so no map interaction is needed
      store.localSites.push({
        params: store.splatParams,
        taskId: 'task-001',
        raster: {},
        // rasterLayer deliberately omitted — the action guards with `if (site.rasterLayer)`
      })

      expect(store.localSites.length).toBe(1)

      store.removeSite(0)

      expect(store.localSites.length).toBe(0)
    })

    it('removes only the site at the specified index when multiple exist', () => {
      const store = useSitesStore()

      store.localSites.push({
        params: store.splatParams,
        taskId: 'task-001',
        raster: {},
      })
      store.localSites.push({
        params: store.splatParams,
        taskId: 'task-002',
        raster: {},
      })

      store.removeSite(0)

      expect(store.localSites.length).toBe(1)
      expect(store.localSites[0].taskId).toBe('task-002')
    })
  })
})
