@echo off

:: Check if venv exists
if not exist "_venv\Scripts\python.exe" (
echo ERROR: venv not found.
pause
exit /b
)

:: Run type choice
echo.
echo ==========================
echo Choose an option to run:
echo blank			-
echo solo			- 
echo gnn			- trains a solo network (default)
echo marl			- trains two competing networks
echo ==========================
set /p choice=Enter your choice:
:: Choice to file
if /i "%choice%" == "" (
	set pyfile=gnn.py
	goto pass_type
)
if /i "%choice%"=="blank" (
	set pyfile=blank.py
	goto pass_type
)
if /i "%choice%"=="solo" (
	set pyfile=solo.py
	goto pass_type
)
if /i "%choice%"=="gnn" (
	set pyfile=gnn.py
	goto pass_type
)
if /i "%choice%"=="marl" (
	set pyfile=marl.py
	goto pass_type
)
echo.
echo ERROR: Invalid choice "%choice%".
pause
exit /b

:pass_type
:: Check if file exists
if not exist "%pyfile%" (
	echo ERROR: File not found: %pyfile%
	pause
	exit /b
)


:: Network choice
echo.
echo ==========================
echo Predefined networks:
echo manhattan		- small grid (default)
echo Zagreb			- example of an OpenStreetMap cutout
echo ==========================
set /p network_name=Enter network name:
if /i "%network_name%" == "" (set network_name=manhattan)

set network_filepath=networks/%network_name%

:: Check if file exists
if exist "%network_filepath%" (goto run)

:missing_network
echo ERROR: Network folder not found: "%network_name%" (path: "%network_filepath%")
pause
exit /b
	
:run
:: Run Python file through venv
start "Runner" cmd /k "_venv\Scripts\python.exe %pyfile% %network_name%"

exit /b
