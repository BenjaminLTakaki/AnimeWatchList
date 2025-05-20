// Updated JavaScript for handling form and UI functionality
document.addEventListener('DOMContentLoaded', function() {
    // Add visual feedback when pasting Spotify URL
    const playlistUrlInput = document.getElementById('playlist_url');
    if (playlistUrlInput) {
        // Check if input has value when page loads (e.g. after error)
        if (playlistUrlInput.value.trim() !== '') {
            playlistUrlInput.classList.add('has-value');
        }
        // Add validation for Spotify URLs
        playlistUrlInput.addEventListener('input', function() {
            const value = this.value.trim();
            if (value !== '') {
                this.classList.add('has-value');
                // Validation for Spotify playlist or album URL format
                if (value.includes('open.spotify.com/playlist/') || value.includes('open.spotify.com/album/')) {
                    this.classList.remove('invalid');
                    this.classList.add('valid');
                } else {
                    this.classList.remove('valid');
                    this.classList.add('invalid');
                }
            } else {
                this.classList.remove('has-value');
                this.classList.remove('valid');
                this.classList.remove('invalid');
            }
        });
    }
    
    // Add loading state to form submission
    const form = document.querySelector('form');
    if (form) {
        form.addEventListener('submit', function() {
            const submitButton = this.querySelector('.submit-btn');
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.innerHTML = 'Generating... <span class="spinner"></span>';
                submitButton.classList.add('loading');
            }
            // Create a loading overlay
            const loadingOverlay = document.createElement('div');
            loadingOverlay.className = 'loading-overlay';
            loadingOverlay.innerHTML = `
                <div class="loading-content">
                    <div class="loading-spinner"></div>
                    <p>Analyzing music and generating cover art...</p>
                    <p class="loading-subtext">This may take a minute or two</p>
                </div>
            `;
            document.body.appendChild(loadingOverlay);
            
            // Allow form submission to continue
            return true;
        });
    }
    
    // On result page, add animation for cover reveal
    const albumCover = document.querySelector('.album-cover');
    if (albumCover) {
        // Add fade-in animation when image loads
        albumCover.style.opacity = '0';
        albumCover.addEventListener('load', function() {
            setTimeout(() => {
                albumCover.style.transition = 'opacity 1s ease-in-out';
                albumCover.style.opacity = '1';
            }, 300);
        });
    }
    
    // LoRA file upload handling
    const loraUploadForm = document.getElementById('lora-upload-form');
    if (loraUploadForm) {
        loraUploadForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const uploadStatus = document.getElementById('upload-status');
            
            // Validate file
            const fileInput = document.getElementById('lora_file');
            if (!fileInput.files.length) {
                uploadStatus.textContent = 'Please select a file to upload';
                uploadStatus.className = 'error';
                return;
            }
            
            const file = fileInput.files[0];
            const validExtensions = ['.safetensors', '.ckpt', '.pt'];
            const fileExt = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
            
            if (!validExtensions.includes(fileExt)) {
                uploadStatus.textContent = 'Invalid file type. Please upload a .safetensors, .ckpt, or .pt file';
                uploadStatus.className = 'error';
                return;
            }
            
            // Create loading state
            uploadStatus.textContent = 'Uploading...';
            uploadStatus.className = '';
            
            // Submit via AJAX
            fetch('/api/upload_lora', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    uploadStatus.textContent = data.message;
                    uploadStatus.className = 'success';
                    
                    // Refresh page after a delay to show updated LoRA list
                    setTimeout(() => {
                        window.location.reload();
                    }, 2000);
                } else {
                    uploadStatus.textContent = data.error || 'Upload failed';
                    uploadStatus.className = 'error';
                }
            })
            .catch(error => {
                uploadStatus.textContent = 'Error: ' + error.message;
                uploadStatus.className = 'error';
            });
        });
    }
    
    // ----- PRESET BUTTONS FUNCTIONALITY ----- //
    const presetButtons = document.querySelectorAll('.preset-btn');
    const moodInput = document.getElementById('mood');
    
    if (presetButtons.length > 0 && moodInput) {
        presetButtons.forEach(button => {
            button.addEventListener('click', function() {
                // Remove active class from all buttons
                presetButtons.forEach(btn => btn.classList.remove('active'));
                
                // Add active class to clicked button
                this.classList.add('active');
                
                // Set the mood input value based on preset
                const preset = this.getAttribute('data-preset');
                switch(preset) {
                    case 'minimalist':
                        moodInput.value = 'clean minimalist design with subtle colors';
                        break;
                    case 'high-contrast':
                        moodInput.value = 'bold high contrast design with striking visuals';
                        break;
                    case 'retro':
                        moodInput.value = 'vintage retro aesthetic with analog texture';
                        break;
                    case 'bold-colors':
                        moodInput.value = 'vibrant colorful design with bold typography';
                        break;
                }
            });
        });
    }
    
    // ----- RESULT PAGE FUNCTIONALITIES ----- //
    
    // Copy title button
    const copyTitleButton = document.getElementById('copy-title');
    if (copyTitleButton) {
        copyTitleButton.addEventListener('click', function() {
            const title = document.querySelector('.album-title').textContent.trim();
            
            navigator.clipboard.writeText(title)
                .then(() => {
                    // Show success message
                    this.textContent = 'Title Copied!';
                    
                    // Reset button text after a delay
                    setTimeout(() => {
                        this.textContent = 'Copy Title';
                    }, 2000);
                })
                .catch(err => {
                    console.error('Failed to copy title: ', err);
                });
        });
    }
    
    // Copy/Download cover button
    const copyCoverButton = document.getElementById('copy-cover');
    if (copyCoverButton) {
        copyCoverButton.addEventListener('click', function() {
            const imagePath = this.getAttribute('data-image-path');
            const imageUrl = `/generated_covers/${imagePath}`;
            
            // Create a temporary link to download the image
            const a = document.createElement('a');
            a.href = imageUrl;
            a.download = imagePath;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            
            // Show success message
            this.textContent = 'Cover Downloaded!';
            
            // Reset button text after a delay
            setTimeout(() => {
                this.textContent = 'Download Cover';
            }, 2000);
        });
    }
    
    // Regenerate cover button
    const regenerateButton = document.getElementById('regenerate-cover');
    if (regenerateButton) {
        regenerateButton.addEventListener('click', function() {
            const playlistUrl = this.getAttribute('data-playlist-url');
            const mood = this.getAttribute('data-mood') || '';
            const negativePrompt = this.getAttribute('data-negative-prompt') || '';
            const loraName = this.getAttribute('data-lora-name') || '';
            
            // Create a loading overlay
            const loadingOverlay = document.createElement('div');
            loadingOverlay.className = 'loading-overlay';
            loadingOverlay.innerHTML = `
                <div class="loading-content">
                    <div class="loading-spinner"></div>
                    <p>Regenerating cover with same playlist...</p>
                    <p class="loading-subtext">This may take a minute</p>
                </div>
            `;
            document.body.appendChild(loadingOverlay);
            
            // Make AJAX request to regenerate endpoint
            fetch('/api/regenerate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    playlist_url: playlistUrl,
                    mood: mood,
                    negative_prompt: negativePrompt,
                    lora_name: loraName
                }),
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Refresh the page to show new results
                    window.location.reload();
                } else {
                    // Remove loading overlay
                    document.body.removeChild(loadingOverlay);
                    alert('Error: ' + data.error);
                }
            })
            .catch(error => {
                // Remove loading overlay
                document.body.removeChild(loadingOverlay);
                console.error('Error regenerating cover:', error);
                alert('Failed to regenerate cover. Please try again.');
            });
        });
    }

    // Add CSS for textarea in the form
    if (document.getElementById('negative_prompt')) {
        const style = document.createElement('style');
        style.textContent = `
            textarea {
                width: 100%;
                padding: 12px;
                border: none;
                background-color: #333;
                color: #fff;
                border-radius: 5px;
                font-size: 1rem;
                margin-bottom: 5px;
                transition: all 0.3s ease;
                border-left: 4px solid #1DB954;
                box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1) inset;
                font-family: monospace;
                resize: vertical;
            }
            
            textarea:focus {
                outline: none;
                box-shadow: 0 0 0 2px rgba(29, 185, 84, 0.3);
                background-color: #3a3a3a;
            }
        `;
        document.head.appendChild(style);
    }
});