<template>
  <div>
    <nav class="navbar navbar-dark bg-dark fixed-top">
      <div class="container-fluid">
        <a class="navbar-brand" href="#">
          <img src="/logo.svg" alt="Meshtastic Logo" width="30" height="30" class="d-inline">
          Meshtastic Site Planner
        </a>
        <button class="navbar-toggler" type="button" data-bs-toggle="offcanvas" data-bs-target="#offcanvasDarkNavbar" aria-controls="offcanvasDarkNavbar" aria-label="Toggle navigation">
          <span class="navbar-toggler-icon"></span>
        </button>
        <div class="offcanvas offcanvas-end text-bg-dark show" tabindex="-1" id="offcanvasDarkNavbar" aria-labelledby="offcanvasDarkNavbarLabel" data-bs-backdrop="false">
          <div class="offcanvas-header">
            <h5 class="offcanvas-title" id="offcanvasDarkNavbarLabel">Site Parameters</h5>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="offcanvas" aria-label="Close"></button>
          </div>
          <div class="offcanvas-body">
            <ul class="navbar-nav">
              <li class="nav-item">
                <a class="nav-link dropdown-toggle" href="#" role="button"
                   @click.prevent="togglePanel('transmitter')"
                   :aria-expanded="openPanels.has('transmitter').toString()">Site / Transmitter</a>
                <ul :class="['dropdown-menu', 'dropdown-menu-dark', 'p-3', { show: openPanels.has('transmitter') }]"
                    style="position:static">
                  <li>
                    <Transmitter />
                  </li>
                </ul>
              </li>
              <li class="nav-item">
                <a class="nav-link dropdown-toggle" href="#" role="button"
                   @click.prevent="togglePanel('receiver')"
                   :aria-expanded="openPanels.has('receiver').toString()">Receiver</a>
                <ul :class="['dropdown-menu', 'dropdown-menu-dark', 'p-3', { show: openPanels.has('receiver') }]"
                    style="position:static">
                  <li>
                    <Receiver />
                  </li>
                </ul>
              </li>
              <li class="nav-item">
                <a class="nav-link dropdown-toggle" href="#" role="button"
                   @click.prevent="togglePanel('environment')"
                   :aria-expanded="openPanels.has('environment').toString()">Environment</a>
                <ul :class="['dropdown-menu', 'dropdown-menu-dark', 'p-3', { show: openPanels.has('environment') }]"
                    style="position:static">
                  <li>
                    <Environment />
                  </li>
                </ul>
              </li>
              <li class="nav-item">
                <a class="nav-link dropdown-toggle" href="#" role="button"
                   @click.prevent="togglePanel('simulation')"
                   :aria-expanded="openPanels.has('simulation').toString()">Simulation Options</a>
                <ul :class="['dropdown-menu', 'dropdown-menu-dark', 'p-3', { show: openPanels.has('simulation') }]"
                    style="position:static">
                  <li>
                    <Simulation />
                  </li>
                </ul>
              </li>
              <li class="nav-item">
                <a class="nav-link dropdown-toggle" href="#" role="button"
                   @click.prevent="togglePanel('display')"
                   :aria-expanded="openPanels.has('display').toString()">Display</a>
                <ul :class="['dropdown-menu', 'dropdown-menu-dark', 'p-3', { show: openPanels.has('display') }]"
                    style="position:static">
                  <li>
                    <Display />
                  </li>
                </ul>
              </li>
            </ul>
            <div class="mt-3 d-flex gap-2">
              <button :disabled="store.simulationState === 'running'" @click="store.runSimulation" type="button" class="btn btn-success btn-sm" id="runSimulation">
                <span :class="{ 'd-none': store.simulationState !== 'running' }" class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                <span class="button-text">{{ buttonText() }}</span>
              </button>
              <button :disabled="store.exportLoading" @click="store.exportMap" type="button" class="btn btn-secondary btn-sm">
                <span :class="{ 'd-none': !store.exportLoading }" class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                Export PDF
              </button>
            </div>
            <div v-if="store.exportError" class="alert alert-warning alert-dismissible mt-2 py-1 px-2 small" role="alert">
              {{ store.exportError }}
              <button type="button" class="btn-close btn-sm" @click="store.exportError = ''" aria-label="Close"></button>
            </div>
            <ul class="list-group mt-3">
              <li class="list-group-item d-flex justify-content-between align-items-center" v-for="(site, index) in store.$state.localSites" :key="site.taskId">
                <span>{{ site.params.transmitter.name }}</span>
                <button type="button" @click="store.removeSite(index)" class="btn-close" aria-label="Close"></button>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </nav>
    <div id="map" ref="map">
    </div>
  </div>
</template>

<script setup lang="ts">
import "leaflet/dist/leaflet.css"
import "bootstrap/dist/css/bootstrap.min.css"
import "bootstrap/dist/js/bootstrap.bundle.min.js"
import Transmitter from "./components/Transmitter.vue"
import Receiver from "./components/Receiver.vue"
import Environment from "./components/Environment.vue"
import Simulation from "./components/Simulation.vue"
import Display from "./components/Display.vue"

import { reactive } from 'vue'
import { useStore } from './store.ts'
const store = useStore()
const buttonText = () => {
  if ('running' === store.simulationState) {
    return 'Running'
  } else if ('failed' === store.simulationState) {
    return 'Failed'
  } else {
    return 'Run Simulation'
  }
}

// Which panels are currently expanded (transmitter + display open by default)
const openPanels = reactive(new Set(['transmitter', 'display']))
const togglePanel = (name: string) => {
  openPanels.has(name) ? openPanels.delete(name) : openPanels.add(name)
}
</script>

<style>
.leaflet-div-icon {
  background: transparent;
  border: none !important;
}
/* .leaflet-layer,
.leaflet-control-zoom-in,
.leaflet-control-zoom-out,
.leaflet-control-attribution {
  filter: invert(100%) hue-rotate(180deg) brightness(95%) contrast(90%);
} */

</style>
