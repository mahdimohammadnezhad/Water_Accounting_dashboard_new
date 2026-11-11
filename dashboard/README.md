# Water accounting dashboard

Builds the sources-and-uses water balance of a study area (in the style of the `DYNMIC` sheet of the original
Excel workbook) directly from raw files, and shows it for any combination of water year, sub-basin, county, use
and source type. The interface is available in **Persian (default) and English**.

## Inputs
| Data | Typical file | Read by |
|---|---|---|
| Well withdrawals (year, county, UTM X/Y, use, volume) | `CHAH_MASHAHD.xls` | `wa/loaders.py` → `load_wells` |
| Dam statistics (start-of-year storage, inflow, uses, location) — one sheet per water year | `Amar_SAD.xlsx` | `wa/loaders.py` → `load_dams` |
| Renewable surface / groundwater, aquifer storage change, inter-basin transfer | *Simaye Ab* PDFs (`Bilan/`) | `wa/simaye_ab.py` |
| Sub-basins, counties, dam points | shapefiles (`shape/`) | `wa/spatial.py` |
| Population census (household & population by village, whole province; optional) | `CN95_HouseholdPopulationVillage_09.xlsx` | `wa/census.py` |
| All study areas and all counties of Iran (map context, look-up by name) | `shape/Basins/Mahdoude.shp`, `shape/shahrestan/shrestan.shp` | `configs/_regional.yaml` → `wa/spatial.py` → `read_regional` |

### Country-wide layers
`configs/_regional.yaml` points to the country-wide study-area and county shapefiles. They are shared by every
basin and are used to
- draw the neighbouring study areas and counties faintly on the map (within `context_buffer_km`);
- find the basin's own study area by name or code (`study_area: مشهد` or `study_area: 6007` in the basin config);
- stand in for missing files: a basin **without a sub-basin shapefile** uses its study area as a single sub-basin,
  and a basin **without a county shapefile** takes its counties from the country-wide layer. When adding a basin
  without shapefiles, the study area is found automatically from the well locations (the county column of the
  well statistics is used to identify the UTM zone).

All paths and column names live in one YAML file per basin (`configs/<basin>.yaml`); the code contains no file
names. The sample Excel workbook is **not** used by the dashboard — only `validate_excel.py` reads it, to compare
results.

## Running
Double-click `run_dashboard.bat` (or `..\.venv\Scripts\python.exe -m streamlit run app.py`), then open
http://localhost:8501. The first run (and any run after an input file changes) rebuilds the processed data in
about 10 seconds; after that every filter change takes under a second.

## Dashboard pages
| Tab | Content |
|---|---|
| Sources & uses table | Rows = sources (dams, river reaches, sub-basin aquifers, transfers, treatment plant); columns = use × breakdown × (withdrawal, return); available volume (G), check column, total / consumption / balance rows. Conditional formatting (colour by size, optional log scale). Excel export with the same colours. |
| Charts | Sankey (source → use), withdrawal by use and source type, share of each use in consumption |
| Annual trend | Withdrawal, resources, consumption and balance for every year with the same filters |
| Sub-basin × county | Withdrawal and area of every county inside every sub-basin, plus a downloadable detail table |
| Map (first tab) | Sub-basins, the study area, county borders, wells and dams on OpenStreetMap, Esri satellite imagery or a plain (offline) background. A three-way **review mode** — *county view*, *sub-basin view*, *combined view* — switches the related layers on and the others off; every layer also has its own on/off button. Neighbouring study areas and counties are drawn faintly, as are the sub-basins/counties not selected in the filters. |
| Management scenarios | Levers applied instantly: change of each use's withdrawal, of all groundwater pumping, closing illegal wells, reusing treated wastewater in agriculture instead of groundwater, changing the inter-basin transfer, wet/dry climate; for the whole basin or the selected area only. Presets (agriculture −20 %, close illegal wells, reuse, drought, combined package). Baseline-vs-scenario cards, withdrawal by use, aquifer deficit and balance over all years, effect by sub-basin. A switch applies the scenario to every tab. |
| Data & quality control | Import warnings, the values read from each Simaye Ab PDF, dam statistics, downloads of all base data |

Column layouts: *Excel template* (drinking & industry by county, the rest by sub-basin, as in DYNMIC), all uses by
county, all uses by sub-basin, or by use only. Return-flow coefficients can be edited in the sidebar.

## Method
- **Wells**: actual withdrawal (m³ → million m³). Sub-basin and county polygon from the well location; wells up to
  5 km outside the boundary snap to the nearest polygon; wells with invalid coordinates go to the main sub-basin
  of their county.
