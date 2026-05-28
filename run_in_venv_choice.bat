@echo off

:: Check if venv exists
if not exist "_venv\Scripts\python.exe" (
echo ERROR: venv not found.
pause
exit /b
)

:: User choice
echo.
echo ==========================
echo Choose an option to run:
echo blank			-
echo solo			- 
echo gnn			- trains a solo network
echo marl			- trains two competing networks
echo ==========================
set /p choice=Enter your choice (A/B/C/D):
:: Choice to file
if /i "%choice%"=="blank" (
	set pyfile=.py
	goto run
)
if /i "%choice%"=="solo" (
	set pyfile=.py
	goto run
)
if /i "%choice%"=="gnn" (
	set pyfile=gnn.py
	goto run
)
if /i "%choice%"=="marl" (
	set pyfile=marl.py
	goto run
)
echo.
echo ERROR: Invalid choice "%choice%".
pause
exit /b

:run
:: Check if file exists
if not exist "%pyfile%" (
echo ERROR: File not found: %pyfile%
pause
exit /b
)

:: Run Python file through venv
start "Runner" cmd /k "_venv\Scripts\python.exe %pyfile%"
::call _venv\Scripts\activate
::python "%pyfile%"

exit /b
