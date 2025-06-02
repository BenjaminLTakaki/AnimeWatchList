# Test Script for SkillsTown Podcast Integration
# This script tests the API endpoints to ensure everything is working

Write-Host "🧪 Testing SkillsTown Podcast Integration" -ForegroundColor Green

# Test 1: Check if services are running
Write-Host "`n📊 Testing service availability..." -ForegroundColor Yellow

# Test Qdrant
try {
    $qdrantResponse = Invoke-WebRequest -Uri "http://localhost:6333/health" -Method GET -TimeoutSec 5
    if ($qdrantResponse.StatusCode -eq 200) {
        Write-Host "✅ Qdrant is running (Port 6333)" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ Qdrant is not responding (Port 6333)" -ForegroundColor Red
}

# Test Chisel
try {
    $chiselResponse = Invoke-WebRequest -Uri "http://localhost:8080/health" -Method GET -TimeoutSec 5
    if ($chiselResponse.StatusCode -eq 200) {
        Write-Host "✅ Chisel is running (Port 8080)" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ Chisel is not responding (Port 8080)" -ForegroundColor Red
    Write-Host "   Try: cd C:\Users\benta\Desktop\Chisel\chisel && go run ." -ForegroundColor Yellow
}

# Test NarreteX
try {
    $narretexResponse = Invoke-WebRequest -Uri "http://localhost:8100/health" -Method GET -TimeoutSec 5
    if ($narretexResponse.StatusCode -eq 200) {
        Write-Host "✅ NarreteX is running (Port 8100)" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ NarreteX is not responding (Port 8100)" -ForegroundColor Red
    Write-Host "   Try: cd C:\Users\benta\Desktop\Narretex\Narretex && go run ." -ForegroundColor Yellow
}

# Test SkillsTown
try {
    $skillstownResponse = Invoke-WebRequest -Uri "http://localhost:5000" -Method GET -TimeoutSec 5
    if ($skillstownResponse.StatusCode -eq 200) {
        Write-Host "✅ SkillsTown is running (Port 5000)" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ SkillsTown is not responding (Port 5000)" -ForegroundColor Red
    Write-Host "   Try: cd c:\Users\benta\Desktop\portfolio_website\AnimeWatchList\projects\skillstown && python app.py" -ForegroundColor Yellow
}

# Test 2: Check SkillsTown podcast endpoint (requires authentication)
Write-Host "`n🎙️ Testing podcast endpoint..." -ForegroundColor Yellow
Write-Host "   Note: This requires a logged-in session, so test manually in browser" -ForegroundColor Cyan

# Test 3: Display integration summary
Write-Host "`n📋 Integration Summary:" -ForegroundColor Yellow
Write-Host "   ✅ Added /generate-podcast route to app.py" -ForegroundColor Green
Write-Host "   ✅ Updated course_detail.html with podcast button" -ForegroundColor Green
Write-Host "   ✅ Updated my_courses.html with podcast dropdown" -ForegroundColor Green
Write-Host "   ✅ Added JavaScript for audio playback" -ForegroundColor Green
Write-Host "   ✅ Added requests dependency to requirements.txt" -ForegroundColor Green

Write-Host "`n🎯 Next Steps:" -ForegroundColor Yellow
Write-Host "   1. Ensure all services are running (use start_services.ps1)" -ForegroundColor White
Write-Host "   2. Open http://localhost:5000 in your browser" -ForegroundColor White
Write-Host "   3. Login and test podcast generation on a course" -ForegroundColor White

Write-Host "`n🔧 Manual Testing Checklist:" -ForegroundColor Yellow
Write-Host "   □ Login to SkillsTown successfully" -ForegroundColor White
Write-Host "   □ Navigate to My Courses page" -ForegroundColor White
Write-Host "   □ Click dropdown → Generate Podcast (should download)" -ForegroundColor White
Write-Host "   □ Visit course detail page" -ForegroundColor White
Write-Host "   □ Click 'Create Podcast' button (should show audio player)" -ForegroundColor White
Write-Host "   □ Verify audio plays correctly" -ForegroundColor White
Write-Host "   □ Test download functionality" -ForegroundColor White

Read-Host "Press Enter to exit..."
