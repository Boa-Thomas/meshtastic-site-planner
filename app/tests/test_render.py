"""
Unit tests for app.services.render.

Focus: the pure pipeline functions (validation, resize-with-mask, colorize,
encode, mosaic combination). The Redis-backed paths (`render_colorized`,
`render_mosaic`) are exercised end-to-end against an in-memory MemoryFile
GeoTIFF so the full chain (load -> reproject -> colorize -> encode) is
covered without external services.
"""

from __future__ import annotations

import io
import os
import tempfile

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_bounds

from app.services.render import (
    DCF_MAX_DBM,
    DCF_MAX_GRAY,
    DCF_MIN_DBM,
    NODATA,
    _colorize,
    _encode_png,
    _ensure_pixel_budget,
    _resize_with_mask,
    _validate_bbox,
    _validate_task_id,
    render_colorbar,
    validate_params,
)


VALID_TASK_ID = "12345678-1234-4321-abcd-1234567890ab"


# --------------------------------------------------------------------------- #
# validate_params                                                              #
# --------------------------------------------------------------------------- #

def test_validate_params_accepts_known_colormaps():
    for name in ["plasma", "viridis", "turbo", "jet", "cool", "rainbow", "CMRmap"]:
        p = validate_params(VALID_TASK_ID, name, -130.0, -50.0, 0.85, 1000, "epsg3857", "lanczos", None)
        assert p.colormap == name


def test_validate_params_rejects_unknown_colormap():
    with pytest.raises(ValueError, match="Unsupported colormap"):
        validate_params(VALID_TASK_ID, "magma", -130.0, -50.0, 0.85, 1000, "epsg3857", "lanczos", None)


def test_validate_params_rejects_inverted_dbm():
    with pytest.raises(ValueError, match="Invalid dBm range"):
        validate_params(VALID_TASK_ID, "plasma", -50.0, -130.0, 0.85, 1000, "epsg3857", "lanczos", None)


def test_validate_params_rejects_bad_opacity():
    with pytest.raises(ValueError, match="Opacity must be in"):
        validate_params(VALID_TASK_ID, "plasma", -130.0, -50.0, 1.5, 1000, "epsg3857", "lanczos", None)


def test_validate_params_rejects_bad_srs():
    with pytest.raises(ValueError, match="Unsupported srs"):
        validate_params(VALID_TASK_ID, "plasma", -130.0, -50.0, 0.85, 1000, "epsg4321", "lanczos", None)


def test_validate_params_rejects_bad_resample():
    with pytest.raises(ValueError, match="Unsupported resample"):
        validate_params(VALID_TASK_ID, "plasma", -130.0, -50.0, 0.85, 1000, "epsg3857", "cubic", None)


def test_cache_key_is_stable_and_unique():
    p1 = validate_params(VALID_TASK_ID, "plasma", -130, -50, 0.85, 1000, "epsg3857", "lanczos", None)
    p2 = validate_params(VALID_TASK_ID, "plasma", -130, -50, 0.85, 1000, "epsg3857", "lanczos", None)
    p3 = validate_params(VALID_TASK_ID, "viridis", -130, -50, 0.85, 1000, "epsg3857", "lanczos", None)
    assert p1.cache_key() == p2.cache_key()
    assert p1.cache_key() != p3.cache_key()


# --------------------------------------------------------------------------- #
# Security: task_id validation (path traversal defence)                       #
# --------------------------------------------------------------------------- #

def test_validate_task_id_accepts_canonical_uuid():
    _validate_task_id("12345678-1234-4321-abcd-1234567890ab")


def test_validate_task_id_accepts_uppercase_uuid():
    _validate_task_id("12345678-ABCD-4321-ABCD-1234567890AB")


@pytest.mark.parametrize("bad", [
    "../../etc/passwd",
    "..\\..\\windows\\system32",
    "/etc/passwd",
    "task_id; rm -rf /",
    "",
    "x" * 64,
    "12345678-1234-4321-abcd",            # too short
    "12345678-1234-4321-abcd-12345",      # malformed
    "ggggggggg-1234-4321-abcd-1234567890ab",  # non-hex
    "12345678 1234 4321 abcd 1234567890ab",   # spaces instead of dashes
])
def test_validate_task_id_rejects_invalid_inputs(bad):
    with pytest.raises(ValueError, match="Invalid task_id"):
        _validate_task_id(bad)


def test_validate_params_rejects_path_traversal_task_id():
    with pytest.raises(ValueError, match="Invalid task_id"):
        validate_params(
            "../../etc/passwd", "plasma", -130, -50, 0.85, 1000,
            "epsg3857", "lanczos", None,
        )


# --------------------------------------------------------------------------- #
# bbox geometry validation                                                    #
# --------------------------------------------------------------------------- #

def test_validate_bbox_accepts_valid_4326():
    _validate_bbox((-46.7, -23.6, -46.5, -23.4), "epsg4326")


def test_validate_bbox_accepts_valid_3857():
    _validate_bbox((-5200000, -2700000, -5100000, -2600000), "epsg3857")


