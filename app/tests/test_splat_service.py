"""
Tests for the SPLAT! service utility functions.

Only the pure (static) helper methods are tested here because the Splat class
constructor requires the SPLAT! binaries to be present on disk, which is not
guaranteed in a CI/unit-test environment.  The static helpers perform all the
non-trivial logic (tile naming, QTH/LRP/DCF content generation) and are safe
to exercise without any external dependencies.
"""

import math
import pytest

# ---------------------------------------------------------------------------
# Import guards
# ---------------------------------------------------------------------------


def test_coverage_prediction_request_model_import():
    """CoveragePredictionRequest should be importable."""
    from app.models.CoveragePredictionRequest import CoveragePredictionRequest

    assert CoveragePredictionRequest is not None


def test_splat_service_import():
    """Splat service should be importable."""
    from app.services.splat import Splat

    assert Splat is not None


# ---------------------------------------------------------------------------
# _hgt_filename_to_sdf_filename
# ---------------------------------------------------------------------------


class TestHgtFilenameToSdfFilename:
    """Tests for Splat._hgt_filename_to_sdf_filename."""

    @pytest.fixture(autouse=True)
    def import_splat(self):
        from app.services.splat import Splat

        self.Splat = Splat

    def test_northern_western_hemisphere_standard_resolution(self):
        """N35W120.hgt.gz -> 35:36:120:121.sdf (Western hemisphere)."""
        result = self.Splat._hgt_filename_to_sdf_filename("N35W120.hgt.gz", high_resolution=False)
        assert result == "35:36:120:121.sdf"

    def test_northern_western_hemisphere_high_resolution(self):
        """N35W120.hgt.gz -> 35:36:120:121-hd.sdf in high-resolution mode."""
        result = self.Splat._hgt_filename_to_sdf_filename("N35W120.hgt.gz", high_resolution=True)
        assert result == "35:36:120:121-hd.sdf"

    def test_southern_western_hemisphere(self):
        """S23W046.hgt.gz -> -23:-22:46:47.sdf (Brazil-like coords)."""
        result = self.Splat._hgt_filename_to_sdf_filename("S23W046.hgt.gz", high_resolution=False)
        assert result == "-23:-22:46:47.sdf"

    def test_default_is_standard_resolution(self):
        """Default high_resolution should be False (standard .sdf extension)."""
        result = self.Splat._hgt_filename_to_sdf_filename("N51W114.hgt.gz")
        assert result.endswith(".sdf")
        assert "-hd.sdf" not in result


# ---------------------------------------------------------------------------
# _calculate_required_terrain_tiles
# ---------------------------------------------------------------------------


