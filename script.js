// Carousel variables
let currentIndex = 0;
let repos = [];
let reposPerView = 3;

// Run when DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
    // Initialize theme
    initializeTheme();
    
    // Initialize EmailJS
    if (typeof emailjs !== 'undefined') {
        emailjs.init("5XhzQ2uxmMYO1HHL_");
    }

    // Theme Toggle
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }

    // Navigation Toggle
    const navToggle = document.querySelector('.nav-toggle');
    const navMenu = document.querySelector('.nav-menu');

    if (navToggle && navMenu) {
        navToggle.addEventListener('click', () => {
            navMenu.classList.toggle('active');
            navToggle.classList.toggle('active');
        });

        // Close menu when clicking outside
        document.addEventListener('click', (e) => {
            if (!navToggle.contains(e.target) && !navMenu.contains(e.target)) {
                navMenu.classList.remove('active');
                navToggle.classList.remove('active');
            }
        });
    }

    // Header scroll effect
    const header = document.querySelector('.header');
    let lastScrollTop = 0;

    window.addEventListener('scroll', () => {
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        
        if (scrollTop > 100) {
            header.style.background = getComputedStyle(document.documentElement).getPropertyValue('--background-dark') === '#fafbfc' 
                ? 'rgba(250, 251, 252, 0.95)' 
                : 'rgba(10, 10, 10, 0.95)';
            header.style.boxShadow = '0 2px 20px rgba(0, 0, 0, 0.1)';
        } else {
            header.style.background = getComputedStyle(document.documentElement).getPropertyValue('--background-dark') === '#fafbfc' 
                ? 'rgba(250, 251, 252, 0.9)' 
                : 'rgba(10, 10, 10, 0.9)';
            header.style.boxShadow = 'none';
        }

        lastScrollTop = scrollTop;
    });

    // Back to Top Button Functionality
    const backToTopBtn = document.querySelector('.back-to-top');

    if (backToTopBtn) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 500) {
                backToTopBtn.classList.add('show');
            } else {
                backToTopBtn.classList.remove('show');
            }
        });

        backToTopBtn.addEventListener('click', () => {
            window.scrollTo({ 
                top: 0, 
                behavior: 'smooth' 
            });
        });
    }

    // Handle Contact Form Submission
    const contactForm = document.getElementById('contact-form');

    if (contactForm) {
        contactForm.addEventListener('submit', function (event) {
            event.preventDefault();

            if (typeof emailjs === 'undefined') {
                showMessage(contactForm, 'Error: EmailJS not loaded', 'error');
                return;
            }

            // Disable submit button to prevent multiple submissions
            const submitButton = contactForm.querySelector('button[type="submit"]');
            const originalText = submitButton.innerHTML;
            
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';
            }

            emailjs.sendForm('service_0uetwny', 'template_r6nz0s3', this)
                .then(() => {
                    // Show success message
                    showMessage(contactForm, 'Message sent successfully!', 'success');

                    // Reset form
                    contactForm.reset();

                    // Re-enable button
                    if (submitButton) {
                        submitButton.disabled = false;
                        submitButton.innerHTML = originalText;
                    }
                }, (error) => {
                    console.error('Error sending message:', error);
                    showMessage(contactForm, 'Failed to send message. Please try again.', 'error');

                    // Re-enable button
                    if (submitButton) {
                        submitButton.disabled = false;
                        submitButton.innerHTML = originalText;
                    }
                });
        });
    }

    // Helper function to show messages with better styling
    function showMessage(form, text, type) {
        // Remove any existing message
        const existingMessage = form.querySelector('.success-message, .error-message');
        if (existingMessage) {
            existingMessage.remove();
        }

        // Create message element
        const messageElement = document.createElement('div');
        messageElement.className = type === 'success' ? 'success-message' : 'error-message';
        messageElement.innerHTML = `
            <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i>
            ${text}
        `;
        form.appendChild(messageElement);

        // Remove message after 5 seconds
        setTimeout(() => {
            messageElement.style.opacity = '0';
            messageElement.style.transform = 'translateY(-20px)';
            setTimeout(() => {
                if (messageElement.parentNode) {
                    messageElement.remove();
                }
            }, 300);
        }, 5000);
    }

    // Initialize carousel controls
    initializeCarousel();
    
    // Fetch GitHub Repositories
    fetchGitHubRepos();
    
    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();

            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                const headerOffset = 100;
                const elementPosition = target.getBoundingClientRect().top;
                const offsetPosition = elementPosition + window.pageYOffset - headerOffset;

                window.scrollTo({
                    top: offsetPosition,
                    behavior: 'smooth'
                });

                // Close mobile menu if open
                if (navMenu && navMenu.classList.contains('active')) {
                    navMenu.classList.remove('active');
                    navToggle.classList.remove('active');
                }
            }
        });
    });

    // Intersection Observer for animations
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, observerOptions);

    // Observe sections for animations
    document.querySelectorAll('section, .project-card').forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(30px)';
        el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(el);
    });
});

