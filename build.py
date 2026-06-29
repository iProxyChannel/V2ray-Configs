import asyncio
import base64
import json
import re
import os
import time
import aiohttp

# تنظیمات از طریق محیط گیت‌هاب
SUB_LINKS = os.getenv("SUB_LINKS", "").split(",") 

def get_flag_emoji(country_code):
    if not country_code:
        return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

# ۱. استخراج IP و پورت
def parse_config(link):
    link = link.strip()
    try:
        if link.startswith("vmess://"):
            decoded = base64.b64decode(link[8:].split('?')[0] + "==").decode('utf-8', errors='ignore')
            config = json.loads(decoded)
            return config.get('add'), int(config.get('port')), link
        elif link.startswith(("vless://", "trojan://", "ss://")):
            match = re.search(r'@([^:]+):(\d+)', link)
            if match:
                return match.group(1), int(match.group(2)), link
    except Exception:
        pass
    return None, None, None

# ۲. تغییر ریمارک کانفیگ
def modify_remark(link, flag):
    new_remark = f"{flag} t.me/iProxyChannel"
    if link.startswith("vmess://"):
        try:
            decoded = base64.b64decode(link[8:].split('?')[0] + "==").decode('utf-8', errors='ignore')
            config = json.loads(decoded)
            config['ps'] = new_remark
            new_json = json.dumps(config)
            return "vmess://" + base64.b64encode(new_json.encode('utf-8')).decode('utf-8')
        except:
            return link
    elif link.startswith(("vless://", "trojan://", "ss://")):
        base_link = link.split("#")[0]
        return f"{base_link}#{new_remark}"
    return link

# ۳. استخراج دسته‌جمعی لوکیشن‌ها (Batch API) برای جلوگیری از بلاک شدن
async def get_flags_batch(session, hosts):
    url = "http://ip-api.com/batch"
    payload = [{"query": host} for host in hosts]
    flags_map = {}
    try:
        async with session.post(url, json=payload, timeout=15) as resp:
            if resp.status == 200:
                results = await resp.json()
                for item in results:
                    host = item.get("query")
                    cc = item.get("countryCode")
                    flags_map[host] = get_flag_emoji(cc)
    except Exception as e:
        print(f"Error fetching batch locations: {e}")
    return flags_map

# ۴. تست پینگ TCP
async def check_server(host, port, link, semaphore):
    async with semaphore:
        start_time = time.time()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=2.5
            )
            writer.close()
            await writer.wait_closed()
            return {"link": link, "host": host, "latency": int((time.time() - start_time) * 1000), "success": True}
        except:
            return {"link": link, "host": host, "latency": 9999, "success": False}

# ۵. دانلود سابسکریپشن‌ها
async def fetch_configs():
    raw_links = []
    async with aiohttp.ClientSession() as session:
        for url in SUB_LINKS:
            if not url.strip(): continue
            try:
                async with session.get(url.strip(), timeout=10) as response:
                    if response.status == 200:
                        text = await response.text()
                        try:
                            text = base64.b64decode(text + "==").decode('utf-8', errors='ignore')
                        except:
                            pass
                        raw_links.extend(text.splitlines())
            except Exception as e:
                print(f"Error fetching {url}: {e}")
    return list(set(raw_links))

async def main():
    print("Fetching raw configs...")
    links = await fetch_configs()
    
    seen_servers = set()
    unique_servers = []
    for link in links:
        host, port, clean_link = parse_config(link)
        if host and port:
            server_key = f"{host}:{port}"
            if server_key not in seen_servers:
                seen_servers.add(server_key)
                unique_servers.append((host, port, clean_link))
                
    print(f"Deduplicated to {len(unique_servers)} unique servers. Scanning...")

    semaphore = asyncio.Semaphore(80)
    tasks = [check_server(h, p, l, semaphore) for h, p, l in unique_servers]
    results = await asyncio.gather(*tasks)
    
    healthy_servers = [r for r in results if r["success"]]
    healthy_servers.sort(key=lambda x: x["latency"])
    
    # انتخاب حداکثر ۵۰۰ کانفیگ برتر
    top_500 = healthy_servers[:500]
    print(f"Scan finished. Processing top {len(top_500)} configurations...")
    
    if top_500:
        # استخراج لیست هاست‌ها برای گرفتن لوکیشن دسته‌جمعی
        hosts_to_query = list(set([srv["host"] for srv in top_500]))
        
        async with aiohttp.ClientSession() as session:
            flags_map = await get_flags_batch(session, hosts_to_query)
            
            final_configs = []
            for srv in top_500:
                flag = flags_map.get(srv["host"], "🌐")
                processed_link = modify_remark(srv["link"], flag)
                final_configs.append(processed_link)
        
        # ذخیره خروجی متنی
        plain_content = "\n".join(final_configs)
        with open("sub_plain.txt", "w", encoding="utf-8") as f:
            f.write(plain_content)
            
        # ذخیره خروجی بیس۶۴
        base64_content = base64.b64encode(plain_content.encode("utf-8")).decode("utf-8")
        with open("sub_base64.txt", "w", encoding="utf-8") as f:
            f.write(base64_content)
            
        print("Successfully updated sub_plain.txt and sub_base64.txt files!")
    else:
        print("No healthy servers found.")

if __name__ == "__main__":
    asyncio.run(main())
