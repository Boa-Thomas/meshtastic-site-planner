"""Tests for the spatial clutter service and its integration with Splat."""

import gzip
import io
import os

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# ClutterSource — pure logic
# ---------------------------------------------------------------------------


class TestClutterSourceConfig:
    def test_requires_bucket(self):
        from app.services.clutter import ClutterSource

        with pytest.raises(ValueError, match="CLUTTER_BUCKET"):
            ClutterSource(
                name="lang2023",
                bucket="",
                prefix="",
                filename_template="{ns}{lat:02d}{ew}{lon:03d}.tif",
                penetration_factor=0.6,
            )

    def test_rejects_out_of_range_factor(self):
        from app.services.clutter import ClutterSource

        with pytest.raises(ValueError, match="PENETRATION_FACTOR"):
            ClutterSource(
                name="lang2023",
                bucket="bucket",
                prefix="",
                filename_template="{ns}{lat:02d}{ew}{lon:03d}.tif",
                penetration_factor=1.5,
            )

    def test_s3_key_default_template(self):
        from app.services.clutter import ClutterSource

        cs = ClutterSource(
            name="lang2023",
            bucket="bucket",
            prefix="",
            filename_template="{ns}{lat:02d}{ew}{lon:03d}.tif",
            penetration_factor=0.5,
        )
        assert cs.s3_key("S23W046.hgt.gz") == "S23W046.tif"

    def test_s3_key_with_prefix(self):
        from app.services.clutter import ClutterSource

        cs = ClutterSource(
            name="custom",
            bucket="bucket",
            prefix="canopy/",
            filename_template="{ns}{lat:02d}{ew}{lon:03d}.tif",
            penetration_factor=0.5,
        )
        assert cs.s3_key("N35W120.hgt.gz") == "canopy/N35W120.tif"


class TestMakeClutterSourceFromEnv:
    def test_disabled_returns_none(self, monkeypatch):
        from app.services import clutter

        monkeypatch.delenv("CLUTTER_SOURCE", raising=False)
        assert clutter.make_clutter_source_from_env() is None

    def test_explicit_none_returns_none(self, monkeypatch):
        from app.services import clutter

        monkeypatch.setenv("CLUTTER_SOURCE", "none")
        assert clutter.make_clutter_source_from_env() is None

    def test_unknown_source_raises(self, monkeypatch):
        from app.services import clutter

        monkeypatch.setenv("CLUTTER_SOURCE", "totally-fake")
        with pytest.raises(ValueError, match="Unknown CLUTTER_SOURCE"):
            clutter.make_clutter_source_from_env()


# ---------------------------------------------------------------------------
# Splat._apply_clutter — synthetic DSM construction
# ---------------------------------------------------------------------------


def _hgt_gz_from_array(arr: np.ndarray) -> bytes:
    """Encode an int16 array as gzipped raw HGT bytes."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(arr.astype(">i2").tobytes())
    return buf.getvalue()


class _StubClutterSource:
    """Test double that returns a fixed canopy grid without hitting S3."""

    name = "stub"
    penetration_factor = 1.0

    def __init__(self, canopy_grid: np.ndarray | None):
        self._canopy_grid = canopy_grid

    def get_effective_height_grid(self, tile_name: str):
        return self._canopy_grid


class TestApplyClutter:
    @pytest.fixture(autouse=True)
    def import_splat(self):
        from app.services.splat import Splat

        self.Splat = Splat

    def _make_splat(self, clutter_source) -> "Splat":
        instance = self.Splat.__new__(self.Splat)
        instance.dem_source = "copernicus"
        instance.clutter_source = clutter_source
        return instance

    def test_no_canopy_tile_returns_dtm_unchanged(self):
        dtm = np.full((3601, 3601), 100, dtype=">i2")
        tile_data = _hgt_gz_from_array(dtm)
        splat = self._make_splat(_StubClutterSource(canopy_grid=None))
        result = splat._apply_clutter(tile_data, "N00E000.hgt.gz")
        assert result == tile_data  # bytes-identical, no re-encode

    def test_canopy_added_to_terrain(self):
        dtm = np.full((3601, 3601), 100, dtype=">i2")
        canopy = np.full((3601, 3601), 15.0, dtype="float32")
        tile_data = _hgt_gz_from_array(dtm)
        splat = self._make_splat(_StubClutterSource(canopy_grid=canopy))
        result = splat._apply_clutter(tile_data, "N00E000.hgt.gz")
        decoded = np.frombuffer(gzip.decompress(result), dtype=">i2").reshape(3601, 3601)
        assert decoded[1500, 1500] == 115  # 100 + 15

    def test_voids_preserved(self):
        """A -32768 sentinel must remain intact even with canopy on top."""
        dtm = np.full((3601, 3601), 100, dtype=">i2")
        dtm[0, 0] = -32768
        canopy = np.full((3601, 3601), 20.0, dtype="float32")
        tile_data = _hgt_gz_from_array(dtm)
        splat = self._make_splat(_StubClutterSource(canopy_grid=canopy))
        result = splat._apply_clutter(tile_data, "N00E000.hgt.gz")
        decoded = np.frombuffer(gzip.decompress(result), dtype=">i2").reshape(3601, 3601)
        assert decoded[0, 0] == -32768
        assert decoded[10, 10] == 120  # non-void cells still get canopy

    def test_output_size_matches_srtmhgt(self):
        dtm = np.full((3601, 3601), 50, dtype=">i2")
        canopy = np.full((3601, 3601), 5.0, dtype="float32")
        splat = self._make_splat(_StubClutterSource(canopy_grid=canopy))
        result = splat._apply_clutter(_hgt_gz_from_array(dtm), "N00E000.hgt.gz")
        raw = gzip.decompress(result)
        assert len(raw) == 3601 * 3601 * 2


# ---------------------------------------------------------------------------
# Cache namespacing — clutter must NOT collide with bare-DEM caches
# ---------------------------------------------------------------------------


class TestCacheNamespaceWithClutter:
    def _make_splat(self, dem_source: str, clutter_source):
        from app.services.splat import Splat

        instance = Splat.__new__(Splat)
        instance.dem_source = dem_source
        instance.clutter_source = clutter_source
        return instance

    def test_no_clutter_keeps_legacy_namespace(self):
        s = self._make_splat("copernicus", None)
        assert s._cache_namespace == "copernicus"
        assert s._disk_key("N00E000.hgt.gz") == "copernicus:N00E000.hgt.gz"

    def test_clutter_appended_to_namespace(self):
        stub = _StubClutterSource(canopy_grid=None)
        s = self._make_splat("fabdem", stub)
        assert s._cache_namespace == "fabdem+stub"
        assert s.tile_redis_key("S23W046.hgt.gz") == "dem:fabdem+stub:hgt:S23W046.hgt.gz"
        assert s._sdf_redis_key("-23:-22:45:46.sdf") == "dem:fabdem+stub:sdf:-23:-22:45:46.sdf"

    def test_different_clutter_sources_have_different_namespaces(self):
        a = self._make_splat("copernicus", _StubClutterSource(canopy_grid=None))
        a.clutter_source.name = "lang2023"
        b = self._make_splat("copernicus", _StubClutterSource(canopy_grid=None))
        b.clutter_source.name = "mapbiomas"
        assert a._cache_namespace != b._cache_namespace
