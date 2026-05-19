$ErrorActionPreference = "Stop"

# Auto-open the digest in your default browser when the run finishes.
# Set this to "0" to skip opening (e.g. if you switch to email-only later).
$env:TPM_OPEN_IN_BROWSER = "1"

# --- Optional: enable email delivery ---
# Generate a Gmail App Password at https://myaccount.google.com/apppasswords
# (requires 2-Step Verification on the Google account) and uncomment to enable.
# $env:TPM_SMTP_HOST   = "smtp.gmail.com"
# $env:TPM_SMTP_PORT   = "587"
# $env:TPM_SMTP_USER   = "saratheas@gmail.com"
# $env:TPM_SMTP_PASS   = "REPLACE_WITH_GMAIL_APP_PASSWORD"
# $env:TPM_FROM_EMAIL  = "saratheas@gmail.com"
# $env:TPM_TO_EMAIL    = "saratheas@gmail.com"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Use the repo's venv python so deps resolve correctly.
$Python = Join-Path (Split-Path -Parent $ScriptDir) ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

# Python logs to logs\YYYY-MM-DD.log via its own FileHandler, so no PS-side redirection
# (PowerShell 5.1 wraps native stderr as NativeCommandError when redirecting all streams).
& $Python tpm_job_agent.py
exit $LASTEXITCODE
