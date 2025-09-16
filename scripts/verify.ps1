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
$ProjectRoot = (Get-Item -Path "." -Verbose).FullName
$ServerScript = Join-Path $ProjectRoot "scripts\server.bat"
$CliScript = Join-Path $ProjectRoot "scripts\cli.bat"
$Port = 8000
$HealthCheckUrl = "http://127.0.0.1:$Port/"
$TestPrompt = "From the installation steps described in README.md, make me a 1970s wood and brushed aluminum themed animated web page with active checklist boxes. Iterate on the page at least twice, checking with the systems architect between iterations."
$TimeoutSeconds = 30

# --- Check for jq dependency ---
# PowerShell doesn't have a direct equivalent of 'command -v'.
# We check if jq.exe exists in any of the directories listed in the PATH environment variable.
$jqFound = $false
$env:Path.Split(';') | ForEach-Object {
    $jqPath = Join-Path $_ "jq.exe"
    if (Test-Path $jqPath) {
        $jqFound = $true
    }
}

if (-not $jqFound) {
    Write-Host "Error: jq is not installed or not found in your PATH. Please install jq to run this verification script."
    Write-Host "Download from: https://stedolan.github.io/jq/download/"
    exit 1
}

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
    
    # Run the CLI script with --json-only flag and capture its output
    Write-Host "--- Running CLI verification test ---"
    # Use the 'stream' command with '--json-only' to test the streaming endpoint.
    # The command will output live logs (which we ignore here) and then the final
    # JSON state object on the last line, which is what we capture.
    $cliOutputLines = & $CliScript stream --json-only $TestPrompt

    # The output might be an array of strings (if there were logs) or a single string.
    # We are interested in the last line, which should be the final JSON state.
    if ($cliOutputLines -is [array]) {
        $cliOutput = $cliOutputLines[-1]
    } else {
        $cliOutput = $cliOutputLines
    }

    # Check if JSON_RESPONSE is empty or not valid JSON
    if ([string]::IsNullOrEmpty($cliOutput)) {
        throw "Verification test FAILED: No JSON response received from CLI."
    }

    try {
        $jsonResponse = $cliOutput | ConvertFrom-Json
    }
    catch {
        throw "Verification test FAILED: CLI output was not valid JSON. Details: $($_.Exception.Message)"
    }

    # Validate the JSON response
    # A successful workflow will now produce a non-empty `user_response` string.
    # This is a more direct and reliable indicator of success.
    if (($jsonResponse.user_response -is [string]) -and `
        ($jsonResponse.user_response.Length -gt 0) -and `
        ($null -ne $jsonResponse.artifacts)) {
        
        Write-Host "---"
        Write-Host "✅ Verification test PASSED: Agent returned a meaningful response and routed successfully." -ForegroundColor Green
        exit 0
    } else {
        Write-Host "---"
        Write-Host "❌ Verification test FAILED: Agent response was not meaningful or routing failed." -ForegroundColor Red
        Write-Host "JSON Response:" -ForegroundColor Red
        $jsonResponse | ConvertTo-Json -Depth 100 | Write-Host -ForegroundColor Red
        exit 1
    }
    
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
