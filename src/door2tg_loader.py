"""Load Door2TG config.yaml and build one tg2sip Config per runtime."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

from .config import (
    BehaviourConfig,
    BridgeConfig,
    Config,
    SipConfig,
    TelegramConfig,
    VideoConfig,
)

log = logging.getLogger(__name__)

# Minimal media defaults when Door2TG config has no tg2sip bridge section.
_DEFAULT_CALL_PROTOCOL = {
    "min_layer": 92,
    "max_layer": 92,
    "udp_p2p": True,
    "udp_reflector": True,
    "library_versions": ["8.0.0", "9.0.0", "12.0.0", "13.0.0"],
}


def is_door2tg_config(raw: dict) -> bool:
    return isinstance(raw, dict) and "doors" in raw and "sip_accounts" in raw


def load_door2tg_configs(path: Path) -> list[tuple[str, Config]]:
    """Return (runtimeId, Config) for every unique (tg, sip) used by doors."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not is_door2tg_config(raw):
        raise ValueError(f"not a Door2TG config: {path}")

    tgAccounts = raw.get("telegram_accounts") or {}
    sipAccounts = raw.get("sip_accounts") or {}
    doors = raw.get("doors") or {}

    buckets: dict[tuple[str, str], list[str]] = {}
    for doorId, door in doors.items():
        tgId = str(door["telegram_account"])
        sipId = str(door["sip_account"])
        buckets.setdefault((tgId, sipId), []).append(str(doorId))

    out: list[tuple[str, Config]] = []
    for (tgId, sipId), doorIds in sorted(buckets.items()):
        tgRaw = tgAccounts[tgId]
        sipRaw = sipAccounts[sipId]
        runtimeId = f"{tgId}-{sipId}"
        sessionDir = Path(str(tgRaw["session_base_dir"])) / sipId
        # Prefer paths relative to repo when running in Docker with mounted tree.
        if not sessionDir.is_absolute():
            sessionDir = Path("/app") / sessionDir
        sessionDir.mkdir(parents=True, exist_ok=True)

        rtp = sipRaw.get("rtp_port_range") or [4000, 4100]
        sip = SipConfig(
            username=str(sipRaw["username"]),
            password=str(sipRaw["password"]),
            domain=str(sipRaw["domain"]),
            registrar=str(sipRaw["registrar"]),
            bind_address=str(sipRaw.get("bind_address", "127.0.0.1")),
            transport=str(sipRaw.get("transport", "udp")),
            local_port=int(sipRaw["local_port"]),
            rtp_port_range=(int(rtp[0]), int(rtp[1])),
            codec_priorities=dict(
                sipRaw.get("codec_priorities")
                or {
                    "PCMA/8000": 200,
                    "PCMU/8000": 180,
                    "opus/48000": 0,
                }
            ),
        )
        tg = TelegramConfig(
            api_id=int(tgRaw["api_id"]),
            api_hash=str(tgRaw["api_hash"]),
            forward_user_id=0,
            session_name="gateway",
            session_dir=sessionDir,
            call_protocol=dict(
                (raw.get("tg2sip") or {}).get("call_protocol")
                or _DEFAULT_CALL_PROTOCOL
            ),
            inbound_routes={},
        )
        bridge = BridgeConfig(
            sip_sample_rate=8000,
            tg_sample_rate=48000,
            frame_ms=20,
            jitter_ms=60,
        )
        behaviour = BehaviourConfig(
            reject_if_busy=True,
            hangup_on_tg_decline=True,
            caller_id_in_tg_message=True,
        )
        # Per-call RTSP comes from SIP headers; no static video source required.
        video = VideoConfig(
            enabled=False,
            source_url="",
            source_cmd="",
            source_user="",
            source_pass="",
            input_args="",
            width=640,
            height=480,
            fps=15,
            h264=True,
        )
        cfg = Config(
            sip=sip,
            telegram=tg,
            bridge=bridge,
            behaviour=behaviour,
            video=video,
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )
        log.info(
            "runtime %s doors=%s session=%s sip=%s@%s:%s",
            runtimeId,
            ",".join(doorIds),
            sessionDir,
            sip.username,
            sip.domain,
            sip.local_port,
        )
        out.append((runtimeId, cfg))
    if not out:
        raise ValueError("Door2TG config has no doors → no tg2sip runtimes")
    return out
