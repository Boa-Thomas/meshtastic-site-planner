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
// High-resolution colorized render
// ---------------------------------------------------------------------------

export type RenderSrs = 'epsg3857' | 'epsg4326'
export type RenderResample = 'nearest' | 'bilinear' | 'lanczos'

export interface RenderOptions {
  colormap: string
  minDbm: number
  maxDbm: number
  opacity: number
  srs?: RenderSrs
  resample?: RenderResample
  /** Output width in pixels. Server auto-derives height keeping aspect. */
  width?: number
  /** Bounding box [west, south, east, north] in `srs` units. */
  bbox?: [number, number, number, number]
}

export interface RenderMeta {
  width: number
  height: number
  srs: RenderSrs
  bounds: [number, number, number, number]
  bounds_4326: [number, number, number, number]
  colormap: string
  min_dbm: number
  max_dbm: number
}

function buildRenderQuery(opts: RenderOptions): string {
  const p = new URLSearchParams({
    colormap: opts.colormap,
    min_dbm: String(opts.minDbm),
    max_dbm: String(opts.maxDbm),
    opacity: String(opts.opacity),
    srs: opts.srs ?? 'epsg3857',
    resample: opts.resample ?? 'lanczos',
  })
  if (opts.width !== undefined) p.set('width', String(Math.round(opts.width)))
  if (opts.bbox) p.set('bbox', opts.bbox.map((c) => c.toFixed(6)).join(','))
  return p.toString()
}

export async function getRenderMeta(
  taskId: string,
  opts: RenderOptions,
  signal?: AbortSignal,
): Promise<RenderMeta> {
  const qs = buildRenderQuery(opts)
  const res = await fetch(`/api/render/${taskId}/meta?${qs}`, { signal })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Render meta failed (${res.status}): ${body}`)
  }
  return res.json()
}

export async function getRenderPng(
  taskId: string,
  opts: RenderOptions,
  signal?: AbortSignal,
): Promise<{ blob: Blob; meta: RenderMeta }> {
  const qs = buildRenderQuery(opts)
  const res = await fetch(`/api/render/${taskId}?${qs}`, { signal })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Render failed (${res.status}): ${body}`)
  }
  const metaHeader = res.headers.get('X-Render-Meta')
  let meta: RenderMeta
  try {
    meta = metaHeader
      ? JSON.parse(metaHeader)
      : ({} as RenderMeta)
  } catch {
    meta = {} as RenderMeta
  }
  const blob = await res.blob()
  return { blob, meta }
}

export async function getRenderMosaicPng(
  taskIds: string[],
  opts: RenderOptions,
  signal?: AbortSignal,
): Promise<{ blob: Blob; meta: RenderMeta }> {
  const qs = buildRenderQuery(opts)
  const ids = taskIds.join(',')
  const res = await fetch(`/api/render/mosaic?task_ids=${encodeURIComponent(ids)}&${qs}`, {
    signal,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Mosaic render failed (${res.status}): ${body}`)
  }
  const metaHeader = res.headers.get('X-Render-Meta')
  let meta: RenderMeta
  try {
    meta = metaHeader ? JSON.parse(metaHeader) : ({} as RenderMeta)
  } catch {
    meta = {} as RenderMeta
  }
  const blob = await res.blob()
  return { blob, meta }
}

export function getColorbarUrl(
  colormap: string,
  minDbm: number,
  maxDbm: number,
  width = 400,
  height = 40,
): string {
  const p = new URLSearchParams({
    colormap,
    min_dbm: String(minDbm),
    max_dbm: String(maxDbm),
    width: String(width),
    height: String(height),
  })
  return `/api/render/colorbar?${p.toString()}`
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
