// Enhanced JavaScript for AnimeWatchList - Mobile-First with Progressive Enhancement
document.addEventListener("DOMContentLoaded", function () {
    console.log("AnimeWatchList enhanced scripts loaded.");

    // ===== MOBILE OPTIMIZATIONS =====
    
    // Prevent zoom on input focus for iOS
    function preventZoom() {
        const inputs = document.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            if (input.style.fontSize !== '16px') {
                input.style.fontSize = '16px';
            }
        });
    }
    
    // Only apply on mobile devices
    if (/iPhone|iPad|iPod|Android/i.test(navigator.userAgent)) {
        preventZoom();
    }

    // ===== TOUCH OPTIMIZATIONS =====
    
    // Add touch feedback for buttons
    function addTouchFeedback() {
        const touchElements = document.querySelectorAll('.btn, .link-btn, button, a[class*="btn"]');
        
        touchElements.forEach(element => {
            // Add touch start effect
            element.addEventListener('touchstart', function(e) {
                this.style.transform = 'scale(0.95)';
                this.style.transition = 'transform 0.1s ease';
            }, { passive: true });
            
            // Remove touch effect
            element.addEventListener('touchend', function(e) {
                setTimeout(() => {
                    this.style.transform = '';
                    this.style.transition = '';
                }, 100);
            }, { passive: true });
            
            // Handle touch cancel
            element.addEventListener('touchcancel', function(e) {
                this.style.transform = '';
                this.style.transition = '';
            }, { passive: true });
        });
    }
    
    // Apply touch feedback on touch devices
    if ('ontouchstart' in window) {
        addTouchFeedback();
    }

    // ===== FORM ENHANCEMENTS =====
    
    // Enhanced form submission handling
    function enhanceFormSubmissions() {
        const forms = document.querySelectorAll('form');
        
        forms.forEach(form => {
            form.addEventListener('submit', function(e) {
                const submitBtn = this.querySelector('button[type="submit"], input[type="submit"]');
                
                if (submitBtn && !submitBtn.disabled) {
                    // Prevent double submission
                    submitBtn.disabled = true;
                    submitBtn.style.opacity = '0.7';
                    
                    // Store original text
                    const originalText = submitBtn.textContent || submitBtn.value;
                    
                    // Update button text based on form action
                    if (this.action.includes('mark')) {
                        submitBtn.textContent = 'Marking...';
                    } else if (this.action.includes('search')) {
                        submitBtn.textContent = 'Searching...';
                    } else if (this.action.includes('login')) {
                        submitBtn.textContent = 'Logging in...';
                    } else if (this.action.includes('register')) {
                        submitBtn.textContent = 'Creating account...';
                    } else {
                        submitBtn.textContent = 'Processing...';
                    }
                    
                    // Re-enable after timeout to handle errors
                    setTimeout(() => {
                        submitBtn.disabled = false;
                        submitBtn.style.opacity = '';
                        submitBtn.textContent = originalText;
                    }, 10000);
                }
            });
        });
    }
    
    enhanceFormSubmissions();

    // ===== ANIME MARKING ENHANCEMENTS =====
    
    // Enhanced anime marking with better feedback
    function enhanceAnimeMarking() {
        const markingForms = document.querySelectorAll('form[action*="mark"]');
        
        markingForms.forEach(form => {
            form.addEventListener('submit', function(e) {
                // Get anime title for better feedback
                const animeTitle = this.closest('.anime-card, .anime-item')?.querySelector('h2, h3')?.textContent?.trim();
                
                // Log for debugging
                const formData = new FormData(form);
                console.log("Submitting anime marking form:");
                for (let [key, value] of formData.entries()) {
                    console.log(`${key}: ${value.substring(0, 50)}${value.length > 50 ? '...' : ''}`);
                }
                
                // Show immediate feedback
                if (animeTitle) {
                    showToast(`Marking "${animeTitle}" as watched...`, 'info');
                }
                
                return true; // Allow form submission
            });
        });
    }
    
    enhanceAnimeMarking();

    // ===== NAVIGATION ENHANCEMENTS =====
    
    // Add loading states for navigation
    function enhanceNavigation() {
        const navLinks = document.querySelectorAll('nav a, .btn:not([type="submit"]), .link-btn');
        
        navLinks.forEach(link => {
            link.addEventListener('click', function(e) {
                // Skip for external links, anchors, and special actions
                if (this.href && (
                    this.href.includes('#') || 
                    this.href.includes('mailto:') || 
                    this.href.includes('tel:') ||
                    this.target === '_blank' ||
                    this.href.startsWith('http') && !this.href.includes(window.location.host)
                )) {
                    return;
                }
                
                // Add loading state
                this.style.opacity = '0.7';
                this.style.pointerEvents = 'none';
                
                // Show loading indicator for slower connections
                setTimeout(() => {
                    if (this.style.opacity === '0.7') {
                        showToast('Loading...', 'info');
                    }
                }, 1000);
                
                // Remove loading state after timeout
                setTimeout(() => {
                    this.style.opacity = '';
                    this.style.pointerEvents = '';
                }, 5000);
            });
        });
    }
    
    enhanceNavigation();

    // ===== SEARCH ENHANCEMENTS =====
    
    // Enhance search functionality
    function enhanceSearch() {
        const searchInput = document.querySelector('input[name="query"]');
        const searchForm = document.querySelector('.search-form, form[action*="search"]');
        
        if (searchInput && searchForm) {
            // Add search suggestions or history (basic implementation)
            let searchTimeout;
            
            searchInput.addEventListener('input', function() {
                clearTimeout(searchTimeout);
                const query = this.value.trim();
                
                // Basic validation
                if (query.length > 0 && query.length < 2) {
                    this.setCustomValidity('Please enter at least 2 characters');
                } else {
                    this.setCustomValidity('');
                }
                
                // Auto-search after delay (optional, can be enabled)
                // searchTimeout = setTimeout(() => {
                //     if (query.length >= 3) {
                //         // Auto-search functionality could be added here
                //     }
                // }, 1000);
            });
            
            // Enter key handling
            searchInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && this.value.trim().length >= 2) {
                    searchForm.submit();
                }
            });
        }
    }
    
    enhanceSearch();

    // ===== SORTING ENHANCEMENTS =====
    
    // Enhance sorting dropdowns
    function enhanceSorting() {
        const sortSelects = document.querySelectorAll('.sort-select');
        
        sortSelects.forEach(select => {
            select.addEventListener('change', function() {
                // Add loading state to the page
                const animeList = document.querySelector('.anime-list');
                if (animeList) {
                    animeList.style.opacity = '0.5';
                    animeList.style.pointerEvents = 'none';
                }
                
                showToast('Sorting anime list...', 'info');
                
                // Form will submit automatically via onchange
            });
        });
    }
    
    enhanceSorting();

    // ===== TOAST NOTIFICATIONS =====
    
    // Simple toast notification system
    function showToast(message, type = 'info', duration = 3000) {
        // Remove existing toasts
        const existingToasts = document.querySelectorAll('.toast');
        existingToasts.forEach(toast => toast.remove());
        
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        // Style the toast
        Object.assign(toast.style, {
            position: 'fixed',
            top: '20px',
            right: '20px',
            padding: '12px 20px',
            borderRadius: '8px',
            color: 'white',
            fontWeight: '600',
            fontSize: '14px',
            zIndex: '9999',
            maxWidth: '300px',
            wordWrap: 'break-word',
            boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
            transform: 'translateX(400px)',
            transition: 'transform 0.3s ease-in-out',
            backgroundColor: type === 'error' ? '#f44336' : 
                           type === 'success' ? '#4CAF50' : 
                           type === 'warning' ? '#ff9800' : '#2196F3'
        });
        
        // Add to page
        document.body.appendChild(toast);
        
        // Animate in
        setTimeout(() => {
            toast.style.transform = 'translateX(0)';
        }, 10);
        
        // Remove after duration
        setTimeout(() => {
            toast.style.transform = 'translateX(400px)';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.remove();
                }
            }, 300);
        }, duration);
        
        // Click to dismiss
        toast.addEventListener('click', () => {
            toast.style.transform = 'translateX(400px)';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.remove();
                }
            }, 300);
        });
    }
    
    // Make showToast globally available
    window.showToast = showToast;

    // ===== IMAGE LOADING OPTIMIZATION =====
    
    // Progressive image loading with fallbacks
    function optimizeImageLoading() {
        const images = document.querySelectorAll('img[loading="lazy"]');
        
        images.forEach(img => {
            // Add loading placeholder
            if (!img.complete) {
                img.style.backgroundColor = '#f0f0f0';
                img.style.minHeight = '200px';
            }
            
            // Handle loading errors
            img.addEventListener('error', function() {
                this.style.backgroundColor = '#e0e0e0';
                this.style.color = '#666';
                this.style.display = 'flex';
                this.style.alignItems = 'center';
                this.style.justifyContent = 'center';
                this.style.fontSize = '12px';
                this.style.textAlign = 'center';
                this.innerHTML = '📷<br>Image not available';
                this.style.minHeight = '200px';
            });
            
            // Handle successful loading
            img.addEventListener('load', function() {
                this.style.backgroundColor = '';
                this.style.minHeight = '';
            });
        });
    }
    
    optimizeImageLoading();

    // ===== ACCESSIBILITY ENHANCEMENTS =====
    
    // Keyboard navigation improvements
    function enhanceAccessibility() {
        // Add focus visible for keyboard users
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Tab') {
                document.body.classList.add('keyboard-nav');
            }
        });
        
        document.addEventListener('mousedown', function() {
            document.body.classList.remove('keyboard-nav');
        });
        
        // Improve link accessibility
        const links = document.querySelectorAll('a[target="_blank"]');
        links.forEach(link => {
            if (!link.getAttribute('aria-label') && !link.textContent.includes('(opens in new tab)')) {
                link.setAttribute('aria-label', `${link.textContent} (opens in new tab)`);
            }
        });
    }
    
    enhanceAccessibility();

    // ===== OFFLINE SUPPORT =====
    
    // Basic offline detection
    function handleOfflineMode() {
        function updateOnlineStatus() {
            if (!navigator.onLine) {
                showToast('You are offline. Some features may not work.', 'warning', 5000);
            }
        }
        
        window.addEventListener('online', () => {
            showToast('Connection restored!', 'success');
        });
        
        window.addEventListener('offline', updateOnlineStatus);
        
        // Check initial status
        if (!navigator.onLine) {
            setTimeout(updateOnlineStatus, 1000);
        }
    }
    
    handleOfflineMode();

    // Star Rating Component JavaScript

    class StarRating {
        constructor(container, options = {}) {
            this.container = container;
            this.options = {
                maxRating: 5,
                currentRating: 0,
                interactive: true,
                showText: true,
                size: 'normal', // 'small', 'normal', 'large'
                onRate: null,
                ...options
            };
            
            this.currentRating = this.options.currentRating;
            this.hoverRating = 0;
            
            this.init();
        }
        
        init() {
            this.render();
            if (this.options.interactive) {
                this.bindEvents();
            }
        }
        
        render() {
            const ratingClass = this.options.interactive ? 'interactive' : 'readonly';
            const sizeClass = this.options.size !== 'normal' ? this.options.size : '';
            
            this.container.innerHTML = `
                <div class="star-rating ${ratingClass} ${sizeClass}" data-rating="${this.currentRating}">
                    ${this.renderStars()}
                </div>
                ${this.options.showText ? this.renderText() : ''}
            `;
            
            this.starsContainer = this.container.querySelector('.star-rating');
            this.stars = this.container.querySelectorAll('.star');
            this.textElement = this.container.querySelector('.rating-text');
            
            this.updateStars(this.currentRating);
        }
        
        renderStars() {
            let starsHtml = '';
            for (let i = 1; i <= this.options.maxRating; i++) {
                starsHtml += `
                    <span class="star" data-rating="${i}" role="button" tabindex="0" 
                        aria-label="Rate ${i} star${i !== 1 ? 's' : ''}" 
                        title="${i} star${i !== 1 ? 's' : ''}">
                        <svg viewBox="0 0 24 24">
                            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
                        </svg>
                    </span>
                `;
            }
            return starsHtml;
        }
        
        renderText() {
            const ratingText = this.getRatingText(this.currentRating);
            const hasRating = this.currentRating > 0;
            return `<span class="rating-text ${hasRating ? 'has-rating' : ''}">${ratingText}</span>`;
        }
        
        getRatingText(rating) {
            if (rating === 0 || rating === null || rating === undefined) {
                return 'Not rated';
            }
            return `${rating}/5 stars`;
        }
        
        bindEvents() {
            if (!this.options.interactive) return;
            
            this.stars.forEach((star, index) => {
                const rating = index + 1;
                
                // Mouse events
                star.addEventListener('mouseenter', () => this.handleHover(rating));
                star.addEventListener('click', () => this.handleClick(rating));
                
                // Keyboard events
                star.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        this.handleClick(rating);
                    }
                });
            });
            
            this.starsContainer.addEventListener('mouseleave', () => this.handleMouseLeave());
        }
        
        handleHover(rating) {
            this.hoverRating = rating;
            this.updateStars(rating);
            if (this.textElement) {
                this.textElement.textContent = this.getRatingText(rating);
                this.textElement.className = 'rating-text has-rating';
            }
        }
        
        handleMouseLeave() {
            this.hoverRating = 0;
            this.updateStars(this.currentRating);
            if (this.textElement) {
                this.textElement.textContent = this.getRatingText(this.currentRating);
                this.textElement.className = `rating-text ${this.currentRating > 0 ? 'has-rating' : ''}`;
            }
        }
        
        handleClick(rating) {
            // Allow clicking the same rating to set it to 0 (remove rating)
            const newRating = this.currentRating === rating ? 0 : rating;
            this.setRating(newRating);
            
            if (this.options.onRate) {
                this.options.onRate(newRating);
            }
        }
        
        updateStars(rating) {
            this.stars.forEach((star, index) => {
                const starRating = index + 1;
                if (starRating <= rating) {
                    star.classList.add('filled');
                } else {
                    star.classList.remove('filled');
                }
            });
        }
        
        setRating(rating, animate = true) {
            this.currentRating = rating;
            this.starsContainer.setAttribute('data-rating', rating);
            
            if (animate) {
                this.starsContainer.classList.add('animate');
                setTimeout(() => {
                    this.starsContainer.classList.remove('animate');
                }, 300);
            }
            
            this.updateStars(rating);
            if (this.textElement) {
                this.textElement.textContent = this.getRatingText(rating);
                this.textElement.className = `rating-text ${rating > 0 ? 'has-rating' : ''}`;
            }
        }
        
        getRating() {
            return this.currentRating;
        }
        
        destroy() {
            if (this.starsContainer) {
                this.starsContainer.removeEventListener('mouseleave', this.handleMouseLeave);
            }
            if (this.stars) {
                this.stars.forEach(star => {
                    star.removeEventListener('mouseenter', this.handleHover);
                    star.removeEventListener('click', this.handleClick);
                    star.removeEventListener('keydown', this.handleKeydown);
                });
            }
        }
    }

    // Utility functions for anime rating
    function initializeRatingSystem() {
        console.log('Initializing rating system...');
        
        // Initialize all existing rating displays (readonly)
        document.querySelectorAll('.rating-display-container').forEach(container => {
            const rating = parseInt(container.dataset.rating) || 0;
            new StarRating(container, {
                currentRating: rating,
                interactive: false,
                showText: true,
                size: 'small'
            });
        });
        
        // Initialize interactive rating forms
        document.querySelectorAll('.rating-form-container').forEach(container => {
            const animeId = container.dataset.animeId;
            const currentRating = parseInt(container.dataset.currentRating) || 0;
            
            new StarRating(container, {
                currentRating: currentRating,
                interactive: true,
                showText: true,
                onRate: (rating) => handleAnimeRating(animeId, rating, container)
            });
        });
    }

    async function handleAnimeRating(animeId, rating, container) {
        try {
            // Show loading state
            container.style.opacity = '0.7';
            
            const formData = new FormData();
            formData.append('anime_id', animeId);
            formData.append('rating', rating);
            
            const response = await fetch('/animewatchlist/rate_anime', {
                method: 'POST',
                body: formData
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    showToast(`Rating ${rating > 0 ? `${rating}/5 stars` : 'removed'}!`, 'success');
                    
                    // Update any readonly displays for this anime
                    document.querySelectorAll(`[data-anime-id="${animeId}"] .rating-display-container`).forEach(display => {
                        const starRating = display.starRatingInstance;
                        if (starRating) {
                            starRating.setRating(rating);
                        }
                    });
                    
                    // If rating > 0, mark as watched automatically
                    if (rating > 0 && result.marked_as_watched) {
                        showToast('Anime added to watched list!', 'success');
                        // Optionally redirect or update UI
                        setTimeout(() => {
                            if (window.location.pathname.includes('/animewatchlist') && !window.location.pathname.includes('/watched')) {
                                // We're on discovery page, get next anime
                                window.location.reload();
                            }
                        }, 1500);
                    }
                } else {
                    throw new Error(result.message || 'Failed to save rating');
                }
            } else {
                throw new Error('Network error');
            }
            
        } catch (error) {
            console.error('Rating error:', error);
            showToast('Failed to save rating. Please try again.', 'error');
            
            // Reset rating on error
            const starRating = container.starRatingInstance;
            if (starRating) {
                starRating.setRating(starRating.options.currentRating || 0, false);
            }
        } finally {
            container.style.opacity = '';
        }
    }

    function createRatingForm(animeId, currentRating = 0) {
        return `
            <div class="rating-form">
                <h4>Rate this anime</h4>
                <div class="rating-form-container" data-anime-id="${animeId}" data-current-rating="${currentRating}">
                    <!-- Star rating will be initialized here -->
                </div>
            </div>
        `;
    }

    function createRatingDisplay(rating, animeId = null) {
        const dataAttr = animeId ? `data-anime-id="${animeId}"` : '';
        return `
            <div class="rating-display" ${dataAttr}>
                <span class="user-rating-label">My Rating:</span>
                <div class="rating-display-container" data-rating="${rating || 0}">
                    <!-- Star rating will be initialized here -->
                </div>
            </div>
        `;
    }

    // Enhanced toast function specifically for ratings
    function showRatingToast(rating, action = 'rated') {
        let message;
        if (rating === 0) {
            message = 'Rating removed';
        } else {
            message = `${action === 'rated' ? 'Rated' : 'Rating updated to'} ${rating}/5 stars`;
        }
        
        showToast(message, 'success', 2000);
    }

    // Initialize rating system when DOM is loaded
    document.addEventListener('DOMContentLoaded', function() {
        // Wait a bit for the page to fully load
        setTimeout(() => {
            initializeRatingSystem();
        }, 100);
    });

    // Re-initialize ratings when content is dynamically loaded
    function reinitializeRatings() {
        setTimeout(() => {
            initializeRatingSystem();
        }, 100);
    }

    // Export for global use
    window.StarRating = StarRating;
    window.initializeRatingSystem = initializeRatingSystem;
    window.reinitializeRatings = reinitializeRatings;
    window.createRatingForm = createRatingForm;
    window.createRatingDisplay = createRatingDisplay;
    window.handleAnimeRating = handleAnimeRating;
    // ===== PERFORMANCE MONITORING =====
    
    // Basic performance monitoring
    function monitorPerformance() {
        // Log slow operations
        const observer = new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
                if (entry.duration > 1000) { // Slower than 1 second
                    console.warn(`Slow operation detected: ${entry.name} took ${entry.duration}ms`);
                }
            }
        });
        
        if ('PerformanceObserver' in window) {
            observer.observe({ entryTypes: ['measure', 'navigation'] });
        }
    }
    
    if (console && console.warn) {
        monitorPerformance();
    }

    // ===== SCROLL ENHANCEMENTS =====
    
    // Smooth scroll for anchor links
    function enhanceScrolling() {
        const anchorLinks = document.querySelectorAll('a[href^="#"]');
        
        anchorLinks.forEach(link => {
            link.addEventListener('click', function(e) {
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {
                    e.preventDefault();
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            });
        });
    }
    
    enhanceScrolling();

    console.log("✅ All enhancements loaded successfully!");
    
    // Show welcome message for new users (only on first visit)
    if (!localStorage.getItem('welcomeShown') && document.querySelector('.welcome-message')) {
        localStorage.setItem('welcomeShown', 'true');
        setTimeout(() => {
            showToast('Welcome to AnimeWatchList! 🎌', 'success', 4000);
        }, 1000);
    }
});

// ===== CSS INJECTION FOR KEYBOARD NAVIGATION =====
const keyboardNavStyles = `
.keyboard-nav *:focus {
    outline: 2px solid #2E51A2 !important;
    outline-offset: 2px !important;
}

.keyboard-nav .btn:focus,
.keyboard-nav .link-btn:focus {
    box-shadow: 0 0 0 3px rgba(46, 81, 162, 0.3) !important;
}
`;

const styleSheet = document.createElement('style');
styleSheet.textContent = keyboardNavStyles;
document.head.appendChild(styleSheet);
