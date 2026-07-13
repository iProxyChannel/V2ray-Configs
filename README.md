# V2Ray Configs

جمع‌آوری، تست و رتبه‌بندی خودکار کانفیگ‌های V2Ray (VMess, VLESS, Trojan, Shadowsocks) از چند سابسکریپشن عمومی — به‌صورت خودکار هر ۱۲ ساعت با GitHub Actions به‌روزرسانی می‌شود.

📡 کانال تلگرام: [@iProxyChannel](https://t.me/iProxyChannel)

---

## 🚀 لینک‌های سابسکریپشن

این لینک‌ها را در کلاینت V2Ray خود (v2rayN, v2rayNG, NekoBox, Hiddify, Streisand و ...) به‌عنوان Subscription اضافه کنید تا همیشه به آخرین و سریع‌ترین کانفیگ‌ها دسترسی داشته باشید:

**Plain (متنی):**
```
https://raw.githubusercontent.com/iProxyChannel/V2ray-Configs/main/sub_plain.txt
```

**Base64:**
```
https://raw.githubusercontent.com/iProxyChannel/V2ray-Configs/main/sub_base64.txt
```

> اکثر کلاینت‌ها (مثل v2rayN و v2rayNG) از هر دو فرمت پشتیبانی می‌کنند؛ اگر یکی کار نکرد، دیگری را امتحان کنید.

---

## ⚙️ نحوه عملکرد

اسکریپت `build.py` هر ۱۲ ساعت به‌صورت خودکار توسط GitHub Actions اجرا می‌شود و این مراحل را انجام می‌دهد:

1. **دانلود** — کانفیگ‌ها از لیست سابسکریپشن‌های تعریف‌شده (از طریق Secret) دریافت می‌شوند.
2. **حذف تکراری‌ها** — کانفیگ‌های با آی‌پی و پورت یکسان فیلتر می‌شوند.
3. **تست اتصال** — برای هر سرور یک تست TCP انجام می‌شود و تأخیر (latency) اندازه‌گیری می‌شود.
4. **مرتب‌سازی** — سرورهای سالم بر اساس کمترین تأخیر مرتب می‌شوند و ۵۰۰ مورد برتر انتخاب می‌شوند.
5. **افزودن پرچم کشور** — موقعیت جغرافیایی هر سرور مشخص و به نام کانفیگ اضافه می‌شود.
6. **خروجی** — فایل‌های `sub_plain.txt` و `sub_base64.txt` بازنویسی و commit می‌شوند.

---

## 📁 ساختار پروژه

```
V2ray-Configs/
├── .github/workflows/
│   └── auto_scan.yml     # زمان‌بندی و اجرای خودکار
├── build.py               # اسکریپت اصلی جمع‌آوری و تست
├── requirements.txt        # وابستگی‌های پایتون
├── sub_plain.txt           # خروجی نهایی (متنی)
├── sub_base64.txt          # خروجی نهایی (Base64)
└── README.md
```

---

## 🛠 اجرای محلی (اختیاری)

```bash
git clone https://github.com/iProxyChannel/V2ray-Configs.git
cd V2ray-Configs
pip install -r requirements.txt

export SUB_LINKS="https://sub1.example.com,https://sub2.example.com"
python build.py
```

---

## ⚠️ سلب مسئولیت

این پروژه صرفاً کانفیگ‌های عمومی و در دسترس را جمع‌آوری، تست و مرتب می‌کند و هیچ سروری را میزبانی نمی‌کند. کیفیت، پایداری و امنیت هر سرور مسئولیت منبع اصلی آن است. استفاده از این کانفیگ‌ها به مسئولیت خود کاربر و مطابق با قوانین محل سکونت اوست.

## 📄 لایسنس

MIT
