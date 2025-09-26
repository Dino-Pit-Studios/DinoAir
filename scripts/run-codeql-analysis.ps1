# CodeQL Security Analysis Script for DinoAir
# Analyzes Python and JavaScript code for security vulnerabilities

Write-Host "CodeQL Security Analysis" -ForegroundColor Green
Write-Host "=======================" -ForegroundColor Green

# Configuration
$projectPath = Get-Location
$databaseDir = "codeql-databases"
$resultsDir = "codeql-results"
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"

# Directories to exclude from analysis (library/vendor code)
$excludeDirs = @(".venv", "venv", "node_modules", "__pycache__", ".git", "build", "dist")
$excludePattern = ($excludeDirs | ForEach-Object { "*$_*" }) -join ","

# Ensure CodeQL is in PATH
$codeqlPath = "C:\Users\DinoP\Documents\codeql-bundle-win64\codeql"
if (-not ($env:PATH -like "*$codeqlPath*")) {
    $env:PATH = "$codeqlPath;$env:PATH"
}

# Create directories
New-Item -ItemType Directory -Force -Path $databaseDir | Out-Null
New-Item -ItemType Directory -Force -Path $resultsDir | Out-Null

# Prepare query suites directory and duplicate-code suites
$suitesDir = "codeql-suites"
New-Item -ItemType Directory -Force -Path $suitesDir | Out-Null

# Define comprehensive duplicate-code query suites for Python and JavaScript/TypeScript
# Include both structural duplicates and similarity-based detection
$pythonSuite = @"
- from: codeql/python-queries
  query: external/DuplicateFunction.ql
- from: codeql/python-queries
  query: external/DuplicateBlock.ql
- from: codeql/python-queries
  query: external/MostlyDuplicateClass.ql
- from: codeql/python-queries
  query: external/MostlyDuplicateFile.ql
- from: codeql/python-queries
  query: Metrics/FLinesOfDuplicatedCode.ql
- from: codeql/python-queries
  query: Expressions/DuplicateKeyInDictionaryLiteral.ql
"@

$jsSuite = @"
- from: codeql/javascript-queries
  query: external/DuplicateFunction.ql
- from: codeql/javascript-queries
  query: external/DuplicateToplevel.ql
- from: codeql/javascript-queries
  query: Metrics/FLinesOfDuplicatedCode.ql
- from: codeql/javascript-queries
  query: Expressions/DuplicateCondition.ql
- from: codeql/javascript-queries
  query: Expressions/DuplicateSwitchCase.ql
- from: codeql/javascript-queries
  query: Declarations/DuplicateVarDecl.ql
- from: codeql/javascript-queries
  query: DOM/DuplicateAttributes.ql
- from: codeql/javascript-queries
  query: AngularJS/DuplicateDependency.ql
- from: codeql/javascript-queries
  query: RegExp/DuplicateCharacterInCharacterClass.ql
"@

$pythonSuitePath = Join-Path $suitesDir "python-duplicates.qls"
$jsSuitePath    = Join-Path $suitesDir "javascript-duplicates.qls"

$pythonSuite | Set-Content -Path $pythonSuitePath -Encoding UTF8
$jsSuite     | Set-Content -Path $jsSuitePath -Encoding UTF8

Write-Host "Project: $projectPath" -ForegroundColor Cyan
Write-Host "Database directory: $databaseDir" -ForegroundColor Cyan
Write-Host "Results directory: $resultsDir" -ForegroundColor Cyan
Write-Host "Suites directory: $suitesDir" -ForegroundColor Cyan

