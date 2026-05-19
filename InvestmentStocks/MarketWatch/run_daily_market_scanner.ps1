$ErrorActionPreference = "Stop"

# Optional email settings for scanner notifications.
# Replace placeholder values before first scheduled run.
$env:SCANNER_SMTP_HOST = "smtp.gmail.com"
$env:SCANNER_SMTP_PORT = "587"
$env:SCANNER_SMTP_USER = "your_email@gmail.com"
$env:SCANNER_SMTP_PASS = "your_app_password"
$env:SCANNER_FROM_EMAIL = "your_email@gmail.com"
$env:SCANNER_TO_EMAIL = "saratheas@gmail.com"

Set-Location "C:\Users\sarat\Downloads\GENAI\MarketWatch"
python daily_market_scanner.py