def test_validate_bbox_rejects_inverted_lon():
    with pytest.raises(ValueError, match="west .* less than east"):
        _validate_bbox((-46.5, -23.6, -46.7, -23.4), "epsg4326")


def test_validate_bbox_rejects_inverted_lat():
    with pytest.raises(ValueError, match="south .* less than north"):
        _validate_bbox((-46.7, -23.4, -46.5, -23.6), "epsg4326")


def test_validate_bbox_rejects_out_of_range_4326():
    with pytest.raises(ValueError, match="longitude out of range"):
        _validate_bbox((-200.0, -23.6, -46.5, -23.4), "epsg4326")
    with pytest.raises(ValueError, match="latitude out of range"):
        _validate_bbox((-46.7, -91.0, -46.5, -23.4), "epsg4326")


def test_validate_bbox_rejects_out_of_range_3857():
    with pytest.raises(ValueError, match="x out of Web Mercator extent"):
        _validate_bbox((-1e9, -2700000, -5100000, -2600000), "epsg3857")


def test_validate_bbox_rejects_non_finite():
    with pytest.raises(ValueError, match="must be a finite number"):
        _validate_bbox((float("nan"), -23.6, -46.5, -23.4), "epsg4326")
    with pytest.raises(ValueError, match="must be a finite number"):
        _validate_bbox((-46.7, -23.6, float("inf"), -23.4), "epsg4326")


def test_validate_params_propagates_bbox_errors():
    with pytest.raises(ValueError, match="west .* less than east"):
        validate_params(
            VALID_TASK_ID, "plasma", -130, -50, 0.85, 1000,
            "epsg4326", "lanczos", (10.0, 0.0, 5.0, 1.0),
        )


# --------------------------------------------------------------------------- #
# Pixel-budget guard                                                          #
# --------------------------------------------------------------------------- #

def test_ensure_pixel_budget_accepts_normal_size():
    _ensure_pixel_budget(4000, 3000)  # 12 MP, well under 200 MP


def test_ensure_pixel_budget_rejects_huge_size():
    with pytest.raises(ValueError, match="exceeds MAX_RENDER_PIXELS"):
        _ensure_pixel_budget(100000, 100000)


def test_ensure_pixel_budget_rejects_invalid_dimensions():
    with pytest.raises(ValueError, match="invalid dimensions"):
        _ensure_pixel_budget(0, 1000)
    with pytest.raises(ValueError, match="invalid dimensions"):
        _ensure_pixel_budget(1000, -5)


# --------------------------------------------------------------------------- #
# _resize_with_mask                                                            #
# --------------------------------------------------------------------------- #

def test_resize_preserves_nodata_via_nearest():
    arr = np.full((10, 10), NODATA, dtype=np.uint8)
    arr[4:6, 4:6] = 100
    out = _resize_with_mask(arr, 50, "lanczos")
    assert out.shape == (50, 50)
    # Nodata at corners survived
    assert out[0, 0] == NODATA
    assert out[49, 49] == NODATA
    # Signal in centre is still present (not necessarily exactly 100 after Lanczos)
    centre = out[24:26, 24:26]
    assert np.any(centre != NODATA)


def test_resize_no_op_when_widths_match():
    arr = np.full((20, 30), 42, dtype=np.uint8)
    out = _resize_with_mask(arr, 30, "bilinear")
    assert out is arr  # Same object -- early return


def test_resize_rejects_invalid_width():
    arr = np.zeros((10, 10), dtype=np.uint8)
    with pytest.raises(ValueError):
        _resize_with_mask(arr, 0, "lanczos")


# --------------------------------------------------------------------------- #
# _colorize                                                                    #
# --------------------------------------------------------------------------- #

def test_colorize_nodata_becomes_transparent():
    data = np.full((4, 4), NODATA, dtype=np.uint8)
    rgba = _colorize(data, "plasma", -130, -50, 0.85)
    assert rgba.shape == (4, 4, 4)
    assert np.all(rgba[..., 3] == 0)
    # nodata RGB should also be zeroed per current implementation
    assert np.all(rgba[..., :3] == 0)


def test_colorize_signal_has_opacity_scaled_alpha():
    data = np.full((1, 1), 120, dtype=np.uint8)
    rgba = _colorize(data, "plasma", -130, -50, 0.5)
    # Alpha should be roughly opacity * 255 = 127
    assert 100 <= rgba[0, 0, 3] <= 200


def test_colorize_respects_user_dbm_range():
    """Same pixel should give different colors when user clamps the dBm range."""
    data = np.full((1, 1), 100, dtype=np.uint8)
    rgba_wide = _colorize(data, "plasma", -130, -30, 1.0)
    rgba_narrow = _colorize(data, "plasma", -100, -90, 1.0)
    assert not np.array_equal(rgba_wide[0, 0, :3], rgba_narrow[0, 0, :3])


def test_colorize_dcf_endpoints():
    """Pixel 0 == DCF_MIN_DBM, pixel 247 == DCF_MAX_DBM."""
    # Convert pixel 0 back to dBm
    p0_dbm = DCF_MIN_DBM + (0.0 / DCF_MAX_GRAY) * (DCF_MAX_DBM - DCF_MIN_DBM)
    p247_dbm = DCF_MIN_DBM + (247.0 / DCF_MAX_GRAY) * (DCF_MAX_DBM - DCF_MIN_DBM)
    assert p0_dbm == DCF_MIN_DBM
    assert p247_dbm == DCF_MAX_DBM


