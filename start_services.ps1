# SkillsTown Local Development Setup Script
# This script starts all required services for the podcast generation feature

Write-Host "🚀 Starting SkillsTown Local Development Environment" -ForegroundColor Green

# Check if Qdrant is running
Write-Host "📊 Checking Qdrant status..." -ForegroundColor Yellow
$qdrantRunning = docker ps | Select-String "qdrant"
if ($qdrantRunning) {
    Write-Host "✅ Qdrant is already running" -ForegroundColor Green
} else {
    Write-Host "❌ Qdrant not found. Please start Qdrant first:" -ForegroundColor Red
    Write-Host "   docker run -p 6333:6333 qdrant/qdrant" -ForegroundColor Cyan
    exit 1
}

# Function to start service in new terminal
function Start-ServiceInNewTerminal {
    param(
        [string]$Title,
        [string]$Path,
        [string]$Command,
        [int]$Port
    )
    
    Write-Host "🔄 Starting $Title..." -ForegroundColor Yellow
    
    # Check if port is already in use
    $portCheck = netstat -an | Select-String ":$Port "
    if ($portCheck) {
        Write-Host "⚠️  Port $Port is already in use. $Title might already be running." -ForegroundColor Yellow
        return
    }
    
    # Start the service in a new PowerShell window
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$Path'; Write-Host 'Starting $Title on port $Port...' -ForegroundColor Green; $Command"
    
    Write-Host "✅ $Title started in new terminal" -ForegroundColor Green
    Start-Sleep -Seconds 2
}

# Start Chisel (Document Processing)
Start-ServiceInNewTerminal -Title "Chisel" -Path "C:\Users\benta\Desktop\Chisel\chisel" -Command "go run ." -Port 8080

# Start NarreteX (Podcast Generation)
Start-ServiceInNewTerminal -Title "NarreteX" -Path "C:\Users\benta\Desktop\Narretex\Narretex" -Command "go run ." -Port 8100

# Wait a moment for services to initialize
Write-Host "⏳ Waiting for services to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Install Python dependencies for SkillsTown
Write-Host "📦 Installing SkillsTown dependencies..." -ForegroundColor Yellow
cd "c:\Users\benta\Desktop\portfolio_website\AnimeWatchList\projects\skillstown"
pip install -r requirements.txt

# Set environment variables for local development
$env:CHISEL_URL = "http://localhost:8080"
$env:NARRETEX_URL = "http://localhost:8100"
$env:FLASK_ENV = "development"
$env:FLASK_DEBUG = "1"

Write-Host "🌐 Environment variables set:" -ForegroundColor Green
Write-Host "   CHISEL_URL: $env:CHISEL_URL" -ForegroundColor Cyan
Write-Host "   NARRETEX_URL: $env:NARRETEX_URL" -ForegroundColor Cyan

# Start SkillsTown
Write-Host "🎓 Starting SkillsTown..." -ForegroundColor Yellow
Start-ServiceInNewTerminal -Title "SkillsTown" -Path "c:\Users\benta\Desktop\portfolio_website\AnimeWatchList\projects\skillstown" -Command "python app.py" -Port 5000

Write-Host "" -ForegroundColor White
Write-Host "🎉 All services started successfully!" -ForegroundColor Green
Write-Host "" -ForegroundColor White
Write-Host "📋 Service URLs:" -ForegroundColor Yellow
Write-Host "   🔧 Chisel (Document Processing): http://localhost:8080" -ForegroundColor Cyan
Write-Host "   🎙️  NarreteX (Podcast Generation): http://localhost:8100" -ForegroundColor Cyan
Write-Host "   🎓 SkillsTown (Main App): http://localhost:5000" -ForegroundColor Cyan
Write-Host "" -ForegroundColor White
Write-Host "📝 Testing Steps:" -ForegroundColor Yellow
Write-Host "   1. Open http://localhost:5000 in your browser" -ForegroundColor White
Write-Host "   2. Login to your SkillsTown account" -ForegroundColor White
Write-Host "   3. Navigate to 'My Courses' or view a specific course" -ForegroundColor White
Write-Host "   4. Click 'Create Podcast' button" -ForegroundColor White
Write-Host "   5. Wait 30-60 seconds for generation" -ForegroundColor White
Write-Host "   6. Audio player should appear with your podcast" -ForegroundColor White
Write-Host "" -ForegroundColor White
Write-Host "🔧 Troubleshooting:" -ForegroundColor Yellow
Write-Host "   - If podcast generation fails, check that all services are running" -ForegroundColor White
Write-Host "   - Check the SkillsTown terminal for error messages" -ForegroundColor White
Write-Host "   - Verify NarreteX is responding at http://localhost:8100" -ForegroundColor White

Read-Host "Press Enter to exit..."
