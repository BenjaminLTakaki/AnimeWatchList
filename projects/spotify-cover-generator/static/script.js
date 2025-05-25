// Updated JavaScript for handling form and UI functionality
document.addEventListener('DOMContentLoaded', function() {
    // Check if user is in guest mode
    const userHeader = document.querySelector('.user-header');
    const isGuestMode = userHeader && userHeader.textContent.includes('Guest');
    
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
    
    // Enhanced loading state for form submission
    const form = document.querySelector('form');
    if (form) {
        form.addEventListener('submit', function() {
            const submitButton = this.querySelector('.submit-btn');
            if (submitButton && !submitButton.disabled) {
                submitButton.disabled = true;
                submitButton.innerHTML = 'Generating... <span class="spinner"></span>';
                submitButton.classList.add('loading');
                
                // Create a loading overlay with guest-specific messaging
                const loadingOverlay = document.createElement('div');
                loadingOverlay.className = 'loading-overlay';
                
                let loadingMessage = 'Analyzing music and generating cover art...';
                let subMessage = 'This may take a minute or two';
                
                if (isGuestMode) {
                    subMessage = 'This is your free generation for today!';
                }
                
                loadingOverlay.innerHTML = `
                    <div class="loading-content">
                        <div class="loading-spinner"></div>
                        <p>${loadingMessage}</p>
                        <p class="loading-subtext">${subMessage}</p>
                        ${isGuestMode ? '<p class="loading-subtext" style="color: #1DB954;">Sign up for more generations!</p>' : ''}
                    </div>
                `;
                document.body.appendChild(loadingOverlay);
            }
            
            // Allow form submission to continue
            return true;
        });
    }
    
    // Guest mode specific features
    if (isGuestMode) {
        // Add guest mode indicators
        addGuestModeIndicators();
        
        // Show upgrade prompts
        showGuestUpgradePrompts();
        
        // Track guest interactions
        trackGuestInteractions();
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
    
    // LoRA file upload handling (only for registered users)
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
                    
                    // Show guest upgrade hint
                    if (isGuestMode) {
                        showGuestHint('Love this title? Sign up to save your generations!');
                    }
                })
                .catch(err => {
                    console.error('Failed to copy title: ', err);
                });
        });
    }
    
    // Download cover button
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
            
            // Show guest upgrade hint
            if (isGuestMode) {
                showGuestHint('Want to generate more covers? Sign up for free!');
            }
        });
    }
    
    // Regenerate cover button (enhanced for guest mode)
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
                    
                    // Show guest-specific error messages
                    if (isGuestMode && data.error.includes('limit')) {
                        showGuestUpgradeModal();
                    } else {
                        alert('Error: ' + data.error);
                    }
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
    
    // Guest mode specific functions
    function addGuestModeIndicators() {
        // Add subtle guest mode indicators
        const restrictedElements = document.querySelectorAll('[data-requires-account]');
        restrictedElements.forEach(element => {
            element.style.opacity = '0.6';
            element.style.pointerEvents = 'none';
            
            const lockIcon = document.createElement('span');
            lockIcon.innerHTML = ' 🔒';
            lockIcon.style.color = '#666';
            element.appendChild(lockIcon);
        });
    }
    
    function showGuestUpgradePrompts() {
        // Show periodic upgrade prompts (not too aggressive)
        setTimeout(() => {
            if (Math.random() < 0.3) { // 30% chance
                showGuestHint('💡 Tip: Sign up for free to get 2 generations per day!');
            }
        }, 15000); // After 15 seconds
    }
    
    function trackGuestInteractions() {
        // Track guest user interactions for analytics
        let interactions = 0;
        
        document.addEventListener('click', function() {
            interactions++;
            
            // After several interactions, show upgrade prompt
            if (interactions === 5) {
                showGuestHint('You seem to like our tool! Sign up for free to unlock more features.');
            }
        });
    }
    
    function showGuestHint(message) {
        // Show non-intrusive hint to guests
        const hint = document.createElement('div');
        hint.className = 'guest-hint';
        hint.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: linear-gradient(135deg, #1DB954, #1ed760);
            color: #000;
            padding: 15px 20px;
            border-radius: 8px;
            font-weight: bold;
            max-width: 300px;
            z-index: 1000;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            cursor: pointer;
            transform: translateX(400px);
            transition: transform 0.3s ease;
        `;
        hint.innerHTML = `
            ${message}
            <div style="margin-top: 8px;">
                <a href="/register" style="color: #000; text-decoration: underline;">Sign Up Free</a>
                <span style="margin: 0 10px;">|</span>
                <span onclick="this.parentElement.parentElement.remove()" style="cursor: pointer;">Dismiss</span>
            </div>
        `;
        
        document.body.appendChild(hint);
        
        // Animate in
        setTimeout(() => {
            hint.style.transform = 'translateX(0)';
        }, 100);
        
        // Auto-dismiss after 10 seconds
        setTimeout(() => {
            if (hint.parentElement) {
                hint.style.transform = 'translateX(400px)';
                setTimeout(() => hint.remove(), 300);
            }
        }, 10000);
    }
    
    function showGuestUpgradeModal() {
        // Show upgrade modal when guest hits limits
        const modal = document.createElement('div');
        modal.className = 'upgrade-modal';
        modal.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.8);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 2000;
        `;
        
        modal.innerHTML = `
            <div style="background: #1e1e1e; padding: 40px; border-radius: 12px; max-width: 500px; text-align: center; color: #fff;">
                <h2 style="color: #1DB954; margin: 0 0 20px 0;">🎵 Ready for More?</h2>
                <p>You've reached your daily limit as a guest user.</p>
                <p>Sign up for <strong>free</strong> to get:</p>
                <ul style="text-align: left; margin: 20px 0; color: #ccc;">
                    <li>✅ 2 generations per day</li>
                    <li>✅ Access to LoRA styles</li>
                    <li>✅ Save your creations</li>
                    <li>✅ Edit Spotify playlists</li>
                </ul>
                <div style="margin-top: 30px;">
                    <a href="/register" style="background: #1DB954; color: #000; padding: 15px 30px; text-decoration: none; border-radius: 25px; font-weight: bold; margin-right: 15px;">Sign Up Free</a>
                    <button onclick="this.closest('.upgrade-modal').remove()" style="background: #666; color: #fff; padding: 15px 20px; border: none; border-radius: 25px; cursor: pointer;">Maybe Later</button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
    }
    
    // Add CSS for new elements
    const style = document.createElement('style');
    style.textContent = `
        .guest-hint {
            animation: slideIn 0.3s ease;
        }
        
        @keyframes slideIn {
            from { transform: translateX(400px); }
            to { transform: translateX(0); }
        }
        
        .loading-spinner {
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .upgrade-modal {
            animation: fadeIn 0.3s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        .guest-hint:hover {
            transform: scale(1.02);
        }
        
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
});