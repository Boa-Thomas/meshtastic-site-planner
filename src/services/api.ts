/**
 * Centralized API client for server-side storage endpoints.
 * In production, requests go to the same origin. In dev, Vite proxy handles /api.
 */

import type { MeshNode } from '../types/index'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, options)
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`API ${res.status}: ${body}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

// ---------------------------------------------------------------------------
// Nodes
// ---------------------------------------------------------------------------

export async function getNodes(): Promise<MeshNode[]> {
  return request<MeshNode[]>('/api/nodes')
}

export async function createNode(node: MeshNode): Promise<MeshNode> {
  return request<MeshNode>('/api/nodes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(node),
  })
}

export async function updateNodeApi(id: string, updates: Partial<MeshNode>): Promise<MeshNode> {
  return request<MeshNode>(`/api/nodes/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
}

export async function deleteNodeApi(id: string): Promise<void> {
  return request<void>(`/api/nodes/${id}`, { method: 'DELETE' })
}

export async function deleteAllNodes(): Promise<void> {
  return request<void>('/api/nodes', { method: 'DELETE' })
}

export async function batchCreateNodes(nodes: MeshNode[]): Promise<MeshNode[]> {
  return request<MeshNode[]>('/api/nodes/batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(nodes),
  })
}

// ---------------------------------------------------------------------------
// Sites
// ---------------------------------------------------------------------------

export interface SiteMetadata {
  taskId: string
  params: string
  rasterPath: string
  createdAt: string | null
}

export async function getSites(): Promise<SiteMetadata[]> {
  return request<SiteMetadata[]>('/api/sites')
}

export async function getSiteRaster(taskId: string): Promise<ArrayBuffer> {
  const res = await fetch(`/api/sites/${taskId}/raster`)
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.arrayBuffer()
}

export async function deleteSiteApi(taskId: string): Promise<void> {
  return request<void>(`/api/sites/${taskId}`, { method: 'DELETE' })
}

export async function deleteAllSites(): Promise<void> {
  return request<void>('/api/sites', { method: 'DELETE' })
}

// ---------------------------------------------------------------------------
// Project export/import
// ---------------------------------------------------------------------------

export async function exportProjectFromServer(): Promise<Blob> {
  const res = await fetch('/api/project/export')
  if (!res.ok) throw new Error(`Export failed: ${res.status}`)
  return res.blob()
}

export async function importProjectToServer(file: Blob): Promise<{ nodesImported: number; sitesImported: number }> {
  const formData = new FormData()
  formData.append('file', file, 'project.json.gz')
  return request('/api/project/import', {
    method: 'POST',
    body: formData,
  })
}