# Function to run CodeQL analysis for a language
function Invoke-CodeQLAnalysis {
    param($Language, $DatabaseName)

    Write-Host "`nAnalyzing $Language code..." -ForegroundColor Yellow

    try {
        # Create database with exclusions for library directories
        Write-Host "Creating $Language database..." -ForegroundColor Cyan
        & codeql database create "$databaseDir\$DatabaseName" --language="$Language" --source-root="$projectPath" --overwrite

        if ($LASTEXITCODE -eq 0) {
            Write-Host "Database created successfully" -ForegroundColor Green

            # Run analysis with security suite
            Write-Host "Running security analysis..." -ForegroundColor Cyan
            & codeql database analyze "$databaseDir\$DatabaseName" "codeql/$Language-queries" --format=sarif-latest --output="$resultsDir\$DatabaseName-security-$timestamp.sarif"

            if ($LASTEXITCODE -eq 0) {
                Write-Host "Analysis completed successfully" -ForegroundColor Green

                # Run additional code scanning queries
                Write-Host "Running code scanning queries..." -ForegroundColor Cyan
                & codeql database analyze "$databaseDir\$DatabaseName" "codeql/$Language-queries" --format=csv --output="$resultsDir\$DatabaseName-scanning-$timestamp.csv"

                if ($LASTEXITCODE -eq 0) {
                    Write-Host "Code scanning completed" -ForegroundColor Green
                } else {
                    Write-Host "Code scanning failed (non-critical)" -ForegroundColor Yellow
                }

                # Run duplicate-code detection using custom suites
                try {
                    Write-Host "Running duplicate code detection..." -ForegroundColor Cyan
                    $suitePath = if ($Language -eq "python") { "$suitesDir\python-duplicates.qls" } else { "$suitesDir\javascript-duplicates.qls" }
                    & codeql database analyze "$databaseDir\$DatabaseName" $suitePath --format=sarif-latest --output="$resultsDir\$DatabaseName-duplicates-$timestamp.sarif"

                    if ($LASTEXITCODE -eq 0) {
                        Write-Host "Duplicate code detection completed" -ForegroundColor Green
                    } else {
                        Write-Host "Duplicate code detection failed (non-critical)" -ForegroundColor Yellow
                    }
                } catch {
                    Write-Host "Error during duplicate code detection: $_" -ForegroundColor Yellow
                }

                # Run additional manual duplicate detection for better coverage
                try {
                    Write-Host "Running enhanced duplicate detection with lower thresholds..." -ForegroundColor Cyan

                    # Create custom query for similarity-based duplicates with lower thresholds
                    $customQueryDir = "custom-queries"
                    New-Item -ItemType Directory -Force -Path $customQueryDir | Out-Null

                    if ($Language -eq "python") {
                        $customPythonQuery = @"
/**
 * @name Similar functions (relaxed threshold)
 * @description Find functions that are very similar to each other
 * @kind problem
 * @problem.severity recommendation
 * @precision medium
 * @id py/similar-function-relaxed
 * @tags maintainability
 *       duplicate-code
 */

import python

from Function f1, Function f2
where f1 != f2
  and f1.getLocation().getFile() = f2.getLocation().getFile()
  and f1.getNumLines() > 5
  and f2.getNumLines() > 5
  and f1.getName() != f2.getName()
  and exists(string s1, string s2 |
    s1 = f1.getABodyStmt().toString() and
    s2 = f2.getABodyStmt().toString() and
    s1 = s2
  )
select f1, "This function appears very similar to $@.", f2, f2.getName()
"@
                        $customPythonQuery | Set-Content -Path "$customQueryDir\similar-functions.ql" -Encoding UTF8

                        Write-Host "Running custom similarity query for Python..." -ForegroundColor Cyan
                        & codeql database analyze "$databaseDir\$DatabaseName" "$customQueryDir\similar-functions.ql" --format=sarif-latest --output="$resultsDir\$DatabaseName-similar-$timestamp.sarif" 2>$null
                    }

                    if ($LASTEXITCODE -eq 0) {
                        Write-Host "Enhanced duplicate detection completed" -ForegroundColor Green
                    } else {
                        Write-Host "Enhanced duplicate detection had issues (non-critical)" -ForegroundColor Yellow
                    }
                } catch {
                    Write-Host "Error during enhanced duplicate detection: $_" -ForegroundColor Yellow
                }

                return $true
            } else {
                Write-Host "Analysis failed" -ForegroundColor Red
                return $false
            }
        } else {
            Write-Host "Database creation failed" -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "Error during $Language analysis: $_" -ForegroundColor Red
        return $false
    }
}

# Test CodeQL
Write-Host "`nTesting CodeQL installation..." -ForegroundColor Cyan
try {
    $version = & codeql version 2>&1
    Write-Host "CodeQL Version: $($version[0])" -ForegroundColor Green
} catch {
    Write-Host "CodeQL not found! Please ensure it's installed and in PATH" -ForegroundColor Red
    exit 1
}

# Languages to analyze
$languages = @(
    @{Language="python"; DatabaseName="dinoair-python"},
    @{Language="javascript"; DatabaseName="dinoair-javascript"}
)

$successCount = 0
$totalCount = $languages.Count

# Run analysis for each language
foreach ($config in $languages) {
    if (Invoke-CodeQLAnalysis -Language $config.Language -DatabaseName $config.DatabaseName) {
        $successCount++
    }
}

# Summary
Write-Host "`nAnalysis Summary" -ForegroundColor Green
Write-Host "================" -ForegroundColor Green
Write-Host "Successful analyses: $successCount/$totalCount" -ForegroundColor Cyan
Write-Host "Results saved to: $resultsDir" -ForegroundColor Cyan

if ($successCount -gt 0) {
    Write-Host "`nGenerated files:" -ForegroundColor Yellow
    Get-ChildItem $resultsDir -Name | ForEach-Object {
        Write-Host "  - $_" -ForegroundColor White
    }

    Write-Host "`nTo view SARIF results:" -ForegroundColor Yellow
    Write-Host "1. Install SARIF Viewer extension in VS Code" -ForegroundColor White
    Write-Host "2. Open .sarif files to view security findings" -ForegroundColor White
    Write-Host "3. Check .csv files for detailed code scanning results" -ForegroundColor White

    # Generate concise Markdown report for duplicate-code findings across languages
    try {
        $dupSarifs = Get-ChildItem $resultsDir -Filter "*-duplicates-$timestamp.sarif" -File -ErrorAction SilentlyContinue
        if ($dupSarifs -and $dupSarifs.Count -gt 0) {
            $mdPath = Join-Path $resultsDir "duplicate-code-summary-$timestamp.md"
            $lines = @(
                "# Duplicate Code Findings ($timestamp)",
                "",
                "| Language | File | Line | Rule | Message |",
                "|---|---|---:|---|---|"
            )
            foreach ($file in $dupSarifs) {
                $lang = if ($file.Name -like "*python*") { "Python" } else { "JavaScript/TypeScript" }
                $sarif = Get-Content $file.FullName -Raw | ConvertFrom-Json
                if ($sarif.runs -and $sarif.runs.Count -gt 0 -and $sarif.runs[0].results) {
                    foreach ($r in $sarif.runs[0].results) {
                        $ruleId = $r.ruleId
                        $msg = ($r.message.text | Out-String).Trim() -replace "\r?\n"," " -replace "\|","/"
                        if ($r.locations -and $r.locations.Count -gt 0) {
                            $loc = $r.locations[0]
                            $uri = $loc.physicalLocation.artifactLocation.uri
                            $line = $loc.physicalLocation.region.startLine
                            $lines += "| $lang | $uri | $line | $ruleId | $msg |"
                        } else {
                            $lines += "| $lang | - | - | $ruleId | $msg |"
                        }
                    }
                } else {
                    $lines += "| $lang | - | - | - | No duplicate code findings |"
                }
            }
            $lines | Set-Content -Path $mdPath -Encoding UTF8
            Write-Host "`nDuplicate code summary written to: $mdPath" -ForegroundColor Yellow
        } else {
            Write-Host "`nNo duplicate-code SARIF files found to summarize." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Failed to generate duplicate code Markdown summary: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "No successful analyses completed" -ForegroundColor Red
}

Write-Host "`nDone!" -ForegroundColor Green