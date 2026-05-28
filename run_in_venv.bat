@echo off

:: Check if venv exists
if not exist "_venv\Scripts\python.exe" (
echo ERROR: venv not found.
pause
exit /b
)

:: Ask user for Python file
set /p pyfile=Enter Python file name (example: gnn.py):

:: Check if file exists
if not exist "%pyfile%" (
echo ERROR: File not found: %pyfile%
pause
exit /b
)

:: Run Python file through venv
call _venv\Scripts\activate
python "%pyfile%"

echo.
pause
