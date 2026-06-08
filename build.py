import os
import base64

# نام یا برندی که می‌خواهی انتهای تمام کانفیگ‌ها قرار بگیرد
BRAND_TAG = "t.me/iProxyChannel"

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
    new_tag = f"{protocol.upper()}_{index} {BRAND_TAG}"
    return f"{config_part}#{new_tag}"

def main():
    all_configs = []
    src_dir = "src"
    
    # اگر پوشه src وجود نداشت، آن را بسازد
    if not os.path.exists(src_dir):
        os.makedirs(src_dir)
        print("Please put your raw configs inside 'src' folder.")
        return

    # خواندن فایل‌ها از پوشه src
    for filename in os.listdir(src_dir):
        if filename.endswith(".txt"):
            protocol = filename.replace(".txt", "")
            file_path = os.path.join(src_dir, filename)
            
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            idx = 1
            for line in lines:
                cleaned = clean_and_tag(line, idx, protocol)
                if cleaned:
                    all_configs.append(cleaned)
                    idx += 1

    if not all_configs:
        print("No configs found to process.")
        return

    # ۱. ذخیره نسخه متن خام (Plain Text)
    mixed_text = "\n".join(all_configs)
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