// Theme Management Functions
function initializeTheme() {
    // Check for saved theme preference or default to 'dark'
    const savedTheme = localStorage.getItem('theme') || 'dark';
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = savedTheme === 'system' ? (systemPrefersDark ? 'dark' : 'light') : savedTheme;
    
    setTheme(theme);
    updateThemeToggle(theme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    setTheme(newTheme);
    updateThemeToggle(newTheme);
    localStorage.setItem('theme', newTheme);
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    
    // Update meta theme-color for mobile browsers
    const metaThemeColor = document.querySelector('meta[name=theme-color]');
    if (metaThemeColor) {
        metaThemeColor.setAttribute('content', theme === 'dark' ? '#0a0a0a' : '#fafbfc');
    } else {
        // Create meta theme-color if it doesn't exist
        const meta = document.createElement('meta');
        meta.name = 'theme-color';
        meta.content = theme === 'dark' ? '#0a0a0a' : '#fafbfc';
        document.head.appendChild(meta);
    }
}

function updateThemeToggle(theme) {
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        if (theme === 'light') {
            themeToggle.classList.add('light');
        } else {
            themeToggle.classList.remove('light');
        }
    }
}

// Listen for system theme changes
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'system') {
        const theme = e.matches ? 'dark' : 'light';
        setTheme(theme);
        updateThemeToggle(theme);
    }
});

// FIXED CAROUSEL FUNCTIONS
// Carousel variables are already defined at the top of the script.

// Initialize carousel controls
function initializeCarousel() {
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');

    if (prevBtn && nextBtn) {
        prevBtn.addEventListener('click', () => moveToPrev());
        nextBtn.addEventListener('click', () => moveToNext());
    }

    // Update repos per view based on screen size
    updateReposPerView();
    window.addEventListener('resize', updateReposPerView);
}

function updateReposPerView() {
    const width = window.innerWidth;
    if (width < 480) {
        reposPerView = 1;
    } else if (width < 768) {
        reposPerView = 1;
    } else if (width < 1024) {
        reposPerView = 2;
    } else {
        reposPerView = 3;
    }
    
    if (repos.length > 0) {
        updateCarousel();
    }
}

function moveToPrev() {
    if (currentIndex > 0) {
        currentIndex--;
        updateCarousel();
    }
}

function moveToNext() {
    const maxIndex = Math.max(0, repos.length - reposPerView);
    if (currentIndex < maxIndex) {
        currentIndex++;
        updateCarousel();
    }
}

function moveToIndex(index) {
    const maxIndex = Math.max(0, repos.length - reposPerView);
    currentIndex = Math.min(index, maxIndex);
    updateCarousel();
}

function updateCarousel() {
    const wrapper = document.querySelector('.carousel-wrapper');
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    
    if (!wrapper) return;

    // Calculate translateX based on card width and gap
    const cardWidth = 320; // Fixed width from CSS
    const gap = 32; // 2rem gap from CSS
    const translateX = -(currentIndex * (cardWidth + gap));
    
    wrapper.style.transform = `translateX(${translateX}px)`;

    // Update button states
    if (prevBtn) {
        prevBtn.disabled = currentIndex === 0;
    }
    if (nextBtn) {
        const maxIndex = Math.max(0, repos.length - reposPerView);
        nextBtn.disabled = currentIndex >= maxIndex;
    }

    // Update indicators
    updateIndicators();
}

function updateIndicators() {
    const indicatorsContainer = document.getElementById('indicators');
    if (!indicatorsContainer) return;

    const maxIndex = Math.max(0, repos.length - reposPerView);
    indicatorsContainer.innerHTML = '';

    for (let i = 0; i <= maxIndex; i++) {
        const dot = document.createElement('div');
        dot.className = `carousel-dot ${i === currentIndex ? 'active' : ''}`;
        dot.addEventListener('click', () => moveToIndex(i));
        indicatorsContainer.appendChild(dot);
    }
}

