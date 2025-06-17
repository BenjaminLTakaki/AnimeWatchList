# Spotify Cover Generator API Documentation

## Overview
The Spotify Cover Generator API provides endpoints for generating album/playlist covers based on Spotify playlists or albums using AI-powered image generation.

## Base URL
```
Production: https://your-app.render.com
Development: http://localhost:5000
```

## Authentication
Currently, the API uses Spotify OAuth for accessing Spotify data. No authentication is required for the cover generation endpoint.

## Endpoints

### Health Check
Check the application health status.

**Endpoint:** `GET /health`

**Response:**
```json
{
  "status": "healthy|degraded|unhealthy",
  "timestamp": "2025-06-17T10:30:00Z",
  "version": "1.0.0",
  "checks": {
    "database": "healthy",
    "spotify_api": "healthy",
    "gemini_api": "healthy",
    "stability_api": "healthy"
  },
  "uptime": "72h 15m 30s"
}
```

**Status Codes:**
- `200 OK`: System is healthy
- `503 Service Unavailable`: System is degraded or unhealthy

### Generate Cover
Generate an AI cover image for a Spotify playlist or album.

**Endpoint:** `POST /generate`

**Content-Type:** `application/x-www-form-urlencoded` or `multipart/form-data`

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `playlist_url` | string | Yes | Valid Spotify playlist or album URL |
| `mood` | string | No | Desired mood (energetic, calm, dark, bright, etc.) |
| `custom_prompt` | string | No | Additional custom prompt for image generation |
| `lora_model` | string | No | LoRA model to use for style |
| `strength` | float | No | LoRA strength (0.1-1.0, default: 0.8) |

**Example Request:**
```bash
curl -X POST https://your-app.render.com/generate \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "playlist_url=https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M&mood=energetic"
```

**Successful Response (200 OK):**
```json
{
  "success": true,
  "title": "Generated Album Title",
  "item_name": "Discover Weekly",
  "genres": ["pop", "rock", "indie"],
  "all_genres": ["pop", "rock", "indie", "electronic", "alternative"],
  "mood": "energetic",
  "spotify_url": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
  "image_data_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
  "output_path": "/tmp/generated_cover_123.png",
  "generation_time": 12.5,
  "lora_model_used": "artistic_style_v1"
}
```

**Error Response (400 Bad Request):**
```json
{
  "success": false,
  "error": "Invalid Spotify URL",
  "message": "The provided URL is not a valid Spotify playlist or album URL",
  "error_code": "INVALID_URL"
}
```

**Error Response (500 Internal Server Error):**
```json
{
  "success": false,
  "error": "Generation failed",
  "message": "Unable to generate cover due to API limitations",
  "error_code": "GENERATION_FAILED"
}
```

### Get LoRA Models
Retrieve available LoRA models for image generation.

**Endpoint:** `GET /api/lora-models`

**Response:**
```json
{
  "models": [
    {
      "name": "artistic_style_v1",
      "source_type": "local",
      "path": "/models/artistic_style_v1.safetensors",
      "trigger_words": ["artistic", "style"],
      "description": "Artistic painting style",
      "is_local": true
    },
    {
      "name": "cyberpunk_v2",
      "source_type": "link",
      "path": "https://huggingface.co/models/cyberpunk_v2",
      "trigger_words": ["cyberpunk", "neon"],
      "description": "Cyberpunk aesthetic",
      "is_local": false
    }
  ]
}
```

## Error Codes

| Code | Description |
|------|-------------|
| `INVALID_URL` | The Spotify URL is malformed or not supported |
| `SPOTIFY_ERROR` | Error accessing Spotify API |
| `GENERATION_FAILED` | Image generation failed |
| `API_LIMIT_EXCEEDED` | Rate limit exceeded for external APIs |
| `INVALID_PARAMETERS` | Invalid or missing required parameters |
| `INTERNAL_ERROR` | Unexpected server error |

## Rate Limiting
- **Cover Generation:** 10 requests per minute per IP
- **Health Check:** 60 requests per minute per IP
- **LoRA Models:** 30 requests per minute per IP

Rate limit headers are included in responses:
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1634567890
```

## Webhooks (Future Feature)
Webhook support for long-running generation tasks will be added in v2.0.

## SDKs and Libraries

### Python Example
```python
import requests
import base64

def generate_cover(playlist_url, mood="balanced"):
    response = requests.post(
        "https://your-app.render.com/generate",
        data={
            "playlist_url": playlist_url,
            "mood": mood
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        # Decode base64 image
        image_data = base64.b64decode(data["image_data_base64"])
        with open("cover.png", "wb") as f:
            f.write(image_data)
        return data
    else:
        raise Exception(f"Generation failed: {response.text}")

# Usage
result = generate_cover("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M", "energetic")
print(f"Generated: {result['title']}")
```

### JavaScript Example
```javascript
async function generateCover(playlistUrl, mood = "balanced") {
    const response = await fetch("https://your-app.render.com/generate", {
        method: "POST",
        headers: {
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams({
            playlist_url: playlistUrl,
            mood: mood
        })
    });
    
    if (!response.ok) {
        throw new Error(`Generation failed: ${await response.text()}`);
    }
    
    const data = await response.json();
    
    // Convert base64 to blob for download
    const imageBlob = await fetch(`data:image/png;base64,${data.image_data_base64}`).then(r => r.blob());
    
    return { ...data, imageBlob };
}

// Usage
generateCover("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M", "energetic")
    .then(result => console.log("Generated:", result.title))
    .catch(error => console.error("Error:", error));
```

## Monitoring and Debugging

### Health Monitoring
The `/health` endpoint provides detailed status information:
- Database connectivity
- External API availability
- System resource usage
- Application uptime

### Error Logging
All errors are logged with correlation IDs for debugging:
```json
{
  "timestamp": "2025-06-17T10:30:00Z",
  "level": "ERROR",
  "correlation_id": "req_abc123",
  "error": "Spotify API rate limit exceeded",
  "user_ip": "192.168.1.1",
  "playlist_url": "https://open.spotify.com/playlist/..."
}
```

## Changelog

### v1.0.0 (Current)
- Initial release
- Basic cover generation
- Spotify integration
- LoRA model support
- Health monitoring

### v1.1.0 (Planned)
- Batch generation
- Custom style templates
- Webhook support
- Advanced caching