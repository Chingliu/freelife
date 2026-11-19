from __future__ import annotations

import argparse
import logging

from app.config.logging_config import setup_logging
from app.config.settings import Settings
from app.data.registry import DEFAULT_REGISTRY
from app.data.tdx_sync import DataSyncJob, TdxLocalSyncAdapter, freshness_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EOD data sync")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--download",
        action="store_true",
        help="refresh vipdoc: pytdx incremental first, then hsjday.zip fallback",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ingest-limit", type=int, default=50)
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)

    settings = Settings.load(args.config)
    setup_logging(settings.log_level)
    log = logging.getLogger("sync_eod")

    provider = DEFAULT_REGISTRY.create(settings)
    adapter = DEFAULT_REGISTRY.create_sync(settings, provider)
    if isinstance(adapter, TdxLocalSyncAdapter):
        adapter.download = args.download
        adapter.ingest_limit = args.ingest_limit

    if args.dry_run:
        as_of = provider.get_data_as_of()
        log.info(
            "dry-run provider=%s as_of=%s fresh=%s",
            provider.provider_id,
            as_of,
            freshness_ok(as_of),
        )
        return 0

    job = DataSyncJob(settings, provider, adapter)
    result = job.run(force=args.force or True)
    log.info("sync result ok=%s msg=%s as_of=%s", result.ok, result.message, result.as_of)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
