<template>
  <form novalidate>
        <div class="row g-2">
            <div class="col-6">
                <label for="situation_fraction" class="form-label">Situation Fraction (%)</label>
                <input v-model="simulation.situation_fraction" type="number" class="form-control form-control-sm" id="situation_fraction" required min="1" max="100" step="0.1" />
                <div class="invalid-feedback">Percentage must be between 1 and 100 (default: 50).</div>
            </div>
            <div class="col-6">
                <label for="time_fraction" class="form-label">Time Fraction (%)</label>
                <input v-model="simulation.time_fraction" type="number" class="form-control form-control-sm" id="time_fraction" required min="1" max="100" step="0.1" />
                <div class="invalid-feedback">Percentage must be between 1 and 100 (default: 90).</div>
            </div>
        </div>
        <div class="row g-2 mt-2">
            <div class="col-6">
                <label for="simulation_extent" class="form-label">Max Range (km)</label>
                <input v-model="simulation.simulation_extent" type="number" class="form-control form-control-sm" id="simulation_extent" required min="1" max="600" step="1" />
                <div class="invalid-feedback">Radius must be between 1 and 600 km.</div>
            </div>
            <div class="col-12" v-if="simulation.simulation_extent > 200">
                <small class="text-warning">
                    <i class="bi bi-exclamation-triangle"></i>
                    Large simulation (~{{ estimatedTiles }} tiles). May take several minutes.
                </small>
            </div>
        </div>
        <div class="row mt-3">
            <div class="col-12">
                <label for="high_resolution" class="form-label">High-Resolution</label>
                <div class="form-check">
                    <input v-model="simulation.high_resolution" type="checkbox" class="form-check-input" id="high_resolution" />
                    <label class="form-check-label" for="high_resolution">Use 30 meter resolution terrain data (default: 90 meter).</label>
                </div>
                <small class="text-muted d-block mt-1" v-if="simulation.high_resolution">
                    HD uses ~9× more memory; the radius is capped at 150 km. Above that the simulation falls back to standard resolution.
                </small>
            </div>
        </div>
    </form>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSitesStore } from '../stores/sitesStore'
const simulation = useSitesStore().splatParams.simulation

const estimatedTiles = computed(() => {
    const side = Math.ceil(2 * simulation.simulation_extent / 111 + 2)
    return side * side
})
</script>
