"""Abstract base class for propagation engines."""

from abc import ABC, abstractmethod
from app.models.CoveragePredictionRequest import CoveragePredictionRequest


class PropagationEngine(ABC):
    """Interface for RF propagation prediction engines."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable engine name."""
        ...

    @abstractmethod
    def coverage_prediction(self, request: CoveragePredictionRequest) -> bytes:
        """
        Execute a coverage prediction.

        Args:
            request: The coverage prediction parameters.

        Returns:
            GeoTIFF data as bytes.

        Raises:
            RuntimeError: If the prediction fails.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this engine's binary/dependencies are available."""
        ...
