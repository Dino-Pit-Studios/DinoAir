# Permanent CodeQL PATH Setup Script
# Run this script as Administrator to permanently add CodeQL to Windows PATH

$codeqlPath = "C:\Users\DinoP\Documents\codeql-bundle-win64\codeql"

Write-Host "CodeQL PATH Configuration" -ForegroundColor Green
Write-Host "=========================" -ForegroundColor Green

# Check if CodeQL executable exists
if (Test-Path "$codeqlPath\codeql.exe") {
    Write-Host "CodeQL found at: $codeqlPath" -ForegroundColor Green
} else {
    Write-Host "CodeQL not found at: $codeqlPath" -ForegroundColor Red
    Write-Host "Please verify the installation path" -ForegroundColor Yellow
    exit 1
}

# Get current system PATH
$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")

# Check if CodeQL is already in PATH
if ($currentPath -like "*$codeqlPath*") {
    Write-Host "CodeQL is already in your PATH" -ForegroundColor Yellow
} else {
    try {
        # Add CodeQL to user PATH
        $newPath = "$codeqlPath;$currentPath"
        [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")

        Write-Host "Successfully added CodeQL to PATH" -ForegroundColor Green
        Write-Host "Please restart your terminal for changes to take effect" -ForegroundColor Yellow

    } catch {
        Write-Host "Failed to add CodeQL to PATH" -ForegroundColor Red
        Write-Host "Error: $_" -ForegroundColor Red
        Write-Host "Try running this script as Administrator" -ForegroundColor Yellow
    }
}

# Test CodeQL in current session
Write-Host "`nTesting CodeQL in current session..." -ForegroundColor Cyan
try {
    # Add to current session PATH if not already there
    if (-not ($env:PATH -like "*$codeqlPath*")) {
        $env:PATH = "$codeqlPath;$env:PATH"
    }

    $version = & codeql version 2>&1
    Write-Host "CodeQL is working!" -ForegroundColor Green
    Write-Host "Version: $($version[0])" -ForegroundColor Cyan

    # Show available languages
    Write-Host "`nAvailable languages:" -ForegroundColor Cyan
    $languages = & codeql resolve languages 2>&1
    $languages | ForEach-Object {
        if ($_ -match '^(\w+) \(') {
            Write-Host "  - $($matches[1])" -ForegroundColor White
        }
    }

} catch {
    Write-Host "Error testing CodeQL" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
}

Write-Host "`nNext Steps:" -ForegroundColor Yellow
Write-Host "1. Restart your PowerShell terminal" -ForegroundColor White
Write-Host "2. Run: codeql version" -ForegroundColor White
Write-Host "3. Use: .\run-codeql-analysis.ps1 to analyze DinoAir" -ForegroundColor White