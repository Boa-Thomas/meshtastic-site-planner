"""Tests for the per-request override and caching behavior of engine_factory."""

import pytest


class TestResolveClutterSource:
    def test_none_returns_none(self, monkeypatch):
        from app.services.engine_factory import _resolve_clutter_source
        monkeypatch.delenv("CLUTTER_BUCKET", raising=False)
        assert _resolve_clutter_source("none", 0.6) is None
        assert _resolve_clutter_source("", 0.6) is None
        assert _resolve_clutter_source(None, None) is None

    def test_unknown_source_raises(self):
        from app.services.engine_factory import _resolve_clutter_source
        with pytest.raises(ValueError, match="Unknown clutter source"):
            _resolve_clutter_source("totally-fake", 0.5)

    def test_factor_override_propagates(self, monkeypatch):
        from app.services.engine_factory import _resolve_clutter_source
        monkeypatch.setenv("CLUTTER_BUCKET", "test-bucket")
        cs = _resolve_clutter_source("lang2023", 0.42)
        assert cs is not None
        assert cs.penetration_factor == 0.42
        assert cs.bucket == "test-bucket"

    def test_factor_falls_back_to_env(self, monkeypatch):
        from app.services.engine_factory import _resolve_clutter_source
        monkeypatch.setenv("CLUTTER_BUCKET", "test-bucket")
        monkeypatch.setenv("CLUTTER_PENETRATION_FACTOR", "0.55")
        cs = _resolve_clutter_source("lang2023", None)
        assert cs is not None
        assert cs.penetration_factor == 0.55


class TestCacheNamespaceWithFactor:
    """The Splat namespace must change when the penetration factor changes,
    even if dem_source and clutter_source name are the same."""

    @staticmethod
    def _make_splat(dem: str, clutter):
        from app.services.splat import Splat
        s = Splat.__new__(Splat)
        s.dem_source = dem
        s.clutter_source = clutter
        return s

    def test_factor_in_namespace_when_clutter_on(self):
        class Stub:
            name = "lang2023"
            penetration_factor = 0.6
        s = self._make_splat("fabdem", Stub())
        assert "0.60" in s._cache_namespace
        assert s.tile_redis_key("S23W046.hgt.gz") == "dem:fabdem+lang2023@0.60:hgt:S23W046.hgt.gz"

    def test_different_factors_different_namespaces(self):
        class StubA:
            name = "lang2023"
            penetration_factor = 0.6
        class StubB:
            name = "lang2023"
            penetration_factor = 0.4
        a = self._make_splat("fabdem", StubA())
        b = self._make_splat("fabdem", StubB())
        assert a._cache_namespace != b._cache_namespace

    def test_close_factors_quantize_to_same_namespace(self):
        """Tiny perturbations < 0.005 share a namespace — calibration noise."""
        class StubA:
            name = "lang2023"
            penetration_factor = 0.6001
        class StubB:
            name = "lang2023"
            penetration_factor = 0.6004
        a = self._make_splat("fabdem", StubA())
        b = self._make_splat("fabdem", StubB())
        assert a._cache_namespace == b._cache_namespace

    def test_namespace_omits_factor_when_no_clutter(self):
        s = self._make_splat("copernicus", None)
        assert s._cache_namespace == "copernicus"
