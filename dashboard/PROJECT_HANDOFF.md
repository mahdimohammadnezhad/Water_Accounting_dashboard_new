# Project handoff — Water accounting dashboard (Mashhad–Chenaran and other study areas)

Read this first if you are an AI assistant (or a developer) continuing this project. It summarises what exists,
why it was built that way, how to run and test it, and what is still open. Last updated: 12 November 2026.

## 1. Ground rules from the owner

- **Owner:** Mahdi Mohammadnezhad. He writes in Persian; answer him in Persian unless he asks otherwise. Code,
  comments, commit messages and README are in English; the dashboards are bilingual (Persian default, English).
- **Git authorship:** every commit must have author *and* committer
  `Mahdi Mohammadnezhad <103482700+mahdimohammadnezhad@users.noreply.github.com>` (already set in the repo's local
  git config). **Never add a `Co-Authored-By: Claude …` (or any AI) trailer.** History was rewritten once to remove
  such lines.
- Commit or push only when he asks. Never force-push unless he asks explicitly.
- Only the dashboard code is in git; raw data, the manuscript and the Python environment stay local
  (see `.gitignore` at the repo root: everything except `README.md`, `.gitignore` and `dashboard/` is ignored).
- Remote: https://github.com/mahdimohammadnezhad/Water_Accounting_dashboard_new

## 2. Branches

| Branch | Content | Start |
|---|---|---|
| `main` | Expert dashboard (`app.py`): every table, setting, uncertainty band. Also contains `dashboard/template/` (Plus Admin HTML template the owner committed as a design reference; not used by the code). | `run_dashboard.bat` → `app.py` |
| `management` | Everything in `main` **plus** the management dashboard (`manager.py`, `wa/mgmt.py`) and this file. | `run_dashboard.bat` → `manager.py`; `run_expert.bat` → `app.py` |

The expert code (`app.py` and the shared `wa/` engine) is identical on both branches; `management` only adds files
and changes the launcher. Keep it that way so `main` can be merged into `management` without conflicts.

## 3. Folder layout on the owner's machine

```
D:\Term2\WERI\Water_Accounting\          (git repository root)
  .venv\                                 Python 3.12 environment (not in git)
  CHAH_MASHAHD.xls                       well inventory (49,299 well-year records, 1395-96 … 1402-03)
  Amar_SAD.xlsx                          dam statistics, one sheet per water year (5 dams)
  Bilan\*.pdf                            Simaye Ab water-budget bulletins, 8 years
  CN95_HouseholdPopulationVillage_09.xlsx  1395 census, Khorasan Razavi (household & population by village)
  shape\                                 sub-basins (final_boundary_fixed.shp), counties, dam points,
                                         shape\Basins\Mahdoude.shp + shape\shahrestan\shrestan.shp (country-wide)
  water_acounting_1Sep25.xlsx            legacy Excel account (sheet DYNMIC) — only validate_excel.py reads it
  prompt.docx                            the owner's original requirements (Persian)
  Manuscript\Water_Accounting_Manuscript.docx   journal manuscript draft (local only, see §9)
  dashboard\                             all code (in git)
```

## 4. Environment and running

