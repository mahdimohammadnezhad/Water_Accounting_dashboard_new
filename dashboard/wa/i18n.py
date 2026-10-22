"""Persian / English text. Data stays in Persian internally; labels are translated only for display."""
import re

from .text import norm

LANGS = {"fa": "فارسی", "en": "English"}
FA_DIGITS = str.maketrans("0123456789.,", "۰۱۲۳۴۵۶۷۸۹٫٬")

UI = {
    # page / sidebar
    "page_title": ("داشبورد حسابداری آب", "Water Accounting Dashboard"),
    "settings": ("تنظیمات نمایش", "Display settings"),
    "language": ("زبان / Language", "Language / زبان"),
    "sec_area": ("🗂️ محدوده و سال", "🗂️ Area & year"),
    "basin": ("حوضه / محدوده مطالعاتی", "Basin / study area"),
    "year": ("سال آبی", "Water year"),
    "sec_spatial": ("📍 تقسیمات مکانی", "📍 Spatial units"),
    "county_basis": ("مبنای تعیین شهرستان", "County basis"),
    "county_basis_help": ("ستون شهرستان: همان شهرستانی که در آمار چاه‌ها ثبت شده است. مکانی: شهرستان از روی موقعیت "
                          "چاه روی شیپ‌فایل شهرستان‌ها تعیین می‌شود.",
                          "County column: the county recorded in the well statistics. Spatial: the county polygon "
                          "that contains the well in the county shapefile."),
    "basis_attr": ("ستون شهرستان در آمار", "County column in the statistics"),
    "basis_geo": ("شیپ‌فایل شهرستان‌ها (مکانی)", "County shapefile (spatial)"),
    "sub_basin": ("زیرحوضه", "Sub-basin"),
    "county": ("شهرستان", "County"),
    "all": ("همه", "All"),
    "sec_use": ("💧 کاربری و منبع", "💧 Use & source"),
    "use": ("کاربری", "Use"),
    "source_type": ("نوع منبع", "Source type"),
    "sec_table": ("🧮 جدول", "🧮 Table"),
    "layout": ("چیدمان ستون‌ها", "Column layout"),
    "layout_excel": ("قالب اکسل (DYNMIC)", "Excel template (DYNMIC)"),
    "layout_county": ("همه کاربری‌ها به تفکیک شهرستان", "All uses by county"),
    "layout_sub_basin": ("همه کاربری‌ها به تفکیک زیرحوضه", "All uses by sub-basin"),
    "layout_none": ("فقط به تفکیک کاربری", "By use only"),
    "restrict": ("فقط شهرستان‌های تعریف‌شده برای شرب و صنعت", "Only the counties listed for drinking & industry"),
    "restrict_help": ("در قالب اکسل ستون‌های شرب و صنعت فقط برای شهرستان‌های فهرست‌شده در پیکربندی ساخته می‌شوند؛ با "
                      "برداشتن تیک بقیه شهرستان‌ها هم ستون می‌گیرند.",
                      "In the Excel template, drinking and industry columns exist only for the counties listed in "
                      "the config; untick to give every county a column."),
    "cf": ("قالب‌بندی شرطی (رنگ بر اساس اندازه)", "Conditional formatting (colour by size)"),
    "log": ("مقیاس رنگ لگاریتمی", "Logarithmic colour scale"),
    "log_help": ("با مقیاس لگاریتمی، اعداد کوچک هم رنگ قابل تشخیص می‌گیرند.",
                 "With a log scale small numbers also get a visible colour."),
    "coef_box": ("⚙️ ضرایب برگشت (قابل ویرایش)", "⚙️ Return-flow coefficients (editable)"),
    "coef_caption": ("تغییرات فوراً در همه جداول و نمودارها اعمال می‌شود.", "Changes apply immediately everywhere."),
    "coef": ("ضریب", "coef."),
    "river_share": ("سهم رودخانه", "river share"),
    "reload": ("🔄 خواندن دوباره فایل‌های ورودی", "🔄 Reload input files"),
    "built_at": ("آخرین ساخت داده", "Data last built"),
    "building": ("در حال خواندن فایل‌های ورودی و ساخت داده‌ها (فقط بار اول یا پس از تغییر فایل‌ها) ...",
                 "Reading the input files and building the data (only the first time or after files change) ..."),
    "rebuilding": ("در حال ساخت دوباره داده‌ها ...", "Rebuilding the data ..."),
    "no_config": ("هیچ فایل پیکربندی در پوشه configs پیدا نشد. از «افزودن حوضه جدید» استفاده کنید.",
                  "No config file found in the configs folder. Use 'Add a new basin'."),
    "build_error": ("ساخت داده‌های این حوضه با خطا متوقف شد:", "Building this basin's data failed:"),
    "add_basin": ("➕ افزودن حوضه جدید", "➕ Add a new basin"),
    "add_help": ("مسیر پوشه‌ای را بدهید که فایل اکسل چاه‌ها، فایل اکسل سدها (هر سال یک شیت)، PDFهای سیمای آب و "
                 "شیپ‌فایل‌های زیرحوضه و شهرستان در آن است (زیرپوشه هم مجاز است). فایل‌ها خودکار شناسایی و "
                 "پیکربندی ساخته می‌شود.",
                 "Give the path of a folder holding the well Excel, the dam Excel (one sheet per year), the Simaye "
                 "Ab PDFs and the sub-basin and county shapefiles (sub-folders are fine). Files are detected "
                 "automatically and a config is created."),
    "add_folder": ("پوشه داده‌ها", "Data folder"),
    "add_name": ("نام حوضه", "Basin name"),
    "add_btn": ("بررسی پوشه و ساخت پیکربندی", "Scan folder & create config"),
    "add_done": ("پیکربندی ساخته شد: {path}", "Config created: {path}"),
    "add_fail": ("ساخت پیکربندی ناموفق بود: {err}", "Could not create the config: {err}"),
    # header + cards
    "hero_title": ("داشبورد حسابداری منابع و مصارف آب", "Water Accounting Dashboard — Sources & Uses"),
    "unit_sub": ("واحد: میلیون مترمکعب", "unit: million m³"),
    "chip_year": ("سال آبی {y}", "Water year {y}"),
    "chip_all_sb": ("همه زیرحوضه‌ها", "All sub-basins"),
    "chip_sb": ("زیرحوضه: {x}", "Sub-basins: {x}"),
    "chip_all_ct": ("همه شهرستان‌ها", "All counties"),
    "chip_ct": ("شهرستان: {x}", "Counties: {x}"),
    "chip_attr": ("شهرستان بر اساس آمار", "County from statistics"),
    "chip_geo": ("شهرستان بر اساس شیپ‌فایل", "County from shapefile"),
    "sec_resources": ("منابع آب (سیمای آب)", "Water resources (Simaye Ab)"),
    "sec_uses": ("مصارف و بیلان (جدول زیر)", "Uses & balance (table below)"),
    "renew_total": ("آب تجدیدپذیر کل", "Total renewable water"),
    "renew_surface": ("تجدیدپذیر سطحی (رواناب)", "Renewable surface (runoff)"),
    "renew_ground": ("تجدیدپذیر زیرزمینی (نفوذ)", "Renewable groundwater (recharge)"),
    "nonrenew": ("غیرتجدیدپذیر (کسری مخزن)", "Non-renewable (aquifer deficit)"),
    "note_simaye": ("سیمای آب {y}", "Simaye Ab {y}"),
    "note_area": ("{p}٪ مساحت", "{p}% of area"),
    "note_ds": ("قرینه تغییر ذخیره آبخوان (⁦−ΔS⁩)", "minus aquifer storage change (−ΔS)"),
    "withdrawal": ("برداشت کل", "Total withdrawal"),
    "note_withdrawal": ("سد + چاه + انتقالی + تصفیه‌خانه", "dams + wells + transfers + treatment"),
    "return": ("آب برگشتی", "Return flow"),
    "note_return": ("ضریب برگشت × برداشت", "return coef. × withdrawal"),
    "consumption": ("مصرف (C)", "Consumption (C)"),
    "note_consumption": ("برداشت − برگشت", "withdrawal − return"),
    "balance": ("کنترل بیلان (B)", "Balance check (B)"),
    "note_balance": ("منابع در دسترس − مصرف", "available resources − consumption"),
    "unit_short": ("م.م.م", "MCM"),
    "area_caption": ("شاخص‌های سیمای آب برای کل محدوده گزارش شده‌اند و به نسبت مساحت محدوده انتخابی ({p}) محاسبه شده‌اند.",
                     "Simaye Ab indicators are reported for the whole area and are scaled by the selected area ({p})."),
    # tabs
    "tab_table": ("📋 جدول منابع و مصارف", "📋 Sources & uses table"),
    "tab_charts": ("📊 نمودارها", "📊 Charts"),
    "tab_trend": ("📈 روند سالانه", "📈 Annual trend"),
    "tab_matrix": ("🧩 زیرحوضه × شهرستان", "🧩 Sub-basin × county"),
    "tab_map": ("🗺️ نقشه", "🗺️ Map"),
    "tab_qc": ("🔎 داده‌ها و کنترل کیفیت", "🔎 Data & quality control"),
    "table_note": ("سطرها منابع‌اند و ستون‌ها کاربری × تفکیک × (برداشت | برگشت). برگشتی در سطرهای «بازه رودخانه» و «آبخوان» "
                   "نشان می‌دهد آب برگشتی هر کاربری به کجا رفته است؛ در سطر «مجموع» برگشت کل = ضریب × برداشت است. "
                   "«تصفیه خانه» سهمی از برگشت شرب است و در کنترل بیلان شمرده نمی‌شود. کنترل بیلان = حجم در دسترس سدها، "
                   "آب زیرزمینی و انتقالی − مصارف.",
                   "Rows are sources; columns are use × breakdown × (withdrawal | return). Returns in the river-reach "
                   "and aquifer rows show where each use's return flow goes; in the 'Total' row return = coefficient × "
                   "withdrawal. 'Treatment plant' is a share of the drinking return and is not counted in the balance. "
                   "Balance check = available volume of dams, groundwater and transfers − consumption."),
    "omitted": ("{v} م.م.م برداشت شرب/صنعت شهرستان‌هایی که در قالب اکسل ستون ندارند کنار گذاشته شده است. برای دیدن آن تیک "
                "«فقط شهرستان‌های تعریف‌شده» را بردارید.",
                "{v} MCM of drinking/industry withdrawal of counties without a column in the Excel template is left out. "
                "Untick 'Only the counties listed' to see it."),
    "attr_warning": ("حجم در دسترس آب زیرزمینی به تفکیک شهرستان از روی شیپ‌فایل شهرستان‌ها محاسبه می‌شود؛ برای شهرستان‌هایی "
                     "که در شیپ‌فایل نیستند ({x}) ستون G آب زیرزمینی صفر است.",
                     "Groundwater available volume per county comes from the county shapefile; for counties missing "
                     "from it ({x}) the groundwater G column is zero."),
    "dl_table": ("⬇️ دانلود جدول (Excel)", "⬇️ Download table (Excel)"),
    "dl_csv": ("⬇️ داده جزئی برداشت‌ها (CSV)", "⬇️ Withdrawal details (CSV)"),
    "table_title": ("منابع و مصارف سال آبی {y} — {b}", "Sources and uses, water year {y} — {b}"),
    "no_data": ("برای فیلترهای انتخابی برداشتی ثبت نشده است.", "No withdrawals for the selected filters."),
    "matrix_note": ("سهم هر شهرستان از هر زیرحوضه: مجموع برداشت (منابع و کاربری‌های انتخابی) و مساحت.",
                    "Each county's share of each sub-basin: total withdrawal (selected sources and uses) and area."),
    "matrix_title": ("برداشت سال {y} (م.م.م)", "Withdrawal {y} (MCM)"),
    "area_title": ("مساحت (کیلومترمربع، از شیپ‌فایل‌ها)", "Area (km², from the shapefiles)"),
    "detail_title": ("جزئیات: زیرحوضه × شهرستان × نوع منبع × کاربری", "Details: sub-basin × county × source × use"),
    "dl_detail": ("⬇️ دانلود این جدول (Excel)", "⬇️ Download this table (Excel)"),
    "total": ("جمع", "Total"),
    "basemap": ("نقشه پایه", "Basemap"),
    "map_mode": ("نوع بررسی", "Review mode"),
    "mode_county": ("🏛️ بررسی شهرستانی", "🏛️ County view"),
    "mode_sub_basin": ("💧 بررسی زیرحوضه‌ای", "💧 Sub-basin view"),
    "mode_combined": ("🧩 بررسی ترکیبی", "🧩 Combined view"),
    "map_layers": ("لایه‌ها", "Layers"),
    "lyr_sb": ("زیرحوضه‌ها و محدوده", "Sub-basins / area"),
    "lyr_ct": ("شهرستان‌های محدوده", "Counties of the area"),
    "lyr_ctx_sa": ("سایر محدوده‌های مطالعاتی", "Other study areas"),
    "lyr_ctx_ct": ("سایر شهرستان‌ها", "Other counties"),
    "lyr_wells": ("چاه‌ها", "Wells"),
    "lyr_dams": ("سدها", "Dams"),
    "lg_ctx_sa": ("سایر محدوده‌های مطالعاتی", "Other study areas"),
    "lg_ctx_ct": ("سایر شهرستان‌ها", "Other counties"),
    "hv_study_area": ("محدوده مطالعاتی", "Study area"),
    "map_note": ("نقشه پایه OpenStreetMap و ماهواره‌ای (Esri) به اینترنت نیاز دارند؛ حالت «ساده» بدون اینترنت کار می‌کند. "
                 "«نوع بررسی» لایه‌های مربوط را روشن و بقیه را خاموش می‌کند؛ هر لایه را با دکمه‌های بالای نقشه یا کلیک "
                 "روی نامش در راهنمای نقشه هم می‌توان خاموش/روشن کرد. محدوده‌ها و شهرستان‌های اطراف (تا فاصله "
                 "تعیین‌شده در configs/_regional.yaml) کم‌رنگ نمایش داده می‌شوند و زیرحوضه‌ها/شهرستان‌هایی که در فیلتر "
                 "انتخاب نشده‌اند هم کم‌رنگ‌اند.",
                 "The OpenStreetMap and satellite (Esri) basemaps need internet; 'Plain' works offline. The review mode "
                 "switches the related layers on and the others off; every layer can also be toggled with the buttons "
                 "above the map or by clicking its name in the legend. Neighbouring study areas and counties (within the "
                 "distance set in configs/_regional.yaml) are drawn faintly, as are sub-basins/counties not selected "
                 "in the filters."),
    "qc_simaye": ("جدول بیلان سیمای آب (خوانده‌شده از PDFها)", "Simaye Ab balance table (read from the PDFs)"),
    "qc_dams": ("سدها و موقعیت آنها", "Dams and their location"),
    "qc_info": ("جزئیات ورود داده", "Data import details"),
    "qc_dam_stats": ("آمار سدها", "Dam statistics"),
    "qc_base": ("داده‌های پایه (همه سال‌ها)", "Base data (all years)"),
    "dl_w": ("⬇️ برداشت‌ها (CSV)", "⬇️ Withdrawals (CSV)"),
    "dl_r": ("⬇️ آب برگشتی (CSV)", "⬇️ Return flows (CSV)"),
    "dl_res": ("⬇️ منابع در دسترس (CSV)", "⬇️ Available resources (CSV)"),
    "qc_caption": ("ساخت داده: {t} ({s} ثانیه). آزمون سلامت: python check_basin.py",
                   "Data built: {t} ({s} s). Health check: python check_basin.py"),
    "resources": ("منابع در دسترس", "Available resources"),
    "withdrawal_s": ("برداشت", "Withdrawal"),
    "return_s": ("برگشت", "Return"),
    # uncertainty
    "sec_unc": ("📏 عدم قطعیت", "📏 Uncertainty"),
    "unc_show": ("نمایش باند عدم قطعیت", "Show uncertainty bands"),
    "unc_help": ("بازه‌ها با شبیه‌سازی مونت‌کارلو از خطای فرضی هر ورودی به دست می‌آیند (۵ تا ۹۵ درصد). عدد اصلی همان "
                 "برآورد قطعی است.",
                 "Ranges come from a Monte Carlo propagation of the assumed error of every input (5-95 %). The main "
                 "number is the best estimate."),
    "unc_box": ("⚙️ فرض‌های عدم قطعیت (خطای نسبی ٪، یک انحراف معیار)", "⚙️ Uncertainty assumptions (relative error %, 1σ)"),
    "unc_gw_m": ("چاه کنتوردار", "Metered wells"), "unc_gw_u": ("چاه بدون کنتور", "Unmetered wells"),
    "unc_gw_i": ("چاه غیرمجاز", "Illegal wells"), "unc_gw": ("چاه (نامشخص)", "Wells (unknown)"),
    "unc_dam": ("آمار سدها", "Dam statistics"), "unc_transfer": ("آب انتقالی", "Transfer"),
    "unc_treatment": ("تصفیه‌خانه", "Treatment plant"), "unc_special": ("سایر جداول", "Other tables"),
    "unc_renew_surface": ("تجدیدپذیر سطحی", "Renewable surface"),
    "unc_renew_ground": ("تجدیدپذیر زیرزمینی", "Renewable groundwater"),
    "unc_storage_change": ("تغییر ذخیره آبخوان", "Aquifer storage change"),
    "unc_return_coef": ("ضرایب برگشت", "Return coefficients"),
    "band": ("بازه ۹۰٪: {lo} تا {hi}", "90% range: {lo} – {hi}"),
    "band_short": ("بازه ۹۰٪", "90% range"),
    "table_bands": ("بازه ۹۰٪ عدم قطعیت — برداشت: {w} | برگشت: {r} | مصرف: {c} | منابع در دسترس: {s} | کنترل بیلان: {b}",
                    "90% uncertainty range — withdrawal: {w} | return: {r} | consumption: {c} | resources: {s} | "
                    "balance: {b}"),
    "qc_unc": ("فرض‌های عدم قطعیت", "Uncertainty assumptions"),
    "unc_class": ("ورودی", "Input"), "unc_sd": ("خطای نسبی (٪، ۱σ)", "Relative error (%, 1σ)"),
    "unc_share": ("سهم از برداشت سال", "Share of the year's withdrawal"),
    # scenarios
    "tab_scen": ("🎯 سناریوهای مدیریتی", "🎯 Management scenarios"),
    "scen_title": ("تنظیم سناریو", "Scenario settings"),
    "scen_help": ("هر تغییری فوراً روی نتایج سمت مقابل اعمال می‌شود. وضع موجود = داده‌های همان سال آبی.",
                  "Every change is applied immediately to the results. Baseline = the data of the selected year."),
    "scen_presets": ("سناریوهای آماده", "Presets"),
    "p_reset": ("↺ بازنشانی", "↺ Reset"),
    "p_agri": ("کاهش ۲۰٪ کشاورزی", "Agriculture −20%"),
    "p_illegal": ("بستن چاه‌های غیرمجاز", "Close illegal wells"),
    "p_reuse": ("استفاده مجدد از پساب", "Reuse treated wastewater"),
    "p_drought": ("خشکسالی (−۳۰٪)", "Drought (−30%)"),
    "p_combo": ("بسته مدیریتی ترکیبی", "Combined package"),
    "scen_uses": ("تغییر برداشت هر کاربری (٪)", "Change of each use's withdrawal (%)"),
    "scen_gw": ("تغییر کل برداشت از آب زیرزمینی (٪)", "Change of all groundwater pumping (%)"),
    "scen_illegal": ("بستن چاه‌های غیرمجاز (٪ برداشت آنها)", "Close illegal wells (% of their withdrawal)"),
    "scen_reuse": ("استفاده مجدد از پساب تصفیه‌خانه در کشاورزی به‌جای آب زیرزمینی (٪ خروجی)",
                   "Reuse treatment-plant effluent in agriculture instead of groundwater (% of output)"),
    "scen_transfer": ("تغییر آب انتقالی (میلیون مترمکعب)", "Change of the inter-basin transfer (MCM)"),
    "scen_climate": ("تغییر اقلیم: آب تجدیدپذیر و ورودی سدها (٪)", "Climate: renewable water and dam inflow (%)"),
    "scen_scope": ("محدوده اعمال", "Applies to"),
    "scope_all": ("کل حوضه", "Whole basin"), "scope_selection": ("فقط محدوده انتخابی", "Selected area only"),
    "scen_global": ("اعمال سناریو در همه بخش‌های داشبورد", "Apply the scenario to the whole dashboard"),
    "scen_global_chip": ("🎯 سناریو فعال", "🎯 Scenario on"),
    "scen_none": ("هنوز تغییری تنظیم نشده است؛ یکی از سناریوهای آماده را انتخاب کنید یا مقادیر را تغییر دهید.",
                  "No change set yet; pick a preset or move a control."),
    "base": ("وضع موجود", "Baseline"), "scen": ("سناریو", "Scenario"), "delta": ("تغییر", "Change"),
    "deficit": ("کسری مخزن آبخوان", "Aquifer deficit"),
    "gw_withdrawal": ("برداشت آب زیرزمینی", "Groundwater withdrawal"),
    "ch_scen_use": ("برداشت هر کاربری: وضع موجود و سناریو", "Withdrawal by use: baseline vs scenario"),
    "ch_scen_trend": ("کسری مخزن آبخوان و کنترل بیلان در همه سال‌ها", "Aquifer deficit and balance check, all years"),
    "scen_table": ("اثر سناریو به تفکیک زیرحوضه", "Scenario effect by sub-basin"),
    "scen_note": ("فرض‌ها: کاهش برداشت به همان نسبت برگشت را هم کم می‌کند؛ پساب استفاده‌شده جایگزین برداشت زیرزمینی "
                  "کشاورزی می‌شود؛ کسری مخزن سناریو = کسری مشاهده‌شده + تغییر برداشت زیرزمینی − تغییر برگشت به آبخوان − "
                  "تغییر تغذیه. حجم در دسترس آب زیرزمینی (G) فقط با تغییر اقلیم عوض می‌شود.",
                  "Assumptions: a lower withdrawal also lowers its return flow; reused effluent replaces agricultural "
                  "groundwater pumping; scenario aquifer deficit = observed deficit + change in GW withdrawal − change "
                  "in return to the aquifers − change in recharge. Groundwater availability (G) changes only with "
                  "the climate lever."),
    # charts
    "ch_sankey": ("جریان برداشت: از منبع تا کاربری", "Withdrawal flow: from source to use"),
    "ch_bar": ("برداشت هر کاربری به تفکیک نوع منبع", "Withdrawal of each use by source type"),
    "ch_donut": ("سهم کاربری‌ها از مصرف (C)", "Share of each use in consumption (C)"),
    "ch_donut_center": ("مصرف کل", "total use"),
    "ch_trend_w": ("روند برداشت سالانه به تفکیک کاربری", "Annual withdrawal by use"),
    "ch_trend_b": ("روند منابع، مصارف و کنترل بیلان", "Resources, uses and balance over time"),
    "ch_trend_i": ("آب تجدیدپذیر و غیرتجدیدپذیر (سیمای آب)", "Renewable and non-renewable water (Simaye Ab)"),
    "ch_res_line": ("منابع در دسترس (سد + زیرزمینی + انتقالی)", "Available resources (dams + groundwater + transfers)"),
    "unit_axis": ("میلیون مترمکعب", "million m³"),
    "bm_osm": ("OpenStreetMap", "OpenStreetMap"),
    "bm_satellite": ("تصویر ماهواره‌ای", "Satellite"),
    "bm_plain": ("ساده (بدون اینترنت)", "Plain (offline)"),
    "lg_sb": ("زیرحوضه‌ها", "Sub-basins"),
    "lg_ct": ("مرز شهرستان‌ها", "County borders"),
    "lg_wells": ("چاه‌ها (اندازه = برداشت)", "Wells (size = withdrawal)"),
    "lg_dams": ("سدها", "Dams"),
    "hv_county": ("شهرستان", "County"),
    "hv_well": ("چاه", "Well"),
    "dam": ("سد", "Dam"),
    # table legend
    "lg_w": ("برداشت (پررنگ‌تر = بیشتر)", "Withdrawal (darker = larger)"),
    "lg_r": ("برگشت", "Return"),
    "lg_g": ("حجم در دسترس (نوار)", "Available volume (bar)"),
    "lg_neg": ("کنترل منفی (کسری)", "Negative check (deficit)"),
    "lg_pos": ("کنترل مثبت", "Positive check"),
}

