# Build a standalone Windows .exe for the Tournament Planner.
#
# Usage (from the project root):
#     powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
#
# Result: dist\TournamentPlanner.exe  (single file, no console window)

$ErrorActionPreference = "Stop"

# 1. Make sure PyInstaller is installed in the active environment.
python -m pip install --upgrade pyinstaller

# 2. Build.
#    - ui.py is the entry point; anything imported by it is automatically added
#    - --onefile  : pack everything into a single .exe
#    - --windowed : no console window (this is a tkinter GUI)
#    - --name     : name of the produced executable
python -m PyInstaller `
    --clean `
    --onefile `
    --windowed `
    --name TournamentPlanner `
    ui.py

Write-Host ""
Write-Host "Build finished. Executable: dist\TournamentPlanner.exe"
Write-Host "NOTE: the target PC still needs the Microsoft Access Database Engine"
Write-Host "      (ACE) ODBC driver installed for pyodbc to open .TP files."