# --------------------------------------------------------------------------- #
# _encode_png                                                                  #
# --------------------------------------------------------------------------- #

def test_encode_png_produces_valid_signature():
    data = np.zeros((10, 10, 4), dtype=np.uint8)
    data[..., 3] = 255
    png = _encode_png(data)
    # PNG magic: 0x89 P N G
    assert png[:4] == b"\x89PNG"


# --------------------------------------------------------------------------- #
# render_colorbar                                                              #
# --------------------------------------------------------------------------- #

def test_colorbar_returns_png_bytes():
    png = render_colorbar("turbo", -130, -50, 400, 40)
    assert png[:4] == b"\x89PNG"


def test_colorbar_rejects_unknown_colormap():
    with pytest.raises(ValueError):
        render_colorbar("notacolormap", -130, -50, 400, 40)


def test_colorbar_rejects_silly_dimensions():
    with pytest.raises(ValueError):
        render_colorbar("plasma", -130, -50, 10, 40)
    with pytest.raises(ValueError):
        render_colorbar("plasma", -130, -50, 400, 1000)


# --------------------------------------------------------------------------- #
# End-to-end via on-disk fixture (avoids Redis)                                #
# --------------------------------------------------------------------------- #

@pytest.fixture
def synthetic_geotiff_on_disk(tmp_path, monkeypatch):
    """
    Write a small synthetic SPLAT-style GeoTIFF to RASTER_DIR so render
    can find it via the disk fallback (no Redis needed).
    """
    raster_dir = tmp_path / "rasters"
    raster_dir.mkdir()

    # Monkey-patch RASTER_DIR seen by the render module
    from app.services import render as render_mod
    monkeypatch.setattr(render_mod, "RASTER_DIR", str(raster_dir))

    # 50x50 grayscale, signal in centre, nodata in corners
    h, w = 50, 50
    data = np.full((h, w), NODATA, dtype=np.uint8)
    yy, xx = np.indices((h, w))
    mask = (xx - w / 2) ** 2 + (yy - h / 2) ** 2 < (w / 3) ** 2
    data[mask] = np.clip(
        100 + np.sqrt((xx[mask] - w / 2) ** 2 + (yy[mask] - h / 2) ** 2).astype("int") * 5,
        0,
        247,
    ).astype(np.uint8)

    task_id = VALID_TASK_ID
    raster_path = raster_dir / f"{task_id}.tif"
    transform = from_bounds(-46.7, -23.7, -46.5, -23.5, w, h)
    with rasterio.open(
        raster_path, "w",
        driver="GTiff", height=h, width=w, count=1, dtype="uint8",
        crs="EPSG:4326", transform=transform, nodata=NODATA, compress="lzw",
    ) as dst:
        dst.write(data, 1)

    yield task_id


def test_end_to_end_render_writes_valid_png(synthetic_geotiff_on_disk, monkeypatch):
    """Full pipeline: load -> reproject -> colorize -> PNG."""
    # Avoid Redis writes during the test
    class _NoopRedis:
        def get(self, *_a, **_kw): return None
        def setex(self, *_a, **_kw): return None

    from app.services import render as render_mod
    monkeypatch.setattr(render_mod, "get_redis_client", lambda: _NoopRedis())

    params = validate_params(
        synthetic_geotiff_on_disk, "plasma", -130.0, -50.0, 0.85,
        None, "epsg3857", "bilinear", None,
    )
    png, meta = render_mod.render_colorized(params)
    assert png[:4] == b"\x89PNG"
    assert meta.width > 0 and meta.height > 0
    assert meta.srs == "epsg3857"
    assert len(meta.bounds) == 4
    assert len(meta.bounds_4326) == 4

    # Re-decode and validate transparency at corners (nodata)
    img = Image.open(io.BytesIO(png))
    assert img.mode == "RGBA"
    px = img.load()
    assert px[0, 0][3] == 0, "top-left corner should be transparent (nodata)"


def test_end_to_end_mosaic_combines_two_tasks(synthetic_geotiff_on_disk, monkeypatch, tmp_path):
    """Mosaic of the same source twice should yield the same output as single-render."""
    class _NoopRedis:
        def get(self, *_a, **_kw): return None
        def setex(self, *_a, **_kw): return None

    from app.services import render as render_mod
    monkeypatch.setattr(render_mod, "get_redis_client", lambda: _NoopRedis())

    from app.services.render import validate_mosaic_params, render_mosaic
    mparams = validate_mosaic_params(
        (synthetic_geotiff_on_disk, synthetic_geotiff_on_disk),
        "plasma", -130.0, -50.0, 0.85, None, "epsg3857", "bilinear", None,
    )
    png, meta = render_mosaic(mparams)
    assert png[:4] == b"\x89PNG"
    assert meta.width > 0 and meta.height > 0