# data vocabulary (Persian -> English); unknown names are shown unchanged
TERMS = {
    # uses
    "شرب": "Drinking (urban)", "شرب روستایی": "Drinking (rural)", "کشاورزی": "Agriculture",
    "صنعتی": "Industry", "خدمات": "Services", "فضای سبز": "Green space", "فضای سبز مشهد": "Mashhad green space",
    "محیط زیست": "Environment", "سایر": "Other",
    # source groups & table structure
    "سد": "Dam", "بازه رودخانه": "River reach", "آب زیرزمینی": "Groundwater", "انتقالی": "Transfer",
    "تصفیه خانه": "Treatment plant", "آب انتقالی": "Transfer", "جمع‌بندی": "Summary", "مجموع": "Total",
    "مصارف (C)": "Consumption (C)", "کنترل بیلان (B)": "Balance check (B)", "برداشت": "Withdrawal",
    "برگشت": "Return", "کل": "All", "جمع": "Total", "نامشخص": "Unknown",
    "حجم در دسترس (G)": "Available volume (G)", "کنترل (G − برداشت)": "Check (G − withdrawal)",
    "گروه منبع": "Source group", "منبع": "Source", "کاربری": "Use", "تفکیک": "Breakdown",
    "زیرحوضه": "Sub-basin", "شهرستان": "County", "نوع منبع": "Source type",
    # counties (Khorasan Razavi and neighbours)
    "مشهد": "Mashhad", "چناران": "Chenaran", "طرقبه-شاندیز": "Torqabeh-Shandiz", "طرقبه شاندیز": "Torqabeh-Shandiz",
    "گلبهار": "Golbahar", "قوچان": "Quchan", "نیشابور": "Neyshabur", "فریمان": "Fariman", "باخرز": "Bakharz",
    "سبزوار": "Sabzevar", "درگز": "Dargaz", "کلات": "Kalat", "سرخس": "Sarakhs", "تربت حیدریه": "Torbat-e Heydarieh",
    "تربت جام": "Torbat-e Jam", "کاشمر": "Kashmar", "گناباد": "Gonabad", "تایباد": "Taybad", "خواف": "Khaf",
    "رشتخوار": "Roshtkhar", "بردسکن": "Bardaskan", "خلیل آباد": "Khalilabad", "مه ولات": "Mahvelat",
    "زاوه": "Zaveh", "فیروزه": "Firuzeh", "جوین": "Joveyn", "جغتای": "Joghatai", "خوشاب": "Khoshab",
    "داورزن": "Davarzan", "صالح آباد": "Salehabad", "بینالود": "Binalud", "کوهسرخ": "Kuhsorkh",
    "بجستان": "Bajestan", "زبرخان": "Zebarkhan", "اسفراین": "Esfarayen", "شیروان": "Shirvan", "بجنورد": "Bojnurd",
    # dams
    "طرق": "Torogh", "کارده": "Kardeh", "ارداک": "Ardak", "ارداک چناران": "Ardak", "چالی دره": "Chalidareh",
    "دولت آباد": "Dowlatabad", "دوستی": "Doosti",
}
PATTERNS = [
    (re.compile(r"^سد (.+)$"), lambda m, L: f"{term(m.group(1), L)} Dam"),
    (re.compile(r"^بازه رودخانه (.+)$"), lambda m, L: f"River reach {m.group(1)}"),
    (re.compile(r"^آبخوان زیرحوضه (.+)$"), lambda m, L: f"Aquifer, sub-basin {m.group(1)}"),
    (re.compile(r"^زیرحوضه (.+)$"), lambda m, L: f"Sub-basin {m.group(1)}"),
    (re.compile(r"^(.+) \(ضریب برگشت ([\d.]+)\)$"), lambda m, L: f"{term(m.group(1), L)} (return coef. {m.group(2)})"),
]


