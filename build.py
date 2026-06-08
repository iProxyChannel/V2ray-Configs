import os
import base64

# نام یا برندی که می‌خواهی انتهای تمام کانفیگ‌ها قرار بگیرد
BRAND_TAG = "t.me/iProxyChannel"

def detect_protocol(line):
    """تشخیص نوع پروتکل از روی ابتدای خط"""
    if line.startswith("vless://"):
        return "vless"
    elif line.startswith("vmess://"):
        return "vmess"
    elif line.startswith("trojan://"):
        return "trojan"
    elif line.startswith("ss://"):
        return "ss"
    return "unknown"

def clean_and_tag(line, index, protocol):
    line = line.strip()
    if not line:
        return None
    
    # جدا کردن کانفیگ از تگ قدیمی (اگر وجود داشته باشد)
    if "#" in line:
        config_part, _ = line.rsplit("#", 1)
    else:
        config_part = line
        
    # ساختن نام جدید استاندارد: Protocol_Index | Brand
    new_tag = f"{protocol.upper()} {index} {BRAND_TAG}"
    return f"{config_part}#{new_tag}"

def main():
    all_processed_configs = []
    input_file = "all_configs.txt"
    
    # اگر فایل وجود نداشت، یک فایل خالی بسازد
    if not os.path.exists(input_file):
        with open(input_file, "w", encoding="utf-8") as f:
            f.write("")
        print(f"Created empty '{input_file}'. Please put your configs inside it.")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # شمارشگر جداگانه برای هر پروتکل جهت تمیزی کار
    counters = {"vless": 1, "vmess": 1, "trojan": 1, "ss": 1, "unknown": 1}
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        protocol = detect_protocol(line)
        idx = counters[protocol]
        
        cleaned = clean_and_tag(line, idx, protocol)
        if cleaned:
            all_processed_configs.append(cleaned)
            counters[protocol] += 1

    if not all_processed_configs:
        print("No configs found to process.")
        return

    # ۱. ذخیره نسخه متن خام (Plain Text)
    mixed_text = "\n".join(all_processed_configs)
    with open("sub_plain.txt", "w", encoding="utf-8") as f:
        f.write(mixed_text)
    print("Created: sub_plain.txt")

    # ۲. ذخیره نسخه کدگذاری شده (Base64)
    b64_bytes = base64.b64encode(mixed_text.encode("utf-8"))
    b64_string = b64_bytes.decode("utf-8")
    with open("sub_base64.txt", "w", encoding="utf-8") as f:
        f.write(b64_string)
    print("Created: sub_base64.txt")

if __name__ == "__main__":
    main()
