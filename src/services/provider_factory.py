from src.providers.base import BaseProvider
from src.providers.mock_provider import MockProvider
from src.providers.llm_provider import LLMProvider

class ProviderFactory:
    @staticmethod
    def get_provider(name: str) -> BaseProvider:
        if name.lower() == "llm":
            return LLMProvider()
        return MockProvider()

provider_factory = ProviderFactory()
