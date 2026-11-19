from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.config.settings import Settings
from app.data.mock_provider import MockProvider, MockSyncAdapter
from app.data.provider import IDataProvider, IDataSyncAdapter


ProviderFactory = Callable[[Settings], IDataProvider]
SyncFactory = Callable[[Settings, IDataProvider], IDataSyncAdapter | None]


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderFactory] = {}
        self._syncs: dict[str, SyncFactory] = {}

    def register(
        self,
        name: str,
        factory: ProviderFactory,
        sync_factory: SyncFactory | None = None,
    ) -> None:
        self._providers[name] = factory
        if sync_factory is not None:
            self._syncs[name] = sync_factory

    def create(self, settings: Settings) -> IDataProvider:
        name = settings.data.provider
        if name not in self._providers:
            known = ", ".join(sorted(self._providers))
            raise KeyError(f"unknown provider '{name}'; known: {known}")
        return self._providers[name](settings)

    def create_sync(
        self, settings: Settings, provider: IDataProvider
    ) -> IDataSyncAdapter | None:
        factory = self._syncs.get(provider.provider_id)
        if factory is None:
            return None
        return factory(settings, provider)

    def names(self) -> list[str]:
        return sorted(self._providers)


def _mock_factory(_: Settings) -> IDataProvider:
    return MockProvider()


def _mock_sync(_: Settings, provider: IDataProvider) -> IDataSyncAdapter | None:
    if isinstance(provider, MockProvider):
        return MockSyncAdapter(provider)
    return None


def build_default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register("mock", _mock_factory, _mock_sync)

    def tdx_factory(settings: Settings) -> IDataProvider:
        from app.data.tdx_local import TdxLocalProvider

        return TdxLocalProvider(Path(settings.data.tdx.vipdoc))

    def tdx_sync(settings: Settings, provider: IDataProvider) -> IDataSyncAdapter | None:
        from app.data.tdx_sync import TdxLocalSyncAdapter

        return TdxLocalSyncAdapter(settings, provider)

    registry.register("tdx_local", tdx_factory, tdx_sync)
    return registry


DEFAULT_REGISTRY = build_default_registry()
