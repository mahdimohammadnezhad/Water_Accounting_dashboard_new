# Water_Accounting_dashboard_new

An interactive, bilingual (Persian / English) **water-accounting dashboard** built with Streamlit. It reads raw
statistics — well withdrawals, dam statistics, the *Simaye Ab* water-balance PDFs and the sub-basin / county
shapefiles — and builds the sources-and-uses balance table (rows = sources, columns = use × county or
sub-basin × withdrawal / return), with return flows, a balance check, charts, trends and a map.

It was developed for the Mashhad–Chenaran study area, but it is **basin-agnostic**: point it at a folder with the
same kinds of files for any other study area and it detects the files and builds a configuration automatically.

Full documentation: [dashboard/README.md](dashboard/README.md)

## Data
The data files are **not** included in this repository. To run the Mashhad example, put them in the repository
root, next to the `dashboard` folder:

```
Amar_SAD.xlsx                  dam statistics (one sheet per water year)
CHAH_MASHAHD.xls               well withdrawals
Bilan/*.pdf                    Simaye Ab reports (water-balance table)
shape/final_boundary_fixed.*   sub-basins
shape/shahrestan.*             counties
shape/selected_dams.*          dam locations
water_acounting_1Sep25.xlsx    (optional) sample Excel, only used by validate_excel.py
```

## Quick start (Windows)
Double-click `dashboard/run_dashboard.bat`. On first run it creates a Python environment (`.venv`) and installs
the requirements, then opens the dashboard at http://localhost:8501.

Manual start:
```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r dashboard\requirements.txt
cd dashboard
..\.venv\Scripts\python.exe -m streamlit run app.py
```

## Another basin
In the dashboard sidebar open **Add a new basin**, enter the folder that holds the basin's files and click
*Scan folder & create config* — or from the command line:
```
cd dashboard
..\.venv\Scripts\python.exe new_basin.py "D:\data\Neyshabur" --name "Neyshabur study area"
```
