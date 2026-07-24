"""
اسکن گروه‌ها/کانال‌های تلگرام برای کانفیگ‌های پروکسی،
تست زنده بودن و تاخیر، اعمال برندینگ (پرچم کشور + آیدی)
و تولید فایل سابسکریپشن با ۲۰۰ کانفیگ برتر.

پیش‌نیازها (GitHub Secrets):
    TG_API_ID       - از my.telegram.org
    TG_API_HASH     - از my.telegram.org
    TG_SESSION      - خروجی generate_session.py
    TARGET_CHANNEL  - آیدی کانال جهت برندینگ (مثلاً @iProxyChannel)

فایل‌های ورودی:
    sources.txt     - لیست کانال‌ها/گروه‌های منبع
    state.json      - حفظ وضعیت بین اجراها

فایل‌های خروجی:
    sub.txt         - خروجی متنی ساده (Plain Text)
    sub_b64.txt     - خروجی استاندار Base64 برای کلاینت‌ها
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import socket
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, quote

from telethon.sync import TelegramClient
from telethon.sessions import StringSession
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("generate_sub")

STATE_FILE = Path("state.json")
SOURCES_FILE = Path("sources.txt")
SUB_FILE = Path("sub.txt")
SUB_B64_FILE = Path("sub_b64.txt")

CONFIG_PATTERN = re.compile(
    r"(?:vmess|vless|trojan|ss|ssr|hysteria|hysteria2|hy2|tuic)://[^\s`\"'<>]+",
    re.IGNORECASE,
)

LOOKBACK_MESSAGES = int(os.environ.get("LOOKBACK_MESSAGES", "300"))

TEST_POOL_SIZE = int(os.environ.get("TEST_POOL_SIZE", "1000"))
TEST_CONCURRENCY = int(os.environ.get("TEST_CONCURRENCY", "50"))
TEST_TIMEOUT = float(os.environ.get("TEST_TIMEOUT", "3.0"))
TEST_ATTEMPTS = int(os.environ.get("TEST_ATTEMPTS", "2"))
TOP_N = int(os.environ.get("TOP_N", "200"))

CHANNEL_LABEL_OVERRIDE = os.environ.get("CHANNEL_LABEL", "").strip()


# ---------- state ----------

def load_state() -> dict:
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    else:
        state = {}
    state.setdefault("last_ids", {})
    state.setdefault("seen_hashes", [])
    state.setdefault("host_geo", {})  # host -> {"country_code": "US", "is_hosting": bool}
    return state


def save_state(state: dict) -> None:
    state["seen_hashes"] = state["seen_hashes"][-15000:]
    if len(state["host_geo"]) > 15000:
        state["host_geo"] = dict(list(state["host_geo"].items())[-15000:])
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def config_hash(config: str) -> str:
    return hashlib.sha256(config.strip().encode("utf-8")).hexdigest()


def load_sources() -> list[str]:
    if not SOURCES_FILE.exists():
        log.error("فایل sources.txt پیدا نشد.")
        sys.exit(1)
    return [
        line.strip()
        for line in SOURCES_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def compute_channel_label(target_channel: str) -> str:
    if CHANNEL_LABEL_OVERRIDE:
        return CHANNEL_LABEL_OVERRIDE
    tc = target_channel.strip()
    if tc.startswith("@"):
        return f"t.me/{tc[1:]}"
    if tc.lstrip("-").isdigit():
        return tc
    return f"t.me/{tc}"


# ---------- اسکن منابع ----------

async def scan_sources(client: TelegramClient, sources: list[str], state: dict) -> list[str]:
    seen_hashes = set(state["seen_hashes"])
    per_source_new: dict[str, list[str]] = {}

    for source in sources:
        try:
            entity = await client.get_entity(source)
        except Exception as e:
            log.warning("دسترسی به %s ممکن نشد: %s", source, e)
            continue

        last_id = state["last_ids"].get(str(source), 0)
        max_id_seen = last_id
        found: list[str] = []

        async for message in client.iter_messages(entity, limit=LOOKBACK_MESSAGES, min_id=last_id):
            max_id_seen = max(max_id_seen, message.id)
            if not message.text:
                continue
            for match in CONFIG_PATTERN.findall(message.text):
                h = config_hash(match)
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)
                found.append(match)

        state["last_ids"][str(source)] = max_id_seen
        if found:
            per_source_new[source] = found
        log.info("منبع %s: %d کانفیگ جدید پیدا شد.", source, len(found))

    state["seen_hashes"] = list(seen_hashes)

    # چیدمان چرخشی (Round-Robin) بین منابع برای حفظ تنوع
    interleaved: list[str] = []
    lists = [lst for lst in per_source_new.values() if lst]
    idx = 0
    while lists:
        for lst in lists:
            if idx < len(lst):
                interleaved.append(lst[idx])
        idx += 1
        lists = [lst for lst in lists if idx < len(lst)]

    return interleaved


# ---------- استخراج host/port ----------

def parse_host_port(raw: str) -> tuple[str, int] | None:
    try:
        scheme = raw.split("://", 1)[0].lower()
        if scheme == "vmess":
            b64 = raw.split("://", 1)[1]
            b64 += "=" * (-len(b64) % 4)
            data = json.loads(base64.b64decode(b64).decode("utf-8", errors="ignore"))
            host = data.get("add")
            port = int(data.get("port"))
            if host and port:
                return host, port
            return None

        parsed = urlsplit(raw)
        if parsed.hostname and parsed.port:
            return parsed.hostname, int(parsed.port)

        if scheme == "ss":
            body = raw.split("://", 1)[1].split("#", 1)[0]
            if "@" not in body:
                body += "=" * (-len(body) % 4)
                decoded = base64.b64decode(body).decode("utf-8", errors="ignore")
                if "@" in decoded:
                    hostport = decoded.split("@", 1)[1]
                    host, port = hostport.split(":", 1)
                    return host, int(re.sub(r"\D", "", port))
        return None
    except Exception:
        return None


# ---------- Geolocation با ip-api ----------

def flag_emoji(country_code: str | None) -> str:
    if not country_code or len(country_code) != 2 or not country_code.isalpha():
        return "🏳️"
    return "".join(chr(0x1F1E6 + ord(c.upper()) - ord("A")) for c in country_code)


def resolve_ip(host: str) -> str | None:
    try:
        socket.inet_aton(host)
        return host
    except OSError:
        pass
    try:
        return socket.gethostbyname(host)
    except Exception:
        return None


def resolve_missing_hosts(hosts: set[str], geo_cache: dict) -> None:
    missing = [h for h in hosts if h not in geo_cache]
    if not missing:
        return

    query_for_host: dict[str, str] = {}
    for h in missing:
        ip = resolve_ip(h)
        query_for_host[h] = ip if ip else h

    queries = list(set(query_for_host.values()))
    query_result: dict[str, dict] = {}

    for i in range(0, len(queries), 100):
        chunk = queries[i : i + 100]
        payload = [{"query": q, "fields": "status,countryCode,hosting,query"} for q in chunk]
        try:
            resp = requests.post("http://ip-api.com/batch", json=payload, timeout=20)
            resp.raise_for_status()
            for item in resp.json():
                q = item.get("query")
                if item.get("status") == "success":
                    query_result[q] = {
                        "country_code": item.get("countryCode", ""),
                        "is_hosting": bool(item.get("hosting", False)),
                    }
        except Exception as e:
            log.warning("خطا در geolocation دسته %d: %s", i, e)

    for h in missing:
        q = query_for_host[h]
        geo_cache[h] = query_result.get(q, {"country_code": "", "is_hosting": False})


# ---------- برندینگ ----------

def apply_branding(cfg: str, flag: str, channel_label: str, index: int) -> str:
    label_text = f"{flag} {channel_label} | {index:03d}"
    scheme = cfg.split("://", 1)[0].lower()

    if scheme == "vmess":
        try:
            b64 = cfg.split("://", 1)[1]
            b64_padded = b64 + "=" * (-len(b64) % 4)
            data = json.loads(base64.b64decode(b64_padded).decode("utf-8", errors="ignore"))
            data["ps"] = label_text
            new_b64 = base64.b64encode(json.dumps(data, ensure_ascii=False).encode("utf-8")).decode("utf-8")
            return f"vmess://{new_b64}"
        except Exception:
            return cfg

    base = cfg.split("#", 1)[0]
    return f"{base}#{quote(label_text)}"


# ---------- تست TCP Ping ----------

async def tcp_ping(host: str, port: int, attempts: int, timeout: float) -> float | None:
    latencies = []
    for _ in range(attempts):
        start = time.monotonic()
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
            latencies.append((time.monotonic() - start) * 1000)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
        except Exception:
            continue
    if not latencies:
        return None
    return sum(latencies) / len(latencies)


async def test_configs(configs: list[str]) -> list[dict]:
    sem = asyncio.Semaphore(TEST_CONCURRENCY)
    results: list[dict] = []

    async def worker(cfg: str):
        parsed = parse_host_port(cfg)
        if not parsed:
            return
        host, port = parsed
        async with sem:
            latency = await tcp_ping(host, port, TEST_ATTEMPTS, TEST_TIMEOUT)
        if latency is not None:
            proto = cfg.split("://", 1)[0].lower()
            results.append({"config": cfg, "host": host, "port": port, "latency_ms": latency, "protocol": proto})

    await asyncio.gather(*(worker(c) for c in configs))
    return results


# ---------- تولید سابسکریپشن ----------

async def build_subscription(candidates: list[str], geo_cache: dict, target_channel: str) -> None:
    if not candidates:
        log.info("کانفیگ جدیدی برای تست یافت نشد.")
        return

    pool = candidates[:TEST_POOL_SIZE]
    log.info("در حال تست %d کانفیگ...", len(pool))
    tested = await test_configs(pool)

    if not tested:
        log.info("هیچ کانفیگ زنده‌ای یافت نشد.")
        return

    for r in tested:
        info = geo_cache.get(r["host"], {"country_code": "", "is_hosting": False})
        r["is_hosting"] = info["is_hosting"]

    # سورت: ۱. اولویت با غیر دیتاسنتری (is_hosting=False)، ۲. کمترین تاخیر (latency_ms)
    tested.sort(key=lambda r: (r["is_hosting"], r["latency_ms"]))
    top = tested[:TOP_N]

    channel_label = compute_channel_label(target_channel)
    final_configs = []

    for idx, r in enumerate(top, 1):
        geo = geo_cache.get(r["host"], {"country_code": "", "is_hosting": False})
        flag = flag_emoji(geo["country_code"])
        branded = apply_branding(r["config"], flag, channel_label, idx)
        final_configs.append(branded)

    # ذخیره متنی ساده
    plain_content = "\n".join(final_configs)
    SUB_FILE.write_text(plain_content, encoding="utf-8")

    # ذخیره خروجی Base64
    b64_content = base64.b64encode(plain_content.encode("utf-8")).decode("utf-8")
    SUB_B64_FILE.write_text(b64_content, encoding="utf-8")

    log.info("تعداد %d کانفیگ برتر با موفقیت در فایل‌های sub.txt و sub_b64.txt ذخیره شد.", len(final_configs))


# ---------- main ----------

async def main() -> None:
    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    session_str = os.environ["TG_SESSION"]
    target_channel = os.environ.get("TARGET_CHANNEL", "@iProxyChannel")

    state = load_state()
    sources = load_sources()

    async with TelegramClient(StringSession(session_str), api_id, api_hash) as client:
        new_configs = await scan_sources(client, sources, state)

    log.info("تعداد کل کانفیگ‌های جدید استخراج شده: %d", len(new_configs))

    hosts = set()
    for cfg in new_configs[:TEST_POOL_SIZE]:
        parsed = parse_host_port(cfg)
        if parsed:
            hosts.add(parsed[0])
    resolve_missing_hosts(hosts, state["host_geo"])

    await build_subscription(new_configs, state["host_geo"], target_channel)

    save_state(state)


if __name__ == "__main__":
    asyncio.run(main())
