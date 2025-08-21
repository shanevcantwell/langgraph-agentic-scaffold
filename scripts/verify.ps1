<#
.SYNOPSIS
    Runs a basic end-to-end sanity check of the agentic system for Windows.
.DESCRIPTION
    This script starts the server, waits for it to become healthy, sends a test 
    prompt via the CLI, and then reliably stops the server. It is the Windows
    equivalent of verify.sh.
.EXAMPLE
    .\scripts\verify.ps1
    Starts the server, runs the test, and stops the server, reporting success or failure.
#>

# --- Configuration ---
$ProjectRoot = (Get-Item -Path ".\" -Verbose).FullName
$ServerScript = Join-Path $ProjectRoot "scripts\server.bat"
$CliScript = Join-Path $ProjectRoot "scripts\cli.bat"
$Port = 8000
$HealthCheckUrl = "http://127.0.0.1:$Port/"
$TestPrompt = "Hello, world! Please respond with a simple confirmation."
$TimeoutSeconds = 30

# --- Main Logic ---
try {
    Write-Host "--- Starting server for verification test ---"
    # Start the server in the background.
    Start-Process -FilePath $ServerScript -ArgumentList "start" -WindowStyle Hidden
    
    Write-Host "--- Waiting for server to become healthy (max $TimeoutSeconds seconds) ---"
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $serverReady = $false
    
    while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        try {
            # Use Invoke-WebRequest to check the health endpoint.
            $response = Invoke-WebRequest -Uri $HealthCheckUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                Write-Host ""
                Write-Host "Server is up and running."
                $serverReady = $true
                break
            }
        }
        catch {
            # Suppress errors while waiting for the server to start
        }
        Write-Host -NoNewline "."
        Start-Sleep -Seconds 1
    }
    
    if (-not $serverReady) {
        Write-Host ""
        throw "Verification test FAILED: Server did not become healthy within $TimeoutSeconds seconds."
    }
    
    # Run the CLI script and check its exit code
    Write-Host "--- Running CLI verification test ---"
    & $CliScript $TestPrompt
    
    if ($LASTEXITCODE -ne 0) {
        throw "Verification test FAILED: CLI script returned a non-zero exit code."
    }
    
    Write-Host "---"
    Write-Host "✅ Verification test PASSED." -ForegroundColor Green
    
}
catch {
    Write-Host ""
    Write-Host "❌ $_" -ForegroundColor Red
    Write-Host "Check server logs for errors: .\logs\agentic_server.log"
    # Exit with a non-zero status code to indicate failure
    exit 1
}
finally {
    Write-Host "---"
    Write-Host "Running cleanup: stopping server..."
    # Use the server script to stop.
    & $ServerScript stop
    Write-Host "Cleanup complete."
}