def t(key, lang, **kw):
    fa, en = UI[key]
    s = en if lang == "en" else fa
    return s.format(**kw) if kw else s


def term(s, lang):
    """Translate a data label (use, county, dam, row/column label) for display."""
    if lang != "en" or not isinstance(s, str):
        return s
    n = norm(s)
    if n in TERMS:
        return TERMS[n]
    for rx, fn in PATTERNS:
        m = rx.match(n)
        if m:
            return fn(m, lang)
    return s


def msg(m, lang):
    """Report message stored as {"fa": ..., "en": ...} (or a plain string)."""
    if isinstance(m, dict):
        return m.get(lang) or m.get("fa") or ""
    return str(m)


def num(v, lang, fmt="{:,.1f}"):
    if v is None:
        return "—"
    s = fmt.format(v) if isinstance(v, (int, float)) else str(v)
    return s.translate(FA_DIGITS) if lang == "fa" else s


def ltr(s):
    """Wrap digit runs (years like 1402-03) in an LTR isolate so they don't flip inside RTL text."""
    return re.sub(r"([۰-۹0-9][۰-۹0-9٫٬.,:/\- ]*[۰-۹0-9])", "⁦\\1⁩", s)


def year(y, lang):
    return ltr(num(y, lang)) if lang == "fa" else y
