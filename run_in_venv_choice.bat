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
echo 1 blank		- run a blank example (no charging stations)
echo 2 solo			- run an algorithmic solo simulation
echo 3 comp			- (default) run an algorithmic competitive simulation
echo 4 gnn			- trains a solo network
echo 5 marl			- trains two competing networks
echo ==========================
set /p choice=Enter your choice:
:: Choice to file
if /i "%choice%" == "" (
:: default
	goto comp
)
if /i "%choice%" == "1" (goto blank)
if /i "%choice%" == "2" (goto solo)
if /i "%choice%" == "3" (goto comp)
if /i "%choice%" == "4" (goto gnn)
if /i "%choice%" == "5" (goto marl)
if /i "%choice%"=="blank" (
:blank
	set pyfile=blank.py
	set title=Blank simulation
	goto pass_type
)
if /i "%choice%"=="solo" (
:solo
	set pyfile=solo.py
	set title=Solo algorithm
	goto pass_type
)
if /i "%choice%"=="comp" (
:comp
	set pyfile=comp.py
	set title=Competitive algorithm
	goto pass_type
)
if /i "%choice%"=="gnn" (
:gnn
	set pyfile=gnn.py
	set title=Graph NN RL
	goto pass_type
)
if /i "%choice%"=="marl" (
:marl
	set pyfile=marl.py
	set title=Multi-Agent RL
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
echo manhattan		- (default) simple 9x9 grid
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
set title="Runner %title%"
start %title% cmd /k "_venv\Scripts\python.exe %pyfile% %network_name%"

exit /b
