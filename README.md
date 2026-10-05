# Water_Accounting_dashboard_new

داشبورد هوشمند حسابداری منابع و مصارف آب (Streamlit) برای محدوده مطالعاتی مشهد - چناران، قابل تعمیم به
حوضه‌ها، شهرستان‌ها و زیرحوضه‌های دیگر از طریق فایل پیکربندی.

توضیحات کامل منطق محاسبات، منابع داده و نحوه افزودن حوضه جدید: [dashboard/README.md](dashboard/README.md)

## داده‌ها
فایل‌های داده در این مخزن نیستند. برای اجرا آنها را کنار پوشه `dashboard` (در ریشه همین مخزن) قرار دهید:

```
Amar_SAD.xlsx            آمار سدها (هر سال آبی یک شیت)
CHAH_MASHAHD.xls         آمار برداشت چاه‌ها
Bilan/*.pdf              سیمای آب (جدول بیلان)
shape/final_boundary_fixed.*   زیرحوضه‌ها
shape/shahrestan.*             شهرستان‌ها
shape/selected_dams.*          نقاط سدها
water_acounting_1Sep25.xlsx    (اختیاری) اکسل نمونه، فقط برای validate_excel.py
```

## اجرا (ویندوز)
روی `dashboard/run_dashboard.bat` دوبار کلیک کنید. بار اول محیط پایتون (`.venv`) ساخته و پکیج‌ها نصب می‌شوند.

یا به‌صورت دستی:
```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r dashboard\requirements.txt
cd dashboard
..\.venv\Scripts\python.exe -m streamlit run app.py
```