- **Dams**: available volume = start-of-year storage + inflow; withdrawals per use from the *uses* columns;
  county from the *location* column; sub-basin from the dam point shapefile.
- **Simaye Ab**: the first table of each PDF is read from its value column, so it also works for PDFs whose
  legacy Persian font cannot be extracted as text. Non-renewable = −ΔS; groundwater available = renewable
  groundwater + non-renewable, split between sub-basins and counties by area.
- **Transfer** (e.g. Doosti dam for Mashhad): withdrawal = the transfer volume quoted in the Simaye Ab table;
  available volume = a fixed allocation in the config (180 MCM for Mashhad).
- **Return flow**: return = coefficient × withdrawal of the group. The `river_fraction` share goes to a river
  reach (for Mashhad urban drinking: reach 4), the rest to the aquifers in proportion to groundwater withdrawal.
  Half of Mashhad's urban drinking return is reported as treatment-plant output.
- **Consumption (C)** = withdrawal − return; **balance check (B)** = renewable water − consumption (see below).

## Balance check and the Simaye Ab water budget
- **Balance check (B)** = renewable water of the selected area (Simaye Ab, scaled by area) − consumption. A negative
  value means consumption exceeds the renewable water, i.e. it is drawn from storage. The sidebar can switch back
  to the Excel definition (available volume of dams, groundwater and transfers − consumption).
- The **water budget** panel at the top reads every row of the first Simaye Ab table (rainfall, evapotranspiration,
  renewable surface/groundwater, surface & transfer and groundwater inflows/outflows, aquifer and reservoir
  storage change, reservoir evaporation) and draws inputs against outputs:
  renewable + inflows + storage loss = net consumption + outflows (+ storage gain). The dashboard's own consumption
  is marked on the outputs bar so the two can be compared.

## Trends and future demand
- *Annual trend* tab: withdrawal by use; **dependence of uses on sources** (for each year, how much groundwater,
  dam water, transfer and effluent goes to each use, absolute or %); **renewable water, consumption and balance**
  with uncertainty bands and any number of "x % of renewable water" lines, each with its uncertainty cloud.
- *Water demand & future* tab: observed consumption, the past demand estimated from population, and projections to
  a chosen horizon under three scenarios — *supply drinking & industry* (population and industry growth, band =
  growth rate ± its uncertainty), *rebalancing* (agriculture reduced until consumption reaches a target % of the
  mean renewable water by a target year, not below a floor; reports whether the target is reached) and *review of
  executed measures* (the linear trend of past consumption continued, with its prediction band) — against the
  renewable water with its band. Per-capita change, industry growth, target and floor are editable (defaults are
  starting assumptions; a basin config can set them under `demand:`).

## Population
- **Census.** The Statistical Centre file (household & population by village, `code of record` hierarchy:
  1 province, 2 county, 5 city with its urban zones, 6/8 village) is read by `wa/census.py`. Urban population of a
  county = county total − its villages; zone records of large cities (e.g. «مشهد1»…«مشهد 12») are not counted twice.
- **Population of the study area** = Σ over counties (urban × urban share + rural × rural share). Defaults:
  rural share = share of the county's area inside the study area (country-wide county layer); urban share = 100 %
  if at least half of the county lies inside, else 0. A county missing from the county layer but holding at least
  1 % of the withdrawal (Binalud = Torqabeh-Shandiz) counts fully. Both shares are editable in the dashboard
  (table *County population in the census*) and can be fixed in the config (`demand.census.shares`). For Mashhad
  the 1395 census gives about **3.45 million** people inside the study area.
- **Growth rate.** An editable table of periods, *from year → rate (%/yr)*: each row applies from its year until
  the next row; the first row also covers the years between the census and the base year (and back-casting). The
  future band uses rate ± the given uncertainty (percentage points). Population, its band and the per-capita
  withdrawal of drinking & services (l/person/day) are shown on a chart; drinking and services demand grows in
  proportion to the population.
- **Selection.** County filters use the census counties of the selected counties; a partial sub-basin selection
  scales the population by those sub-basins' share of drinking & services withdrawal.
- Without a census file the growth table acts on a relative population index (base year = 100).

```yaml
demand:
  census:
    file: CN95_HouseholdPopulationVillage_09.xlsx   # or files: [...] for a basin spanning several provinces
    year: 1395                                       # default: from the file name (CN95 -> 1395)
    county_aliases: {بینالود: طرقبه-شاندیز}           # census name -> name in the well statistics
    shares: {قوچان: {urban: 0, rural: 31}}           # optional: % of the county's urban / rural population inside
  growth:                                            # annual population growth (%), each from its year on
    - {from: 1395, rate: 1.3}
    - {from: 1403, rate: 1.3}
  growth_band: 0.5                                   # ± percentage points for the future band
```

