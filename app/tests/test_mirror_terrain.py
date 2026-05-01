"""Pure-logic tests for utils/mirror_terrain.py — no S3, no rasterio I/O."""

import importlib.util
import io
import os
import struct
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def mirror_module():
    """Import the standalone CLI module without polluting sys.path."""
    path = REPO_ROOT / "utils" / "mirror_terrain.py"
    spec = importlib.util.spec_from_file_location("mirror_terrain", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["mirror_terrain"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Tile naming
# ---------------------------------------------------------------------------


class TestTileName:
    def test_north_east(self, mirror_module):
        assert mirror_module.tile_name_for(35, 120) == "N35E120"

    def test_south_west(self, mirror_module):
        assert mirror_module.tile_name_for(-23, -46) == "S23W046"

    def test_zero(self, mirror_module):
        assert mirror_module.tile_name_for(0, 0) == "N00E000"


class TestTilesInBbox:
    def test_small_bbox_brazil(self, mirror_module):
        # São Paulo state-ish: 2x3 tile grid.
        tiles = mirror_module.tiles_in_bbox(-25, -49, -23, -46)
        assert sorted(tiles) == sorted([
            "S25W049", "S25W048", "S25W047",
            "S24W049", "S24W048", "S24W047",
        ])

    def test_rejects_inverted_bbox(self, mirror_module):
        with pytest.raises(ValueError, match="bbox"):
            mirror_module.tiles_in_bbox(10, -50, -10, 50)

    def test_fractional_extends_outwards(self, mirror_module):
        # Half a degree should still pull the tile that contains the centre.
        tiles = mirror_module.tiles_in_bbox(-23.5, -46.5, -23.1, -46.1)
        assert "S24W047" in tiles


class TestFilenameFor:
    def test_default_template(self, mirror_module):
        assert mirror_module.filename_for("S23W046", "{tile}.tif") == "S23W046.tif"

    def test_fabdem_template(self, mirror_module):
        result = mirror_module.filename_for("N35E120", "{tile}_FABDEM_V1-2.tif")
        assert result == "N35E120_FABDEM_V1-2.tif"

    def test_split_template(self, mirror_module):
        # Some operators use {ns}/{lat}/{ew}{lon} layouts.
        template = "{ns}{lat:02d}/{ns}{lat:02d}{ew}{lon:03d}.tif"
        assert mirror_module.filename_for("S23W046", template) == "S23/S23W046.tif"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidateTileBytes:
    def test_too_small_is_invalid(self, mirror_module):
        result = mirror_module.validate_tile_bytes(b"hi", "fabdem", deep=False)
        assert not result.ok
        assert "small" in result.error

    def test_non_tiff_is_invalid(self, mirror_module):
        # 256 bytes that don't start with a TIFF magic.
        payload = b"\x00\x01\x02\x03" + os.urandom(252)
        result = mirror_module.validate_tile_bytes(payload, "fabdem", deep=False)
        assert not result.ok
        assert "TIFF" in result.error

    def test_tiff_magic_passes_shallow_check(self, mirror_module):
        # 'II' + 42 + a kilobyte of zeros — invalid TIFF inside, but the magic
        # check is the only thing that runs in shallow mode.
        payload = b"II" + struct.pack("<H", 42) + b"\x00" * 1024
        result = mirror_module.validate_tile_bytes(payload, "fabdem", deep=False)
        assert result.ok
        assert result.size_bytes == len(payload)


class TestParseBbox:
    def test_valid(self, mirror_module):
        assert mirror_module.parse_bbox("-25,-49,-23,-46") == (-25.0, -49.0, -23.0, -46.0)

    def test_invalid_count(self, mirror_module):
        import argparse
        with pytest.raises(argparse.ArgumentTypeError):
            mirror_module.parse_bbox("1,2,3")
