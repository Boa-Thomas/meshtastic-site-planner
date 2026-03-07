<template>
  <div v-if="nodesStore.nodes.length > 0">
    <div class="d-flex justify-content-between align-items-center mb-2">
      <h6 class="text-light mb-0">Mesh Nodes ({{ nodesStore.nodes.length }})</h6>
    </div>
    <ul class="list-group">
      <li
        v-for="node in nodesStore.nodes"
        :key="node.id"
        class="list-group-item list-group-item-action d-flex justify-content-between align-items-center"
        :class="{ active: node.id === nodesStore.selectedNodeId }"
        style="cursor: pointer"
        @click="nodesStore.selectedNodeId = node.id"
      >
        <span>
          {{ node.name }}
          <span
            v-if="node.siteId && sitesStore.localSites.some(s => s.taskId === node.siteId)"
            class="badge bg-success ms-1"
            title="Has SPLAT! coverage simulation"
          >RF</span>
        </span>
        <button
          type="button"
          @click.stop="nodesStore.selectedNodeId = null"
          class="btn-close btn-close-white"
          style="font-size: 0.6rem"
          aria-label="Deselect node"
        ></button>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { useNodesStore } from '../stores/nodesStore'
import { useSitesStore } from '../stores/sitesStore'

const nodesStore = useNodesStore()
const sitesStore = useSitesStore()
</script>
