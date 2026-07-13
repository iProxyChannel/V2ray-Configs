import asyncio
import base64
import json
import logging
import re
import os
import time

import aiohttp

# ---------------------------------------------------------------------------
# تنظیمات
# ---------------------------------------------------------------------------
SUB_LINKS = [u.strip() for u in os.getenv("SUB_LINKS", "").split(",") if u.strip()]

FETCH_TIMEOUT = 10          # ثانیه، برای دانلود هر ساب‌لینک
FETCH_RETRIES = 3           # تعداد تلاش مجدد برای هر ساب‌لینک
FETCH_RETRY_DELAY = 2       # فاصله بین تلاش‌ها (ثانیه)

TCP_TIMEOUT = 2.5           # ثانیه، برای هر تست اتصال TCP
TCP_ATTEMPTS = 2            # تعداد تست تکراری برای هر سرور (میانگین گرفته می‌شود)
CONCURRENCY = 80            # حداکثر تعداد تست هم‌زمان

TOP_N = 500                 # حداکثر تعداد کانفیگ نهایی

IPAPI_URL = "http://ip-api.com/batch"
IPAPI_BATCH_SIZE = 100       # سقف واقعی ip-api.com برای هر batch
IPAPI_SLEEP_BETWEEN = 4      # ثانیه، برای رعایت محدودیت ۱۵ درخواست/دقیقه

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build")


def b64_pad(s: str) -> str:
    """پدینگ صحیح base64 (نه همیشه '==' ثابت)."""
    return s + "=" * (-len(s) % 4)


def get_flag_emoji(country_code):
    if not country_code:
        return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())


# ---------------------------------------------------------------------------
# ۱. استخراج IP و پورت
# ---------------------------------------------------------------------------
def parse_config(link):
    link = link.strip()
    if not link:
        return None, None, None
    try:
        if link.startswith("vmess://"):
            raw = link[8:].split("?")[0]
            decoded = base64.b64decode(b64_pad(raw)).decode("utf-8", errors="ignore")
            config = json.loads(decoded)
            port = config.get("port")
            if config.get("add") and port:
                return config["add"], int(port), link
        elif link.startswith(("vless://", "trojan://", "ss://")):
            match = re.search(r"@([^:/?#]+):(\d+)", link)
            if match:
                return match.group(1), int(match.group(2)), link
    except Exception as e:
        log.debug(f"parse_config failed for link starting '{link[:15]}...': {e}")
    return None, None, None


# ---------------------------------------------------------------------------
# ۲. تغییر ریمارک کانفیگ
# ---------------------------------------------------------------------------
def modify_remark(link, flag):
    new_remark = f"{flag} t.me/iProxyChannel"
    if link.startswith("vmess://"):
        try:
            raw = link[8:].split("?")[0]
            decoded = base64.b64decode(b64_pad(raw)).decode("utf-8", errors="ignore")
            config = json.loads(decoded)
            config["ps"] = new_remark
            new_json = json.dumps(config)
            return "vmess://" + base64.b64encode(new_json.encode("utf-8")).decode("utf-8")
        except Exception as e:
            log.debug(f"modify_remark (vmess) failed: {e}")
            return link
    elif link.startswith(("vless://", "trojan://", "ss://")):
        base_link = link.split("#")[0]
        return f"{base_link}#{new_remark}"
    return link


# ---------------------------------------------------------------------------
# ۳. استخراج دسته‌جمعی لوکیشن‌ها (Batch API) با رعایت سقف و نرخ درخواست
# ---------------------------------------------------------------------------
async def get_flags_batch(session, hosts):
    flags_map = {}
    chunks = [hosts[i:i + IPAPI_BATCH_SIZE] for i in range(0, len(hosts), IPAPI_BATCH_SIZE)]

    for idx, chunk in enumerate(chunks):
        payload = [{"query": host} for host in chunk]
        try:
            async with session.post(IPAPI_URL, json=payload, timeout=15) as resp:
                if resp.status == 200:
                    results = await resp.json()
                    for item in results:
                        host = item.get("query")
                        cc = item.get("countryCode")
                        flags_map[host] = get_flag_emoji(cc)
                else:
                    log.warning(f"ip-api batch {idx + 1}/{len(chunks)} returned status {resp.status}")
        except Exception as e:
            log.warning(f"Error fetching batch {idx + 1}/{len(chunks)} locations: {e}")

        # رعایت محدودیت نرخ درخواست ip-api.com (رایگان: ۱۵ درخواست در دقیقه)
        if idx < len(chunks) - 1:
            await asyncio.sleep(IPAPI_SLEEP_BETWEEN)

    return flags_map


