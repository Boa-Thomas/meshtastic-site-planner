import jsPDF from 'jspdf';
import type { Site } from './types.ts';

const MARGIN = 12;
const PAGE_W = 210;
const PAGE_H = 297;
const USABLE_W = PAGE_W - MARGIN * 2; // 186 mm

const COLS = ['Name', 'Latitude', 'Longitude', 'Freq (MHz)', 'Power (mW)', 'Range (km)', 'Res'];
const COL_W = [44, 26, 26, 25, 28, 22, 15]; // sums to 186

function siteRow(site: Site): string[] {
  const t = site.params.transmitter;
  const s = site.params.simulation;
  return [
    t.name,
    t.tx_lat.toFixed(5),
    t.tx_lon.toFixed(5),
    t.tx_freq.toFixed(1),
    (t.tx_power * 1000).toFixed(0),
    s.simulation_extent.toFixed(0),
    s.high_resolution ? 'HD' : 'Std',
  ];
}

/**
 * Manually composite the Leaflet map to a canvas.
 *
 * Why not html2canvas?
 *   Leaflet loads tile <img> elements without crossOrigin="anonymous", so the
 *   browser caches them without CORS tagging. html2canvas then tries to redraw
 *   them, tainting its canvas, and toDataURL() throws a SecurityError.
 *
 * This function:
 *   1. Re-fetches each tile with fetch(mode:'cors') — bypasses the non-CORS
 *      cache entry and gets a fresh CORS response from the server.
 *   2. Creates a blob URL (same-origin) so drawImage() never taints.
 *   3. Draws GeoRasterLayer <canvas> elements directly on top (they're always
 *      same-origin because the GeoTIFF comes from our own API).
 */
async function captureMap(mapEl: HTMLElement): Promise<string> {
  const rect = mapEl.getBoundingClientRect();
  const SCALE = 2; // retina quality
  const w = rect.width;
  const h = rect.height;

  const out = document.createElement('canvas');
  out.width = Math.round(w * SCALE);
  out.height = Math.round(h * SCALE);
  const ctx = out.getContext('2d')!;
  ctx.scale(SCALE, SCALE);

  ctx.fillStyle = '#e8e8e8';
  ctx.fillRect(0, 0, w, h);

  // ── Tile images (base map) ────────────────────────────────────────────────
  const imgs = [...mapEl.querySelectorAll('img')] as HTMLImageElement[];
  await Promise.allSettled(
    imgs.map(async (img) => {
      const ir = img.getBoundingClientRect();
      const x = ir.left - rect.left;
      const y = ir.top - rect.top;
      const iw = ir.width;
      const ih = ir.height;
      if (iw <= 0 || ih <= 0 || !img.src) return;

      try {
        // mode:'cors' requests a CORS response; this misses the non-CORS cache
        // entry so the server sends a fresh response with Access-Control-Allow-Origin.
        const resp = await fetch(img.src, { mode: 'cors' });
        if (!resp.ok) throw new Error(`${resp.status}`);
        const blob = await resp.blob();
        const blobUrl = URL.createObjectURL(blob);
        const ci = new Image();
        ci.src = blobUrl;
        await new Promise<void>((res, rej) => {
          ci.onload = () => res();
          ci.onerror = rej;
        });
        ctx.drawImage(ci, x, y, iw, ih);
        URL.revokeObjectURL(blobUrl);
      } catch {
        // Tile server doesn't support CORS (e.g. ArcGIS Satellite).
        // Draw a neutral grey square so the map still has shape.
        ctx.fillStyle = '#cccccc';
        ctx.fillRect(x, y, iw, ih);
      }
    }),
  );

  // ── Raster overlays (GeoRasterLayer canvases) ─────────────────────────────
  // These are always same-origin (GeoTIFF served by our own API), so
  // drawImage() works without any CORS gymnastics.
  const canvases = [...mapEl.querySelectorAll('canvas')] as HTMLCanvasElement[];
  for (const canvas of canvases) {
    const cr = canvas.getBoundingClientRect();
    const x = cr.left - rect.left;
    const y = cr.top - rect.top;
    try {
      ctx.drawImage(canvas, x, y, cr.width, cr.height);
    } catch {
      // Shouldn't happen for same-origin canvas, but skip if it does.
    }
  }

  return out.toDataURL('image/jpeg', 0.92);
}

// ── PDF layout helpers ────────────────────────────────────────────────────────

