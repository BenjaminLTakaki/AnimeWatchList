# Chisel Setup Script (Clean Version)
# This script will set up and run the entire Chisel application

Write-Host "🚀 Starting Chisel Setup" -ForegroundColor Cyan
Write-Host "========================" -ForegroundColor Cyan

# Step 1: Start Qdrant database
Write-Host "`n🗄️ Starting Qdrant database..." -ForegroundColor Yellow
try {
    docker-compose up -d
    Write-Host "✅ Qdrant database started successfully" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed to start Qdrant database" -ForegroundColor Red
    Write-Host "Make sure Docker is installed and running" -ForegroundColor Yellow
    exit 1
}

# Step 2: Wait for Qdrant to be ready
Write-Host "`n⏳ Waiting for Qdrant to be ready..." -ForegroundColor Yellow
$maxAttempts = 30
$attempt = 0
do {
    try {
        $response = Invoke-RestMethod -Uri "https://qdrant-vector-db-t8ao.onrender.com/" -Method Get -TimeoutSec 2 -ErrorAction Stop
        Write-Host "✅ Qdrant is ready!" -ForegroundColor Green
        break
    } catch {
        $attempt++
        if ($attempt -ge $maxAttempts) {
            Write-Host "❌ Qdrant failed to start within timeout" -ForegroundColor Red
            exit 1
        }
        Write-Host "." -NoNewline -ForegroundColor Yellow
        Start-Sleep -Seconds 2
    }
} while ($true)

# Step 3: Install Go dependencies
Write-Host "`n📚 Installing Go dependencies..." -ForegroundColor Yellow
try {
    go mod tidy
    Write-Host "✅ Go dependencies installed" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed to install Go dependencies" -ForegroundColor Red
    exit 1
}

# Step 4: Build the application
Write-Host "`n🔨 Building Chisel application..." -ForegroundColor Yellow
try {
    go build -o chisel.exe .
    Write-Host "✅ Chisel built successfully" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed to build Chisel" -ForegroundColor Red
    exit 1
}

# Step 5: Start the application
Write-Host "`n🚀 Starting Chisel API server..." -ForegroundColor Yellow
Write-Host "API will be available at: http://localhost:8080" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

try {
    .\chisel.exe
} catch {
    Write-Host "Failed to start Chisel server" -ForegroundColor Red
    exit 1
}