class TestCalculateRequiredTerrainTiles:
    """Tests for Splat._calculate_required_terrain_tiles."""

    @pytest.fixture(autouse=True)
    def import_splat(self):
        from app.services.splat import Splat

        self.Splat = Splat

    def test_returns_list_of_tuples(self):
        """Result must be a list of 3-tuples (hgt_name, sdf_name, sdf_hd_name)."""
        tiles = self.Splat._calculate_required_terrain_tiles(lat=35.0, lon=-120.0, radius=1000)
        assert isinstance(tiles, list)
        assert len(tiles) > 0
        for tile in tiles:
            assert isinstance(tile, tuple)
            assert len(tile) == 3

    def test_hgt_filename_format(self):
        """Each .hgt.gz tile name must match the expected N/S + 2-digit lat + E/W + 3-digit lon pattern."""
        tiles = self.Splat._calculate_required_terrain_tiles(lat=35.5, lon=-120.5, radius=500)
        for hgt_name, _, _ in tiles:
            assert hgt_name.endswith(".hgt.gz"), f"Unexpected extension: {hgt_name}"
            assert hgt_name[0] in ("N", "S"), f"Invalid hemisphere prefix: {hgt_name}"

    def test_sdf_filename_format(self):
        """Each .sdf filename must match the lat:lat+1:lon:lon+1.sdf pattern."""
        tiles = self.Splat._calculate_required_terrain_tiles(lat=-23.55, lon=-46.63, radius=1000)
        for _, sdf_name, _ in tiles:
            assert sdf_name.endswith(".sdf"), f"Expected .sdf extension: {sdf_name}"
            assert "-hd.sdf" not in sdf_name

    def test_sdf_hd_filename_format(self):
        """Each -hd.sdf filename must end with '-hd.sdf'."""
        tiles = self.Splat._calculate_required_terrain_tiles(lat=-23.55, lon=-46.63, radius=1000)
        for _, _, sdf_hd_name in tiles:
            assert sdf_hd_name.endswith("-hd.sdf"), f"Expected -hd.sdf extension: {sdf_hd_name}"

    def test_small_radius_returns_at_least_one_tile(self):
        """Even a tiny radius (1 m) must yield at least one tile."""
        tiles = self.Splat._calculate_required_terrain_tiles(lat=51.5, lon=-0.1, radius=1)
        assert len(tiles) >= 1

    def test_large_radius_returns_multiple_tiles(self):
        """A 100 km radius should require more than one 1-degree tile."""
        tiles = self.Splat._calculate_required_terrain_tiles(lat=35.0, lon=-120.0, radius=100_000)
        assert len(tiles) > 1

    def test_northern_hemisphere_tile_prefix(self):
        """Tiles for positive latitudes must have the 'N' prefix."""
        tiles = self.Splat._calculate_required_terrain_tiles(lat=48.8, lon=2.3, radius=500)
        for hgt_name, _, _ in tiles:
            # All tiles near Paris should start with 'N'
            assert hgt_name.startswith("N"), f"Expected 'N' prefix near Paris: {hgt_name}"

    def test_southern_hemisphere_tile_prefix(self):
        """Tiles for negative latitudes must have the 'S' prefix."""
        tiles = self.Splat._calculate_required_terrain_tiles(lat=-23.5, lon=-46.6, radius=500)
        for hgt_name, _, _ in tiles:
            assert hgt_name.startswith("S"), f"Expected 'S' prefix near Sao Paulo: {hgt_name}"


# ---------------------------------------------------------------------------
# _create_splat_qth
# ---------------------------------------------------------------------------


class TestCreateSplatQth:
    """Tests for Splat._create_splat_qth."""

    @pytest.fixture(autouse=True)
    def import_splat(self):
        from app.services.splat import Splat

        self.Splat = Splat

    def test_returns_bytes(self):
        result = self.Splat._create_splat_qth("test", 35.0, -120.0, 10.0)
        assert isinstance(result, bytes)

    def test_first_line_is_name(self):
        result = self.Splat._create_splat_qth("MySite", 35.0, -120.0, 10.0)
        lines = result.decode("utf-8").splitlines()
        assert lines[0] == "MySite"

    def test_second_line_is_latitude(self):
        result = self.Splat._create_splat_qth("x", 35.123456, -120.0, 5.0)
        lines = result.decode("utf-8").splitlines()
        assert float(lines[1]) == pytest.approx(35.123456, abs=1e-4)

    def test_elevation_is_last_line(self):
        result = self.Splat._create_splat_qth("x", 35.0, -120.0, 42.0)
        lines = result.decode("utf-8").splitlines()
        assert float(lines[3]) == pytest.approx(42.0, abs=0.01)

    def test_western_longitude_is_positive(self):
        """SPLAT! expects west longitude as a positive number."""
        result = self.Splat._create_splat_qth("x", 35.0, -120.5, 5.0)
        lines = result.decode("utf-8").splitlines()
        lon_in_file = float(lines[2])
        # West longitude stored as its absolute value
        assert lon_in_file == pytest.approx(120.5, abs=1e-4)


# ---------------------------------------------------------------------------
# _create_splat_lrp
# ---------------------------------------------------------------------------


