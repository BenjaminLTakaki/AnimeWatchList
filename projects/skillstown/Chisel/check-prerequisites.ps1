# Chisel Prerequisites Checker
# Run this to verify all requirements are met before starting Chisel

Write-Host "🔍 Chisel Prerequisites Checker" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

# Function to check if a command exists
function Test-Command($cmdname) {
    return [bool](Get-Command -Name $cmdname -ErrorAction SilentlyContinue)
}

# Function to test HTTP endpoint
function Test-HttpEndpoint($url, $name) {
    try {
        $response = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 5 -ErrorAction Stop
        Write-Host "✅ $name is accessible" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "❌ $name is not accessible: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

$allGood = $true

# Check Go installation
Write-Host "`n📦 Checking Go installation..." -ForegroundColor Yellow
if (Test-Command go) {
    $goVersion = go version
    Write-Host "✅ Go is installed: $goVersion" -ForegroundColor Green
} else {
    Write-Host "❌ Go is not installed or not in PATH" -ForegroundColor Red
    Write-Host "   Install with: .\install-prerequisites.ps1" -ForegroundColor Yellow
    $allGood = $false
}

# Check Docker installation
Write-Host "`n🐳 Checking Docker installation..." -ForegroundColor Yellow
if (Test-Command docker) {
    try {
        $dockerVersion = docker --version
        Write-Host "✅ Docker is installed: $dockerVersion" -ForegroundColor Green
        
        # Check if Docker is running
        docker info | Out-Null
        Write-Host "✅ Docker is running" -ForegroundColor Green
    } catch {
        Write-Host "❌ Docker is installed but not running" -ForegroundColor Red
        Write-Host "   Please start Docker Desktop" -ForegroundColor Yellow
        $allGood = $false
    }
} else {
    Write-Host "❌ Docker is not installed or not in PATH" -ForegroundColor Red
    Write-Host "   Install with: .\install-prerequisites.ps1" -ForegroundColor Yellow
    $allGood = $false
}

# Check .env file
Write-Host "`n⚙️  Checking environment configuration..." -ForegroundColor Yellow
if (Test-Path ".env") {
    Write-Host "✅ .env file exists" -ForegroundColor Green
    
    # Check if API keys are set
    $envContent = Get-Content ".env" | Where-Object { $_ -notmatch "^#" -and $_ -ne "" }
    $openaiKey = $envContent | Where-Object { $_ -match "OPENAI_API_KEY=" }
    $groqKey = $envContent | Where-Object { $_ -match "GROQ_API_KEY=" }
    
    if ($openaiKey -and $openaiKey -notmatch "your_actual_openai_key") {
        Write-Host "✅ OpenAI API key is configured" -ForegroundColor Green
    } else {
        Write-Host "⚠️  OpenAI API key needs to be updated in .env file" -ForegroundColor Yellow
    }
    
    if ($groqKey -and $groqKey -notmatch "your_actual_groq_key") {
        Write-Host "✅ Groq API key is configured" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Groq API key needs to be updated in .env file" -ForegroundColor Yellow
    }
} else {
    Write-Host "❌ .env file not found" -ForegroundColor Red
    $allGood = $false
}

# Check if Qdrant is running
Write-Host "`n🗄️  Checking Qdrant database..." -ForegroundColor Yellow
$qdrantRunning = Test-HttpEndpoint "https://qdrant-vector-db-t8ao.onrender.com/" "Qdrant"
if (-not $qdrantRunning) {
    Write-Host "   Run: docker-compose up -d" -ForegroundColor Yellow
}

# Check Go module dependencies
Write-Host "`n📚 Checking Go dependencies..." -ForegroundColor Yellow
if (Test-Path "go.mod") {
    try {
        go mod verify | Out-Null
        Write-Host "✅ Go dependencies are valid" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  Go dependencies may need updating" -ForegroundColor Yellow
        Write-Host "   Run: go mod tidy" -ForegroundColor Yellow
    }
} else {
    Write-Host "❌ go.mod file not found" -ForegroundColor Red
    $allGood = $false
}

# Summary
Write-Host "`n📊 Summary" -ForegroundColor Cyan
Write-Host "==========" -ForegroundColor Cyan

if ($allGood -and $qdrantRunning) {
    Write-Host "✅ All prerequisites are met!" -ForegroundColor Green
    Write-Host "`n🚀 You can now run:" -ForegroundColor Cyan
    Write-Host "   go build -o chisel.exe ." -ForegroundColor White
    Write-Host "   .\chisel.exe" -ForegroundColor White
    Write-Host "`nOr use the automated setup:" -ForegroundColor Cyan
    Write-Host "   .\setup.ps1" -ForegroundColor White
} elseif ($allGood -and -not $qdrantRunning) {
    Write-Host "⚠️  Almost ready! Just start Qdrant:" -ForegroundColor Yellow
    Write-Host "   docker-compose up -d" -ForegroundColor White
    Write-Host "`nThen run:" -ForegroundColor Cyan
    Write-Host "   .\setup.ps1" -ForegroundColor White
} else {
    Write-Host "❌ Some prerequisites are missing" -ForegroundColor Red
    Write-Host "`n🛠️  To fix issues:" -ForegroundColor Cyan
    Write-Host "   .\install-prerequisites.ps1  # Install Go/Docker" -ForegroundColor White
    Write-Host "   # Update API keys in .env file" -ForegroundColor White
    Write-Host "   docker-compose up -d         # Start Qdrant" -ForegroundColor White
    Write-Host "   .\check-prerequisites.ps1    # Run this again" -ForegroundColor White
}