## Uncertainty bands
Every input gets an assumed relative error (1σ, editable in the sidebar or per basin under `uncertainty:`):
metered wells 5 %, unmetered wells 20 %, illegal wells 30 % (from the *smart meter* and *well status* columns of
the well statistics), dam statistics 5 %, transfer 10 %, Simaye Ab renewable surface 15 % / groundwater 20 % /
storage change 25 %, return coefficients 20 %. They are propagated by Monte Carlo (400 samples) through the same
calculation, so withdrawal, return, consumption, resources and the balance check stay consistent. The 90 % range
(5–95 %) is shown under the KPI cards, as error bars on bar charts, as shaded bands on trend lines and in one line
under the balance table; the main numbers remain the best estimates. The bands can be switched off in the sidebar.

## Management scenarios
The scenario changes the processed data and reruns the normal engine (`wa/scenario.py`). A lower withdrawal also
lowers its return flow; reused effluent replaces agricultural groundwater pumping; the climate lever scales
renewable water and dam inflows. The scenario aquifer deficit is the observed deficit (−ΔS) plus the change in
groundwater withdrawal, minus the change in return flow reaching the aquifers, minus the change in recharge.

## Adding another basin
The same code runs for any study area whose files are of the same kinds (they may use other file names, column
names, sheet names, coordinate systems, numbers of sub-basins, etc.).

1. Put the basin's files in one folder (sub-folders are fine): the well Excel, the dam Excel (one sheet per
   water year, e.g. `94-95` or `1394-95`), the Simaye Ab PDFs, and — optionally — the sub-basin, county and
   dam-point shapefiles (without them the country-wide layers are used, see above) and the province census file
   (recognised by its `code of record` / `population` columns).
2. In the sidebar open **Add a new basin**, enter the folder path and a name, and click *Scan folder & create
   config* — or run `..\.venv\Scripts\python.exe new_basin.py "<folder>" --name "<name>"`.
3. The files, fields and coordinate system are detected automatically and `configs/<key>.yaml` is written,
   followed by a health check. The new basin appears in the basin selector.
4. Review the generated config: return coefficients (`uses`), outlet reach of each county
   (`county_outlet_reach`), dam names (`dams.list`) and transfers. `configs/mashhad.yaml` is a fully documented
   example.

Anything missing is tolerated: a basin without dams, transfers, a county shapefile or some Simaye Ab years still
runs; the problems are listed in the *Data & quality control* tab.

## Checks
```
..\.venv\Scripts\python.exe check_basin.py            # build every basin, compute every year/layout/county basis
..\.venv\Scripts\python.exe tests\make_test_basin.py  # synthetic "other basin" → auto-detect → health check
..\.venv\Scripts\python.exe validate_excel.py         # compare with the DYNMIC sheet of the sample Excel
```
`validate_excel.py` shows that, fed the same inputs as the Excel workbook (`tests/mashhad_excel_check.yaml`),
the engine reproduces DYNMIC cell by cell (only the aquifer areas differ slightly: shapefile vs. the
`boundary_area` sheet).

## Folder structure
```
dashboard/
  app.py                 Streamlit interface (Persian / English)
  new_basin.py           create a basin config from a data folder
  check_basin.py         health check of one or all basins
  validate_excel.py      comparison with the sample Excel's DYNMIC sheet
  configs/*.yaml         one config per basin
  configs/_regional.yaml country-wide study-area / county layers shared by all basins
  wa/config.py           config loading and defaults (column aliases, use mapping, return coefficients)
  wa/detect.py           automatic detection of the input files
  wa/loaders.py          wells, dams, transfers, indicators
  wa/simaye_ab.py        Simaye Ab PDF reader
  wa/spatial.py          sub-basins / counties, spatial assignment, areas
  wa/engine.py           balance engine and return flows
  wa/table.py            sources-and-uses table, conditional formatting, Excel export
  wa/uncertainty.py      Monte Carlo uncertainty bands
  wa/scenario.py         management scenarios
  wa/demand.py           population series and water-demand projections
  wa/census.py           population census reader, county shares inside the basin
  wa/charts.py, wa/ui.py charts, map, layout
  wa/i18n.py             Persian / English texts and vocabulary
  static/fonts/          Vazirmatn font (served locally, no internet needed)
  tests/                 Excel-comparison config and the synthetic-basin test
  data/processed/        generated data (automatic; safe to delete)
```
