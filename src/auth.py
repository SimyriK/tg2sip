"""Interactive Telegram login for each tg2sip runtime.

  CONFIG_PATH=/app/door2tg-config/config.yaml \\
    docker compose run --rm tg2sip python -m src.auth

With Door2TG config, authenticates every runtime (or RUNTIME=<id> for one).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import yaml
from pyrogram import Client

from . import log as logmod
from .config import load
from .door2tg_loader import is_door2tg_config, load_door2tg_configs


async def _auth_one(api_id: int, api_hash: str, session_name: str, session_dir: Path) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    client = Client(
        name=session_name,
        api_id=api_id,
        api_hash=api_hash,
        workdir=str(session_dir),
    )
    await client.start()
    me = await client.get_me()
    print(f"signed in as {me.username or me.phone_number} (id={me.id})")
    print(f"session file: {session_dir / (session_name + '.session')}")
    await client.stop()


async def amain() -> None:
    cfgPath = Path(os.environ.get("CONFIG_PATH", "config/config.yaml"))
    raw = yaml.safe_load(cfgPath.read_text(encoding="utf-8")) or {}
    logmod.setup(os.environ.get("LOG_LEVEL", "INFO").upper())

    if is_door2tg_config(raw):
        runtimes = load_door2tg_configs(cfgPath)
        only = os.environ.get("RUNTIME", "").strip()
        for name, cfg in runtimes:
            if only and name != only:
                continue
            print(f"=== auth runtime {name} ===")
            await _auth_one(
                cfg.telegram.api_id,
                cfg.telegram.api_hash,
                cfg.telegram.session_name,
                cfg.telegram.session_dir,
            )
        return

    cfg = load()
    await _auth_one(
        cfg.telegram.api_id,
        cfg.telegram.api_hash,
        cfg.telegram.session_name,
        cfg.telegram.session_dir,
    )


if __name__ == "__main__":
    asyncio.run(amain())
