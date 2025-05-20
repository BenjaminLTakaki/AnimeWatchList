# Spotify Playlist Cover Generator (Gemini + Stable Diffusion API Version)

An AI-powered web application that analyzes Spotify playlists and generates custom album artwork and titles based on the musical genres detected, using Google's Gemini API and Stable Diffusion API.

## Features

### Core Features
- Analyzes Spotify playlists or albums to extract artist genres
- Generates custom album covers using Stable Diffusion API
- Creates unique album titles with Google Gemini 2.5 Flash Preview API
- Visualizes genre distribution with interactive charts

### Enhanced Features
- **Custom LoRA Support**: Use LoRAs via uploads or direct URLs (including Civitai links)
- **Preset Style Selection**: Quick buttons for different visual styles (Minimalist, High Contrast, Retro, Bold Colors)
- **Genre Percentage Visualization**: Visual breakdown of genres with colored progress bars
- **Cover Regeneration**: Regenerate new covers with the same playlist without starting over
- **Copy Functionality**: Download generated covers and copy titles with a single click
- **Loading States**: Visual feedback during the generation process

## Requirements
- Python 3.8+
- Flask
- Spotipy (Spotify API client)
- Matplotlib (for visualization)
- API Keys:
  - Spotify API credentials
  - Google Gemini API key
  - Stable Diffusion API key

## Setup

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file with your API credentials:
   ```
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   GEMINI_API_KEY=your_gemini_api_key
   STABLE_DIFFUSION_API_KEY=your_stablediffusion_api_key
   FLASK_SECRET_KEY=random_secret_key_for_flask
   ```

4. Run the application:
   ```
   python app.py
   ```

## Usage

1. Enter a Spotify playlist or album URL
2. (Optional) Select a preset style or enter a custom mood
3. (Optional) Choose a LoRA for custom styling:
   - Select a saved LoRA from the dropdown
   - OR enter a direct URL to a LoRA file or Civitai model page
4. Click "Generate Cover" and wait for the magic to happen
5. View your custom album cover, title, and genre analysis
6. Use the "Regenerate Cover" button to create variations with the same playlist
7. Download your cover or copy the title to use elsewhere

## LoRA Usage Options

The application supports multiple ways to use LoRAs (Low-Rank Adaptations):

### Local LoRA Files
1. Use the "Upload File" tab to upload your .safetensors, .ckpt, or .pt files
2. After uploading, the LoRA will appear in the dropdown for future use

### LoRA via URL (saved)
1. Use the "Add Via Link" tab to add a LoRA from an external URL
2. You can provide a name or let the system extract one from the URL
3. Adjust the LoRA strength as needed
4. The LoRA will be saved for future use in the dropdown

### Direct LoRA URL (one-time use)
1. Enter a URL directly in the LoRA URL field (instead of using the dropdown)
2. Supported URL types:
   - Direct links to .safetensors files
   - Civitai model pages (e.g., https://civitai.com/models/12345/my-lora)
   - Hugging Face model repositories
3. The LoRA will be used for the current generation only

### Supported URL Types
- **Civitai Model Pages**: Links to model pages on Civitai.com
- **Direct File URLs**: Links ending with .safetensors, .ckpt, or .pt
- **Hugging Face Models**: Links to models on Hugging Face

## API Endpoints

The application provides the following API endpoints:

- `GET /status` - Check system status
- `POST /api/generate` - Generate a cover programmatically
- `POST /api/regenerate` - Regenerate a cover with the same playlist
- `GET /api/loras` - Get list of available LoRAs
- `POST /api/upload_lora` - Upload a new LoRA file
- `POST /api/add_lora_link` - Add a LoRA via URL

## CLI Usage

You can also use the application via command line:

```
# Generate a cover with local LoRA
python app.py --generate <spotify_url> [mood] [lora_name]

# Generate a cover with LoRA URL
python app.py --generate <spotify_url> [mood] [https://example.com/lora.safetensors]

# Start web server
python app.py

# Show help
python app.py --help
```

## Notes on API Keys

- **Spotify API**: Create an app in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/applications)
- **Gemini API**: Get a key from [Google AI Studio](https://makersuite.google.com/app/apikey)
- **Stable Diffusion API**: Register for a free account at [stablediffusionapi.com](https://stablediffusionapi.com/)

## Limitations

- **Stable Diffusion API Free Tier**: Has limited generations per day
- **LoRA Support**: Some LoRAs may not work with the free tier API; direct file URLs work best
- **Civitai Integration**: Basic support for model pages, but may not extract all trigger words

## License
MIT License