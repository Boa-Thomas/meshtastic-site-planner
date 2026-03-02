"""Tests for the propagation engine abstraction."""

import os
import pytest
from unittest.mock import patch, MagicMock

from app.services.engine import PropagationEngine


class TestPropagationEngineInterface:
    """Verify the ABC contract."""

    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            PropagationEngine()

    def test_splat_implements_interface(self):
        """Splat class should be a subclass of PropagationEngine."""
        from app.services.splat import Splat
        assert issubclass(Splat, PropagationEngine)

    def test_signal_server_implements_interface(self):
        from app.services.signal_server import SignalServerEngine
        assert issubclass(SignalServerEngine, PropagationEngine)


class TestSignalServerEngine:
    """Test SignalServerEngine properties."""

    def test_name(self):
        from app.services.signal_server import SignalServerEngine
        engine = SignalServerEngine(binary_path="/nonexistent")
        assert engine.name == "signal_server"

    def test_not_available_when_binary_missing(self):
        from app.services.signal_server import SignalServerEngine
        engine = SignalServerEngine(binary_path="/nonexistent/signalserverHD")
        assert engine.is_available() is False

    def test_propagation_models(self):
        from app.services.signal_server import PROPAGATION_MODELS
        assert "itm" in PROPAGATION_MODELS
        assert "hata" in PROPAGATION_MODELS
        assert "cost231" in PROPAGATION_MODELS
        assert PROPAGATION_MODELS["itm"] == 1


class TestEngineFactory:
    """Test the engine factory."""

    def test_unknown_engine_raises(self):
        from app.services.engine_factory import get_engine
        # Clear cache
        import app.services.engine_factory as ef
        ef._engines.clear()
        with pytest.raises(ValueError, match="Unknown propagation engine"):
            get_engine("nonexistent_engine")

    def test_default_is_splat(self):
        import app.services.engine_factory as ef
        assert ef.DEFAULT_ENGINE == os.environ.get("PROPAGATION_ENGINE", "splat")

    def test_factory_caches_instances(self):
        """Factory should return the same instance for the same engine name."""
        import app.services.engine_factory as ef
        ef._engines.clear()
        # Mock a simple engine
        mock_engine = MagicMock(spec=PropagationEngine)
        mock_engine.is_available.return_value = True
        ef._engines["test_engine"] = mock_engine
        result = ef.get_engine("test_engine")
        assert result is mock_engine
