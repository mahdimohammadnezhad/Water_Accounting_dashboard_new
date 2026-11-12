@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "..\.venv\Scripts\python.exe" (
  echo Creating Python environment ...
  python -m venv ..\.venv
  "..\.venv\Scripts\python.exe" -m pip install -r requirements.txt
)
rem skip Streamlit's one-time "Email:" prompt
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
  if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
  > "%USERPROFILE%\.streamlit\credentials.toml" (
    echo [general]
    echo email = ""
  )
)
"..\.venv\Scripts\python.exe" -m streamlit run app.py
