from abc import ABC, abstractmethod
from src.services.chunker import DiffChunk
from src.models.schemas import Finding

class BaseProvider(ABC):
    @abstractmethod
    async def analyze_chunk(self, chunk: DiffChunk) -> list[Finding]:
        """
        Analyzes a single DiffChunk and returns a list of discovered findings.
        """
        pass