# ---------------------------------------------------------------------------
# ۴. تست پینگ TCP (میانگین چند تلاش برای پایداری بیشتر)
# ---------------------------------------------------------------------------
async def check_server(host, port, link, semaphore):
    async with semaphore:
        latencies = []
        for _ in range(TCP_ATTEMPTS):
            start_time = time.time()
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=TCP_TIMEOUT
                )
                writer.close()
                await writer.wait_closed()
                latencies.append((time.time() - start_time) * 1000)
            except Exception:
                pass

        if not latencies:
            return {"link": link, "host": host, "latency": 9999, "success": False}

        avg_latency = int(sum(latencies) / len(latencies))
        return {"link": link, "host": host, "latency": avg_latency, "success": True}


# ---------------------------------------------------------------------------
# ۵. دانلود سابسکریپشن‌ها (با تلاش مجدد)
# ---------------------------------------------------------------------------
async def fetch_one(session, url):
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            async with session.get(url, timeout=FETCH_TIMEOUT) as response:
                if response.status == 200:
                    text = await response.text()
                    try:
                        text = base64.b64decode(b64_pad(text.strip())).decode("utf-8", errors="ignore")
                    except Exception:
                        pass  # ممکن است از قبل plain text باشد
                    return text.splitlines()
                else:
                    log.warning(f"{url} returned status {response.status} (attempt {attempt}/{FETCH_RETRIES})")
        except Exception as e:
            log.warning(f"Error fetching {url} (attempt {attempt}/{FETCH_RETRIES}): {e}")

        if attempt < FETCH_RETRIES:
            await asyncio.sleep(FETCH_RETRY_DELAY)

    log.error(f"Giving up on {url} after {FETCH_RETRIES} attempts")
    return []


async def fetch_configs():
    if not SUB_LINKS:
        log.error("SUB_LINKS env var is empty — nothing to fetch.")
        return []

    raw_links = []
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[fetch_one(session, url) for url in SUB_LINKS])
        for lines in results:
            raw_links.extend(lines)

    return list(set(raw_links))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
async def main():
    log.info("Fetching raw configs...")
    links = await fetch_configs()
    log.info(f"Fetched {len(links)} raw lines.")

    seen_servers = set()
    unique_servers = []
    parse_failures = 0

    for link in links:
        host, port, clean_link = parse_config(link)
        if host and port:
            server_key = f"{host}:{port}"
            if server_key not in seen_servers:
                seen_servers.add(server_key)
                unique_servers.append((host, port, clean_link))
        elif link.strip():
            parse_failures += 1

    log.info(f"Deduplicated to {len(unique_servers)} unique servers "
              f"({parse_failures} lines failed to parse). Scanning...")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [check_server(h, p, l, semaphore) for h, p, l in unique_servers]
    results = await asyncio.gather(*tasks)

    healthy_servers = [r for r in results if r["success"]]
    healthy_servers.sort(key=lambda x: x["latency"])
    log.info(f"{len(healthy_servers)}/{len(unique_servers)} servers responded successfully.")

    top_servers = healthy_servers[:TOP_N]
    log.info(f"Processing top {len(top_servers)} configurations...")

    if not top_servers:
        log.warning("No healthy servers found. Existing output files were left untouched.")
        return

    hosts_to_query = list({srv["host"] for srv in top_servers})
    async with aiohttp.ClientSession() as session:
        flags_map = await get_flags_batch(session, hosts_to_query)

    final_configs = []
    for srv in top_servers:
        flag = flags_map.get(srv["host"], "🌐")
        processed_link = modify_remark(srv["link"], flag)
        final_configs.append(processed_link)

    plain_content = "\n".join(final_configs)
    with open("sub_plain.txt", "w", encoding="utf-8") as f:
        f.write(plain_content)

    base64_content = base64.b64encode(plain_content.encode("utf-8")).decode("utf-8")
    with open("sub_base64.txt", "w", encoding="utf-8") as f:
        f.write(base64_content)

    log.info("Successfully updated sub_plain.txt and sub_base64.txt files!")


if __name__ == "__main__":
    asyncio.run(main())