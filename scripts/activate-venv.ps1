# Quick Virtual Environment Activation Script
# Run this script to activate the DinoAir virtual environment

Write-Host "🐍 Activating DinoAir Virtual Environment..." -ForegroundColor Green

# Change to the DinoAir directory
$dinoAirPath = "C:\Users\DinoP\Documents\DinoAirNew\DinoAir"
Set-Location $dinoAirPath

# Check if virtual environment exists
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    # Activate the virtual environment
    & ".\.venv\Scripts\Activate.ps1"

    Write-Host "✅ Virtual environment activated!" -ForegroundColor Green
    Write-Host "📁 Current directory: $(Get-Location)" -ForegroundColor Cyan
    Write-Host "🐍 Python version: $((& python --version))" -ForegroundColor Cyan
    Write-Host "📦 Pip location: $((& where.exe pip))" -ForegroundColor Cyan

    Write-Host "`n💡 Tips:" -ForegroundColor Yellow
    Write-Host "   - Use 'deactivate' to exit the virtual environment" -ForegroundColor White
    Write-Host "   - Run 'python -m pip list' to see installed packages" -ForegroundColor White
    Write-Host "   - VS Code should now use this Python interpreter automatically" -ForegroundColor White

} else {
    Write-Host "❌ Virtual environment not found at $dinoAirPath\.venv" -ForegroundColor Red
    Write-Host "   Please ensure you're in the correct directory." -ForegroundColor Yellow
}