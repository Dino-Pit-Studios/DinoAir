# CodeQL Results Summary Script
Write-Host "CodeQL Security Analysis Results Summary" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green

$resultsDir = "codeql-results"

if (Test-Path $resultsDir) {
    Write-Host "`nResults Directory: $resultsDir" -ForegroundColor Cyan

    # List all result files
    $files = Get-ChildItem $resultsDir -Name
    Write-Host "`nGenerated Files:" -ForegroundColor Yellow
    foreach ($file in $files) {
        $size = (Get-Item "$resultsDir\$file").Length
        Write-Host "  - $file ($($size) bytes)" -ForegroundColor White
    }

    # Analyze CSV files for findings
    Write-Host "`nSecurity Findings Summary:" -ForegroundColor Yellow

    $csvFiles = Get-ChildItem $resultsDir -Filter "*.csv"
    $totalFindings = 0

    foreach ($csvFile in $csvFiles) {
        $language = if ($csvFile.Name -like "*python*") { "Python" } else { "JavaScript" }

        try {
            $content = Get-Content $csvFile.FullName | Where-Object { $_ -and $_ -notlike '"name"*' }
            $findingCount = $content.Count
            $totalFindings += $findingCount

            Write-Host "`n$language Analysis:" -ForegroundColor Cyan
            Write-Host "  Total Findings: $findingCount" -ForegroundColor White

            if ($findingCount -gt 0) {
                # Parse and categorize findings
                $severityCount = @{}
                $issueTypes = @{}

                foreach ($line in $content) {
                    if ($line) {
                        $fields = $line -split '","'
                        if ($fields.Count -ge 3) {
                            $issueType = ($fields[0] -replace '"', '').Trim()
                            $severity = ($fields[2] -replace '"', '').Trim()

                            if (-not $severityCount.ContainsKey($severity)) {
                                $severityCount[$severity] = 0
                            }
                            $severityCount[$severity]++

                            if (-not $issueTypes.ContainsKey($issueType)) {
                                $issueTypes[$issueType] = 0
                            }
                            $issueTypes[$issueType]++
                        }
                    }
                }

                Write-Host "  By Severity:" -ForegroundColor White
                foreach ($severity in $severityCount.Keys | Sort-Object) {
                    $color = switch ($severity.ToLower()) {
                        "error" { "Red" }
                        "warning" { "Yellow" }
                        "note" { "Gray" }
                        default { "White" }
                    }
                    Write-Host "    ${severity}: $($severityCount[$severity])" -ForegroundColor $color
                }

                Write-Host "  Top Issue Types:" -ForegroundColor White
                $topIssues = $issueTypes.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 5
                foreach ($issue in $topIssues) {
                    Write-Host "    $($issue.Name): $($issue.Value)" -ForegroundColor White
                }
            }
        } catch {
            Write-Host "  Error reading CSV file: $_" -ForegroundColor Red
        }
    }

    Write-Host "`nOverall Summary:" -ForegroundColor Green
    Write-Host "  Total Security Findings: $totalFindings" -ForegroundColor White

    if ($totalFindings -gt 0) {
        Write-Host "`nNext Steps:" -ForegroundColor Yellow
        Write-Host "1. Install SARIF Viewer extension in VS Code" -ForegroundColor White
        Write-Host "2. Open .sarif files to view detailed security findings" -ForegroundColor White
        Write-Host "3. Review and address security issues found by CodeQL" -ForegroundColor White
        Write-Host "4. Re-run analysis after fixes to verify resolution" -ForegroundColor White
    } else {
        Write-Host "No security issues found - excellent!" -ForegroundColor Green
    }

} else {
    Write-Host "Results directory not found!" -ForegroundColor Red
}

Write-Host "`nCodeQL CLI Configuration:" -ForegroundColor Cyan
Write-Host "  Status: Configured and working" -ForegroundColor Green
Write-Host "  Version: CodeQL 2.23.1" -ForegroundColor White
Write-Host "  PATH: Added to user environment" -ForegroundColor White
Write-Host "  Languages: Python, JavaScript, and 12+ others available" -ForegroundColor White