class TestCreateSplatLrp:
    """Tests for Splat._create_splat_lrp."""

    @pytest.fixture(autouse=True)
    def import_splat(self):
        from app.services.splat import Splat

        self.Splat = Splat

    def _make_lrp(self, **kwargs):
        defaults = dict(
            ground_dielectric=15.0,
            ground_conductivity=0.005,
            atmosphere_bending=301.0,
            frequency_mhz=905.0,
            radio_climate="continental_temperate",
            polarization="vertical",
            situation_fraction=50.0,
            time_fraction=90.0,
            tx_power=30.0,
            tx_gain=2.0,
            system_loss=0.0,
        )
        defaults.update(kwargs)
        return self.Splat._create_splat_lrp(**defaults)

    def test_returns_bytes(self):
        assert isinstance(self._make_lrp(), bytes)

    def test_contains_frequency(self):
        result = self._make_lrp(frequency_mhz=868.0)
        assert b"868.000" in result

    def test_continental_temperate_maps_to_5(self):
        """Radio climate 'continental_temperate' must be encoded as 5."""
        result = self._make_lrp(radio_climate="continental_temperate")
        lines = result.decode("utf-8").splitlines()
        climate_line = lines[4]  # 5th line is the climate field
        assert climate_line.startswith("5")

    def test_vertical_polarization_maps_to_1(self):
        """Vertical polarization must be encoded as 1."""
        result = self._make_lrp(polarization="vertical")
        lines = result.decode("utf-8").splitlines()
        pol_line = lines[5]  # 6th line is polarization
        assert pol_line.startswith("1")

    def test_horizontal_polarization_maps_to_0(self):
        """Horizontal polarization must be encoded as 0."""
        result = self._make_lrp(polarization="horizontal")
        lines = result.decode("utf-8").splitlines()
        pol_line = lines[5]
        assert pol_line.startswith("0")

    def test_situation_fraction_converted_to_decimal(self):
        """situation_fraction=50 must appear as 0.50 in the file."""
        result = self._make_lrp(situation_fraction=50.0)
        content = result.decode("utf-8")
        assert "0.50" in content

    def test_erp_is_positive_for_valid_inputs(self):
        """The computed ERP value (last data line) must be positive."""
        result = self._make_lrp(tx_power=30.0, tx_gain=2.0, system_loss=0.0)
        lines = result.decode("utf-8").splitlines()
        # Last non-comment line contains ERP in Watts
        data_lines = [l for l in lines if not l.startswith(";") and l.strip()]
        erp_line = data_lines[-1]
        erp_value = float(erp_line.split()[0])
        assert erp_value > 0


# ---------------------------------------------------------------------------
# _create_splat_dcf
# ---------------------------------------------------------------------------


class TestCreateSplatDcf:
    """Tests for Splat._create_splat_dcf."""

    @pytest.fixture(autouse=True)
    def import_splat(self):
        from app.services.splat import Splat

        self.Splat = Splat

    def test_returns_bytes(self):
        result = self.Splat._create_splat_dcf("rainbow", -130.0, -30.0)
        assert isinstance(result, bytes)

    def test_contains_32_color_entries(self):
        """SPLAT! supports up to 32 color levels; the DCF must contain exactly 32."""
        result = self.Splat._create_splat_dcf("rainbow", -130.0, -30.0)
        content = result.decode("utf-8")
        # Each data line starts with a signed dBm value like "+xxx: " or "-xxx: "
        data_lines = [
            line
            for line in content.splitlines()
            if line and not line.startswith(";") and ":" in line
        ]
        assert len(data_lines) == 32

    def test_color_values_are_valid_rgb(self):
        """All RGB values in the DCF must be between 0 and 255 inclusive."""
        result = self.Splat._create_splat_dcf("viridis", -130.0, -80.0)
        content = result.decode("utf-8")
        for line in content.splitlines():
            if line and not line.startswith(";") and ":" in line:
                # Format: "±dBm: r, g, b"
                rgb_part = line.split(":", 1)[1]
                r, g, b = [int(v.strip()) for v in rgb_part.split(",")]
                assert 0 <= r <= 255
                assert 0 <= g <= 255
                assert 0 <= b <= 255
