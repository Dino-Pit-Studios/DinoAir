@echo off
setlocal enabledelayedexpansion

REM Pseudocode Translator - Windows Test Runner
REM This script:
REM  - Disables plugins (PSEUDOCODE_ENABLE_PLUGINS=0) for safe, deterministic tests
REM  - Sets PYTHONPATH to the repo root so imports work without extra setup
REM  - Runs both test suites:
REM      1) pseudocode_translator/tests/
REM      2) tests/
REM  - Propagates a non-zero exit code if any test run fails

REM Determine repo root based on the script location
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%\.."
set "REPO_ROOT=%CD%"

echo === Pseudocode Translator: Windows test runner ===
echo Repo root: %REPO_ROOT%
echo - Setting PSEUDOCODE_ENABLE_PLUGINS=0
set "PSEUDOCODE_ENABLE_PLUGINS=0"
echo - Ensuring PYTHONPATH includes repo root
if defined PYTHONPATH (
  set "PYTHONPATH=%REPO_ROOT%;%PYTHONPATH%"
) else (
  set "PYTHONPATH=%REPO_ROOT%"
)
echo PYTHONPATH=%PYTHONPATH%

echo.
echo Running: pytest -q pseudocode_translator/tests/
python -m pytest -q "pseudocode_translator/tests/"
set "RC1=%ERRORLEVEL%"

echo.
echo Running: pytest -q tests/
python -m pytest -q "tests/"
set "RC2=%ERRORLEVEL%"

REM Combine exit codes: non-zero if any failed
set "RC=0"
if not "%RC1%"=="0" set "RC=%RC1%"
if not "%RC2%"=="0" set "RC=%RC2%"

if "%RC%"=="0" (
  echo.
  echo All tests passed.
) else (
  echo.
  echo One or more test runs failed. RC1=%RC1% RC2=%RC2%
)

popd
endlocal & exit /b %RC%