- Python: `..\.venv\Scripts\python.exe` from inside `dashboard\` (pandas 3 with the new string dtype, geopandas,
  pyogrio, shapely 2, plotly 7, streamlit 1.64, xlsxwriter, xlrd, openpyxl, pyyaml). `requirements.txt` lists them.
- Run: `run_dashboard.bat` / `run_expert.bat`, or `..\.venv\Scripts\python.exe -m streamlit run manager.py` (or `app.py`).
- The first run builds `data/processed/<basin key>/` (parquet + `meta.json`, ~30 s); it is rebuilt automatically
  when the config, the code of the build modules or any input file changes (signature in `wa/config.py`).
- Printing Persian from scripts on Windows needs `PYTHONIOENCODING=utf-8`.
- A running Streamlit server does **not** reload changed `wa/*.py` modules — restart it after editing them.
- In Git Bash, heredocs containing `'''` break; write patch/test scripts to a file and run them.
- The PC's internet access to PyPI is blocked (pip install fails); everything needed is already in `.venv`.

## 5. Architecture (`dashboard/`)

| File | Role |
|---|---|
| `app.py` | Expert dashboard (Streamlit, ~800 lines): sidebar filters, 8 tabs (map, sources-and-uses table, charts, annual trend, sub-basin × county, management scenarios, water demand & population, data quality). |
| `manager.py` | Management dashboard (3 controls, 4 tabs; §7). |
| `new_basin.py` | CLI: scan a data folder and write `configs/<key>.yaml` (same as the "add basin" panels). |
| `check_basin.py` | Health check: builds every basin and computes every year × county basis × table layout, map, uncertainty, a scenario with every lever, demand projection. |
| `validate_excel.py` | Cell-by-cell comparison with the legacy Excel (`tests/mashhad_excel_check.yaml`). |
| `tests/make_test_basin.py` | Builds two synthetic "other basins" from the Mashhad files (renamed columns, 3 text-named sub-basins, a missing bulletin year, an extra use; and one without any shapefile or census), auto-detects them and runs the health check. `--keep` leaves their configs for manual testing. |
| `configs/mashhad.yaml` | Fully commented basin config (paths, column names, use mapping, return coefficients, dams, transfer, census, growth). `configs/_regional.yaml` = country-wide layers. |
| `wa/config.py` | Config loading, defaults (column aliases, uncertainty σ), build signature. |
| `wa/detect.py` | Automatic detection of input files/columns/CRS for a new basin; writes the config. |
| `wa/loaders.py` | Wells (well class: metered `gw_m`, unmetered `gw_u`, illegal `gw_i`), dams, transfers, indicators. |
| `wa/simaye_ab.py` | Reads the first table of each Simaye Ab PDF from its value column (works with legacy Persian fonts); fixes documented in the QC report (derived surface value, unsigned ΔS). |
| `wa/spatial.py` | Sub-basin/county assignment (point-in-polygon, 5 km snapping, county majority), areas, country-wide layers. |
| `wa/build.py` | Builds and caches all tables (`W`, `RES`, `indicators`, `cells`, `wells`, `dams`, `dam_stats`, `simaye`, `census`). |
| `wa/engine.py` | Return flows and consumption; `compute(base, cfg, uses, mode)` → `W, RET, RES`. |
| `wa/table.py` | Sources-and-uses matrix in the DYNMIC layout, conditional formatting, Excel export. |
| `wa/uncertainty.py` | Monte Carlo (400 samples, seed 7) on every input; 90 % bands. |
| `wa/scenario.py` | Management levers (use %, groundwater %, illegal wells closed, effluent reuse, transfer, climate) and the scenario aquifer deficit. |
| `wa/demand.py` | Population series (growth-rate periods), demand projections (supply / rebalancing / trend). |
| `wa/census.py` | Census reader and county shares inside the study area. |
| `wa/mgmt.py` | Numbers and figures of the management dashboard. |
| `wa/charts.py`, `wa/ui.py`, `wa/i18n.py`, `wa/text.py` | Plotly figures, HTML/CSS (Vazirmatn, RTL/LTR, cards), Persian/English texts, Persian text normalisation. |

## 6. Method (what the numbers mean)

- **Withdrawal W:** wells (actual abstraction, m³ → MCM), dam releases by use, inter-basin transfer (Doosti dam for
  Mashhad: withdrawal = transfer volume of the bulletin; available = fixed 180 MCM).
- **Return R = c × W** per use and group (county for urban drinking and industry, sub-basin for others);
  share `river_fraction` to a river reach, rest to aquifers in proportion to groundwater withdrawal; half of
  Mashhad's urban-drinking return is reported as treatment-plant output. Coefficients (from the legacy Excel):
  urban drinking 0.7, services 0.7, rural drinking 0.15, agriculture 0.15, industry 0.15 (the bulletin uses
  industry 0.7 / services 0.15 — an open question).
- **Consumption C = W − R.** **Balance check B = renewable water (bulletin, scaled by area) − C**; the Excel
  definition (available volume − C) is an option in the expert dashboard.
- **Bulletin closure:** net consumption implied by the bulletin = renewable + inflows − outflows − reservoir
  evaporation − ΔS (aquifer + reservoirs); shown on the water-budget chart.
- **Uncertainty:** relative 1σ by input (metered wells 5 %, unmetered 20 %, illegal 30 %, unknown 15 %, dams 5 %,
  transfer 10 %, treatment 10 %, renewable surface 15 %, renewable groundwater 20 %, ΔS 25 %, return coefficients
  20 %), normal factors truncated at 0, propagated by Monte Carlo through the same calculation.
- **Scenario aquifer deficit:** D_s = D_obs + ΔW_gw − ΔR_gw − ΔRecharge (first order, no groundwater model).
- **Population:** census population inside the area = Σ counties (urban × urban% + rural × rural%); defaults:
  rural% = area share of the county (country-wide layer), urban% = 100 if ≥ 50 % of the county is inside, else 0;
  a county missing from the layer but holding ≥ 1 % of withdrawal counts fully (Binalud = Torqabeh-Shandiz).
  Growth from a table of periods; drinking & services demand scales with population.
- **Management view (`wa/mgmt.py`):** aquifer storage loss = bulletin −ΔS × area share; *sustainable consumption*
  = mean consumption − mean storage loss over the record; *required cut* = business-as-usual consumption at the
  horizon − sustainable consumption; options are averaged over all years.

## 7. The two dashboards

**Expert (`app.py`, branch main and management):** sidebar with basin, year, county basis, sub-basins, counties,
uses, source types, table layout, balance definition, return coefficients, uncertainty σ, add-basin panel; tabs as
in §5. The "map tab first" order and the three-way map review mode (county / sub-basin / combined) were explicit
owner requests.

**Management (`manager.py`, branch management):** for a manager who must decide "at a glance", following the
three-click rule (answer within 3, at most 5 clicks; no extra information). Controls: basin (if several), water year,
area (whole study area or one sub-basin — counties are deliberately not an area because renewable water and the
aquifer loss only make sense for hydrological units), language. Tabs:
1. *Status* (0 clicks): red/green/grey banner on the aquifer storage loss, 4 key numbers, 8-year trend, consumption
   by use; an amber note when recorded consumption < renewable water while the aquifer still declines.
2. *Areas* (1): map of consumption per area (mm/yr) and rankings of sub-basins and counties. The map is a plain
   Plotly figure (not a tile map) because MapLibre cannot shape Persian text.
3. *Management options* (1): all available options compared (mean of all years), best one named; custom package
   from sliders (3). Options without data are hidden (illegal wells need the legal-status column; reuse needs a
   `treatment_fraction`); the combined package is built from the available parts.
4. *Outlook* (1): required cut by the horizon, also as % of agricultural consumption; growth-rate and horizon
   sliders (2).
Widget keys are per basin (`year_<key>`, `area_<key>`, `f_rate_<key>` …) so selections survive a language change.

## 8. Key results for Mashhad–Chenaran (water years 1395-96 … 1402-03 = 2016/17 … 2023/24)

| Item | Value |
|---|---|
| Area / sub-basins | 9,925 km²; 4 sub-basins (1,614 / 2,549 / 2,737 / 3,024 km²) |
| Mean withdrawal | 811 MCM/yr (groundwater 87 %, transfer 8.3 %, dams 4.7 %) |
| Mean consumption | 520 MCM/yr (agriculture 70 % of consumption, 53 % of withdrawal) |
| Mean renewable water | 597 MCM/yr (313 … 883) |
| Balance check B | +77 MCM/yr mean; negative in 1399-00, 1400-01, 1401-02 |
| Aquifer storage loss (bulletin) | every year, mean 101 MCM/yr, 808 MCM in 8 years |
| Bulletin-implied minus bottom-up consumption | median 161 MCM/yr (records cover ~76 %) |
| Options (mean deficit after) | −20 % irrigation: 31; close illegal wells: 43; reuse 50 %: 67; combined: −11 (recovery); drought −30 %: 239 |
| Population | 3,450,197 in 1395 (census, inside the area); 3.78 M in 1402-03; 4.77 M in 1420-21 at 1.3 %/yr |
| Per-capita drinking + services withdrawal | 236–292 l/person/day (270 in 1402-03) |
| Required cut by 1420-21 (management view) | ~127 MCM/yr ≈ 37 % of current agricultural consumption |
| Excel validation | same inputs → 788 cells, max difference 0.05 MCM; raw files → differences explained by a green-space table and the Doosti transfer entered by hand in Excel |

## 9. Work done so far (chronological)

1. Excel `DYNMIC` account rebuilt in Python/Streamlit from the raw files only; filters, return-flow rules,
   conditional formatting, Excel export (commit 89f88e7).
2. Basin-agnostic config + automatic detection of new basins; Persian/English (ac12bf7).
3. Map first, three review modes, country-wide context layers; fix of negative withdrawals on the map (b8d2ef6).
4. Monte Carlo uncertainty bands and management scenarios (9a85eb7).
5. Balance = renewable − consumption, Simaye Ab water-budget chart, source → use dependence chart, renewable-%
   trend lines, water demand & future tab, 1395 census population with an editable growth-rate table (c0b243c).
6. Journal manuscript (English, aimed at *Environmental Modelling & Software*): written, exported to Word with
   native equations, A4, line and page numbers → `Manuscript/Water_Accounting_Manuscript.docx` (local only).
   Its last section "Notes for the authors" lists what must be done before submission (verify every reference/DOI,
   add local Mashhad studies, replace the placeholder growth rate, decide industry/services return coefficients,
   GIS map for Fig. 1, licence + Zenodo DOI, data permission, high-resolution figures).
7. The owner installed the `ui-ux-pro-max` skill (v2.15.0) and asked for a restyle on the Plus Admin template;
   it was built and then **reverted at his request** — the expert dashboard keeps its original look.
8. Management dashboard on branch `management` (d4ac81a) and its multi-basin support (this commit).

## 10. How to test after a change

```
cd dashboard
..\.venv\Scripts\python.exe check_basin.py              # every basin, every combination → "OK"
..\.venv\Scripts\python.exe tests\make_test_basin.py    # synthetic basins → "RESULT: OK"
..\.venv\Scripts\python.exe validate_excel.py           # Excel comparison
```
For the UIs, Streamlit's `AppTest` works well: load `app.py` / `manager.py`, change widgets, assert
`at.exception` is empty in both languages. Note: AppTest returns *formatted* selectbox labels — set years with
their raw value (`"1402-03"`), not with the displayed label. For visual checks, run the app headless and take
screenshots with Chrome's DevTools protocol.

## 11. Pitfalls already met

- Plotly reads English year labels like `"1400-01"` as dates → force `xaxis.type="category"`.
- Plotly titles in RTL get clipped if the chart container has horizontal padding.
- MapLibre (tile maps) cannot shape Persian labels → hover text only, or a non-tile figure.
- Streamlit forgets the state of widgets that are not rendered; widgets whose label changes with the language need
  a fixed `key`.
- Census names differ from the well statistics (`county_aliases`, built-in `بینالود → طرقبه-شاندیز`); Persian text
  must go through `wa.text.norm` (Arabic ي/ك, ZWNJ, mojibake in shapefiles: `fix_mojibake`).
- Some bulletins print ΔS without a sign (treated as a deficit, `assume_deficit: true`) or miss the surface value
  (derived as total − groundwater); both are listed in the data-quality tab.

## 12. Open items / ideas

- Replace the placeholder population growth rate (1.3 ± 0.5 %/yr) with an official projection (`demand.growth` in
  the basin config).
- Decide the return coefficients of industry and services (Excel 0.15/0.7 vs bulletin 0.7/0.15).
- Add a licence file to the repository (needed for the paper's software-availability section).
- Management view: per-basin defaults for presets; optional export of the status page as a one-page PDF report.
- Possible: couple with a groundwater model, or cross-check consumption with satellite evapotranspiration.