function drawTableHeader(pdf: jsPDF, top: number, rowH: number) {
  pdf.setFillColor(45, 45, 45);
  pdf.rect(MARGIN, top, USABLE_W, rowH, 'F');
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(8);
  pdf.setTextColor(255, 255, 255);
  let cx = MARGIN;
  COLS.forEach((col, i) => {
    pdf.text(col, cx + 2, top + 4.8);
    cx += COL_W[i];
  });
}

function drawTableRows(pdf: jsPDF, rows: Site[], top: number, rowH: number) {
  rows.forEach((site, rowIdx) => {
    const rowY = top + rowH * (rowIdx + 1);
    if (rowIdx % 2 === 0) {
      pdf.setFillColor(248, 248, 248);
      pdf.rect(MARGIN, rowY, USABLE_W, rowH, 'F');
    }
    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(8);
    pdf.setTextColor(40, 40, 40);
    let cx = MARGIN;
    siteRow(site).forEach((val, i) => {
      pdf.text(val, cx + 2, rowY + 4.8);
      cx += COL_W[i];
    });
  });
}

function drawTableBorders(pdf: jsPDF, top: number, rowCount: number, rowH: number) {
  const tableH = rowH * (rowCount + 1);
  pdf.setDrawColor(180, 180, 180);
  pdf.rect(MARGIN, top, USABLE_W, tableH);
  pdf.setDrawColor(220, 220, 220);
  for (let r = 1; r <= rowCount; r++) {
    const ry = top + rowH * r;
    pdf.line(MARGIN, ry, MARGIN + USABLE_W, ry);
  }
  let cx = MARGIN;
  COL_W.slice(0, -1).forEach((cw) => {
    cx += cw;
    pdf.line(cx, top, cx, top + tableH);
  });
}

// ── Public export ─────────────────────────────────────────────────────────────

export async function exportPDF(sites: Site[]): Promise<void> {
  const mapEl = document.getElementById('map');
  if (!mapEl) throw new Error('Map element not found');

  const imgData = await captureMap(mapEl);

  const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });

  // ── Header ──
  const headerY = MARGIN + 6;
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(15);
  pdf.setTextColor(30, 30, 30);
  pdf.text('Meshtastic Coverage Report', MARGIN, headerY);

  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(9);
  pdf.setTextColor(120, 120, 120);
  const dateStr = new Date().toLocaleDateString('en-CA', {
    year: 'numeric', month: 'long', day: 'numeric',
  });
  pdf.text(dateStr, PAGE_W - MARGIN, headerY, { align: 'right' });

  pdf.setDrawColor(210, 210, 210);
  pdf.line(MARGIN, headerY + 3, PAGE_W - MARGIN, headerY + 3);

  // ── Map screenshot ──
  const mapTop = headerY + 7;
  const mapH = 140;
  pdf.addImage(imgData, 'JPEG', MARGIN, mapTop, USABLE_W, mapH);
  pdf.setDrawColor(180, 180, 180);
  pdf.rect(MARGIN, mapTop, USABLE_W, mapH);

  // ── Sites table ──
  const ROW_H = 7;
  let curY = mapTop + mapH + 8;
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(11);
  pdf.setTextColor(30, 30, 30);
  pdf.text('Sites', MARGIN, curY);
  curY += 4;

  if (sites.length === 0) {
    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(9);
    pdf.setTextColor(150, 150, 150);
    pdf.text('No sites to display.', MARGIN, curY + 5);
  } else {
    // Split into pages if table overflows
    const maxRows1 = Math.floor((PAGE_H - MARGIN - curY - ROW_H) / ROW_H);
    const chunks: Site[][] = [sites.slice(0, maxRows1)];
    for (let i = maxRows1; i < sites.length; i += 30) {
      chunks.push(sites.slice(i, i + 30));
    }

    drawTableHeader(pdf, curY, ROW_H);
    drawTableRows(pdf, chunks[0], curY, ROW_H);
    drawTableBorders(pdf, curY, chunks[0].length, ROW_H);

    for (let p = 1; p < chunks.length; p++) {
      pdf.addPage();
      const contTop = MARGIN + 4;
      drawTableHeader(pdf, contTop, ROW_H);
      drawTableRows(pdf, chunks[p], contTop, ROW_H);
      drawTableBorders(pdf, contTop, chunks[p].length, ROW_H);
    }
  }

  // ── Footer ──
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(7);
  pdf.setTextColor(180, 180, 180);
  pdf.text('Generated by Meshtastic Site Planner', PAGE_W / 2, PAGE_H - 6, { align: 'center' });

  pdf.save(`meshtastic-coverage-${new Date().toISOString().slice(0, 10)}.pdf`);
}