// FIXED GitHub Repositories Fetch Function
async function fetchGitHubRepos() {
    const reposContainer = document.getElementById('github-repos');
    if (!reposContainer) return;

    try {
        const response = await fetch('https://api.github.com/users/BenjaminLTakaki/repos?sort=updated&per_page=50');

        if (!response.ok) {
            throw new Error(`GitHub API request failed: ${response.status}`);
        }

        const allRepos = await response.json();

        // Clear loading indicator
        reposContainer.innerHTML = '';

        // Filter out certain repos and ensure descriptions exist
        const filteredRepos = allRepos
            .filter(repo => 
                !repo.fork &&
                repo.name.toLowerCase() !== 'animewatchlist' &&
                repo.name.toLowerCase() !== 'portfoliowebsite' &&
                repo.name.toLowerCase() !== 'skillstownrecommender' &&
                repo.name.toLowerCase() !== 'spotify-cover-generator' &&
                repo.description && 
                repo.description.trim() !== ''
            );

        repos = filteredRepos;

        if (repos.length === 0) {
            reposContainer.innerHTML = '<p class="no-repos">No additional GitHub projects to display.</p>';
            return;
        }

        // Create repo cards with consistent structure
        repos.forEach((repo, index) => {
            const card = document.createElement('div');
            card.className = 'repo-card';

            // Get language color
            const langColor = getLanguageColor(repo.language);

            // Truncate description if too long
            let description = repo.description || 'No description available';
            if (description.length > 120) {
                description = description.substring(0, 117) + '...';
            }

            card.innerHTML = `
                <h4 title="${formatRepoName(repo.name)}">${formatRepoName(repo.name)}</h4>
                <p title="${repo.description || 'No description available'}">${description}</p>
                <div class="repo-meta">
                    ${repo.language ? 
                        `<span class="language">
                            <span class="lang-color" style="background-color: ${langColor}"></span>
                            ${repo.language}
                        </span>` : 
                        ''
                    }
                </div>
                <div class="repo-links">
                    <a href="${repo.html_url}" target="_blank" class="btn btn-secondary">
                        <i class="fab fa-github"></i> View on GitHub
                    </a>
                </div>
            `;

            reposContainer.appendChild(card);
        });

        // Initialize carousel after repos are loaded
        currentIndex = 0;
        updateCarousel();

        // Add intersection observer for repo cards
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.style.opacity = '1';
                    entry.target.style.transform = 'translateY(0)';
                }
            });
        }, {
            threshold: 0.1,
            rootMargin: '0px 0px -50px 0px'
        });

        document.querySelectorAll('.repo-card').forEach(el => {
            el.style.opacity = '0';
            el.style.transform = 'translateY(30px)';
            el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
            observer.observe(el);
        });

    } catch (error) {
        console.error('Error fetching GitHub repos:', error);
        reposContainer.innerHTML = `
            <div class="error-message">
                <i class="fas fa-exclamation-triangle"></i>
                Could not load GitHub projects at this time.
            </div>
        `;
    }
}

// Function to format repository names
function formatRepoName(name) {
    return name
        .split(/[-_]/)
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}

// Function to get language color
function getLanguageColor(language) {
    const colors = {
        'JavaScript': '#f1e05a',
        'Python': '#3572A5',
        'HTML': '#e34c26',
        'CSS': '#563d7c',
        'Java': '#b07219',
        'C#': '#178600',
        'TypeScript': '#2b7489',
        'PHP': '#4F5D95',
        'C++': '#f34b7d',
        'Ruby': '#701516',
        'Go': '#00ADD8',
        'Rust': '#dea584',
        'Swift': '#fa7343',
        'Kotlin': '#F18E33',
        'Vue': '#4FC08D',
        'React': '#61DAFB'
    };

    return colors[language] || '#8e8e8e';
}

// Enhanced loading function for project links
function showLoading(event) {
    const loadingOverlay = document.createElement('div');
    loadingOverlay.className = 'loading-overlay';
    loadingOverlay.innerHTML = `
        <div class="loading-spinner"></div>
        <p>Loading project...</p>
        <small>This may take a moment</small>
    `;
    document.body.appendChild(loadingOverlay);
    
    // Add fade in animation
    setTimeout(() => {
        loadingOverlay.style.opacity = '1';
    }, 10);
    
    // Remove loading overlay after 5 seconds if still present
    setTimeout(() => {
        if (loadingOverlay.parentNode) {
            loadingOverlay.style.opacity = '0';
            setTimeout(() => {
                if (loadingOverlay.parentNode) {
                    loadingOverlay.remove();
                }
            }, 300);
        }
    }, 5000);
}