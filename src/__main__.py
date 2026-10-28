from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

from . import log as logmod
from .config import load
from .door2tg_loader import is_door2tg_config, load_door2tg_configs
from .gateway import Gateway

log = logging.getLogger(__name__)


async def _run_one(name: str, gw: Gateway, stop: asyncio.Future) -> None:
    task = asyncio.create_task(gw.run(), name=f"gateway-{name}")
    await stop
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def amain() -> None:
    cfgPath = Path(os.environ.get("CONFIG_PATH", "config/config.yaml"))
    rawText = cfgPath.read_text(encoding="utf-8")
    import yaml

    raw = yaml.safe_load(rawText) or {}

    loop = asyncio.get_running_loop()
    stop = loop.create_future()

    def _request_stop(*_):
        if not stop.done():
            stop.set_result(None)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _request_stop)

    if is_door2tg_config(raw):
        runtimes = load_door2tg_configs(cfgPath)
        logmod.setup(os.environ.get("LOG_LEVEL", "INFO").upper())
        log.info("starting %d tg2sip runtime(s) from Door2TG config", len(runtimes))
        gateways = [(name, Gateway(cfg)) for name, cfg in runtimes]
        await asyncio.gather(
            *[_run_one(name, gw, stop) for name, gw in gateways]
        )
        return

    cfg = load()
    logmod.setup(cfg.log_level)
    gw = Gateway(cfg)
    await _run_one("default", gw, stop)


if __name__ == "__main__":
    asyncio.run(amain())
