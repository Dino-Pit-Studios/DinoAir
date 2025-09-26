# DinoAir Virtual Environment Activation Script
# Run this script to activate the virtual environment with all dependencies

Write-Host "Activating DinoAir Virtual Environment..." -ForegroundColor Cyan
Write-Host ""

# Activate the virtual environment
& "$PSScriptRoot\.venv\Scripts\Activate.ps1"

Write-Host "DinoAir Virtual Environment Activated!" -ForegroundColor Green
Write-Host "Python version: $(python --version)" -ForegroundColor Blue
Write-Host "Virtual env path: $env:VIRTUAL_ENV" -ForegroundColor Blue
Write-Host ""
Write-Host "Key packages installed:" -ForegroundColor Yellow
Write-Host "   - FastAPI and Uvicorn (API framework)" -ForegroundColor White
Write-Host "   - Pytest and Coverage (Testing)" -ForegroundColor White
Write-Host "   - Black, Ruff, MyPy (Code quality)" -ForegroundColor White
Write-Host "   - Pydantic (Data validation)" -ForegroundColor White
Write-Host "   - HTTPX, aiofiles (Async utilities)" -ForegroundColor White
Write-Host "   - Sphinx (Documentation)" -ForegroundColor White
Write-Host "   - Safety, Bandit (Security)" -ForegroundColor White
Write-Host ""
Write-Host "Common commands:" -ForegroundColor Yellow
Write-Host "   - Run tests: pytest" -ForegroundColor White
Write-Host "   - Format code: black ." -ForegroundColor White
Write-Host "   - Lint code: ruff check ." -ForegroundColor White
Write-Host "   - Type check: mypy ." -ForegroundColor White
Write-Host "   - Start API: uvicorn API_files.app:app --reload" -ForegroundColor White
Write-Host ""