// Import Three.js from CDN using dynamic import
let threeJSLoaded = false;

// Function to load Three.js dynamically
async function loadThreeJS() {
    if (!threeJSLoaded) {
        try {
            // Create script element for Three.js
            const threeScript = document.createElement('script');
            threeScript.src = 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js';
            threeScript.async = true;

            // Create a promise to wait for the script to load
            const threeLoaded = new Promise((resolve, reject) => {
                threeScript.onload = resolve;
                threeScript.onerror = reject;
            });

            // Add the script to the document
            document.head.appendChild(threeScript);

            // Wait for the script to load
            await threeLoaded;
            threeJSLoaded = true;

            // Initialize the Three.js background
            initThreeBackground();
        } catch (error) {
            console.error('Failed to load Three.js:', error);
        }
    }
}

// Initialize Three.js background
function initThreeBackground() {
    // Create a container for the Three.js canvas
    const container = document.createElement('div');
    container.id = 'three-background';
    container.style.position = 'fixed';
    container.style.top = '0';
    container.style.left = '0';
    container.style.width = '100%';
    container.style.height = '100%';
    container.style.zIndex = '-1';
    container.style.opacity = '0.7';
    document.body.prepend(container);

    // Initialize Three.js scene
    const scene = new THREE.Scene();

    // Create camera
    const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.z = 50;

    // Create renderer
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);

    // Create particles
    const particlesGeometry = new THREE.BufferGeometry();
    const particlesCount = 1500;

    const posArray = new Float32Array(particlesCount * 3);

    for (let i = 0; i < particlesCount * 3; i++) {
        posArray[i] = (Math.random() - 0.5) * 100;
    }

    particlesGeometry.setAttribute('position', new THREE.BufferAttribute(posArray, 3));

    // Create material
    const particlesMaterial = new THREE.PointsMaterial({
        size: 0.2,
        color: 0x4C9CFF,
        transparent: true,
        opacity: 0.8
    });

    // Create points
    const particlesMesh = new THREE.Points(particlesGeometry, particlesMaterial);
    scene.add(particlesMesh);

    // Handle window resize
    window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    });

    // Mouse movement effect
    let mouseX = 0;
    let mouseY = 0;

    document.addEventListener('mousemove', (event) => {
        mouseX = (event.clientX / window.innerWidth) * 2 - 1;
        mouseY = -(event.clientY / window.innerHeight) * 2 + 1;
    });

    // Animation loop
    function animate() {
        requestAnimationFrame(animate);

        particlesMesh.rotation.x += 0.0005;
        particlesMesh.rotation.y += 0.0005;

        // Interactive rotation based on mouse position
        particlesMesh.rotation.x += mouseY * 0.0005;
        particlesMesh.rotation.y += mouseX * 0.0005;

        renderer.render(scene, camera);
    }

    animate();
}

// Initialize EmailJS
emailjs.init("5XhzQ2uxmMYO1HHL_");

// Run when DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
    // Load Three.js background
    loadThreeJS();

    // Navigation Toggle
    const navToggle = document.querySelector('.nav-toggle');
    const navMenu = document.querySelector('.nav-menu');

    if (navToggle && navMenu) {
        navToggle.addEventListener('click', () => {
            navMenu.classList.toggle('active');
            navToggle.classList.toggle('active');
        });
    }

    // Back to Top Button Functionality
    const backToTopBtn = document.querySelector('.back-to-top');

    if (backToTopBtn) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 300) {
                backToTopBtn.classList.add('show');
            } else {
                backToTopBtn.classList.remove('show');
            }
        });

        backToTopBtn.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    // Handle Contact Form Submission
    const contactForm = document.getElementById('contact-form');

    if (contactForm) {
        contactForm.addEventListener('submit', function (event) {
            event.preventDefault();

            // Disable submit button to prevent multiple submissions
            const submitButton = contactForm.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.innerText = 'Sending...';
            }

            emailjs.sendForm('service_0uetwny', 'template_r6nz0s3', this)
                .then(() => {
                    // Show success message
                    const successMessage = document.createElement('div');
                    successMessage.className = 'success-message';
                    successMessage.innerText = 'Message sent successfully!';
                    contactForm.appendChild(successMessage);

                    // Reset form
                    contactForm.reset();

                    // Re-enable button after a delay
                    setTimeout(() => {
                        if (submitButton) {
                            submitButton.disabled = false;
                            submitButton.innerText = 'Send Message';
                        }
                        // Remove success message after 5 seconds
                        setTimeout(() => {
                            successMessage.remove();
                        }, 5000);
                    }, 1000);
                }, (error) => {
                    console.error('Error sending message:', error);

                    // Show error message
                    const errorMessage = document.createElement('div');
                    errorMessage.className = 'error-message';
                    errorMessage.innerText = 'Failed to send message. Please try again.';
                    contactForm.appendChild(errorMessage);

                    // Re-enable button
                    if (submitButton) {
                        submitButton.disabled = false;
                        submitButton.innerText = 'Send Message';
                    }

                    // Remove error message after 5 seconds
                    setTimeout(() => {
                        errorMessage.remove();
                    }, 5000);
                });
        });
    }

    // Fetch GitHub Repositories with improved project links
    const githubUsername = 'BenjaminLTakaki';
    const reposContainer = document.getElementById('github-repos');

    if (reposContainer) {
        const fetchRepos = async () => {
            try {
                const response = await fetch(`https://api.github.com/users/${githubUsername}/repos?sort=updated&per_page=4`);
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const repos = await response.json();

                // Show only repositories that aren't already featured as main projects
                const filteredRepos = repos.filter(repo =>
                    repo.name.toLowerCase() !== 'animewatchlist' &&
                    repo.name.toLowerCase() !== 'portfoliowebsite'
                );

                if (filteredRepos.length > 0) {
                    const heading = document.createElement('h3');
                    heading.textContent = 'Other GitHub Projects';
                    heading.className = 'other-projects-heading';
                    reposContainer.appendChild(heading);
                }

                filteredRepos.forEach(repo => {
                    const repoCard = document.createElement('div');
                    repoCard.className = 'repo';

                    // Format repo creation date
                    const createdDate = new Date(repo.created_at);
                    const formattedDate = createdDate.toLocaleDateString('en-US', {
                        year: 'numeric',
                        month: 'short'
                    });

                    // Determine if the project has a homepage or GitHub Pages
                    const hasDemo = repo.homepage || (repo.has_pages && repo.name);
                    const demoUrl = repo.homepage || (repo.has_pages ? `https://${githubUsername}.github.io/${repo.name}` : null);

                    repoCard.innerHTML = `
                        <h3><a href="${repo.html_url}" target="_blank" rel="noopener noreferrer">${repo.name}</a></h3>
                        <p>${repo.description || 'No description available.'}</p>
                        <div class="repo-meta">
                            <span class="repo-language">
                                ${repo.language ? `<span class="repo-language-color" style="background-color: ${getLanguageColor(repo.language)}"></span>${repo.language}` : 'N/A'}
                            </span>
                            <span class="repo-date">Created: ${formattedDate}</span>
                        </div>
                        <div class="project-links">
                            <a href="${repo.html_url}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary">
                                <i class="fab fa-github"></i> View Code
                            </a>
                            ${hasDemo ? `
                            <a href="${demoUrl}" target="_blank" rel="noopener noreferrer" class="btn btn-primary">
                                <i class="fas fa-external-link-alt"></i> Live Demo
                            </a>
                            ` : ''}
                        </div>
                    `;
                    reposContainer.appendChild(repoCard);
                });

                if (filteredRepos.length === 0) {
                    const noReposMessage = document.createElement('p');
                    noReposMessage.textContent = 'More GitHub repositories coming soon!';
                    noReposMessage.className = 'no-repos-message';
                    reposContainer.appendChild(noReposMessage);
                }
            } catch (error) {
                console.error('Error fetching repos:', error);
                const errorMessage = document.createElement('p');
                errorMessage.textContent = 'Unable to load GitHub repositories. Please check back later.';
                errorMessage.className = 'error-message';
                reposContainer.appendChild(errorMessage);
            }
        };

        fetchRepos();
    }

    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();

            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth'
                });
            }
        });
    });
});

// Function to get language color for GitHub repos
function getLanguageColor(language) {
    const colors = {
        'JavaScript': '#f1e05a',
        'Python': '#3572A5',
        'HTML': '#e34c26',
        'CSS': '#563d7c',
        'Java': '#b07219',
        'C#': '#178600',
        'PHP': '#4F5D95',
        'TypeScript': '#2b7489',
        'C++': '#f34b7d',
        'Ruby': '#701516'
    };

    return colors[language] || '#cccccc';
}

// Function to fetch and display top 3 GitHub repositories
document.addEventListener('DOMContentLoaded', function () {
    fetchGitHubRepos();
});

async function fetchGitHubRepos() {
    const reposContainer = document.getElementById('github-repos');
    if (!reposContainer) return;

    // Add loading indicator
    reposContainer.innerHTML = '<div class="loading">Loading projects...</div>';

    try {
        const response = await fetch('https://api.github.com/users/BenjaminLTakaki/repos?sort=updated');

        if (!response.ok) {
            throw new Error('GitHub API request failed');
        }

        const repos = await response.json();

        // Clear loading indicator
        reposContainer.innerHTML = '';

        // Filter out certain repos and get top 3
        const filteredRepos = repos
            .filter(repo =>
                !repo.fork &&
                repo.name.toLowerCase() !== 'animewatchlist' &&
                repo.name.toLowerCase() !== 'portfoliowebsite')
            .slice(0, 3);

        if (filteredRepos.length === 0) {
            reposContainer.innerHTML = '<p>No GitHub projects to display.</p>';
            return;
        }

        // Display each repo
        filteredRepos.forEach(repo => {
            const card = document.createElement('div');
            card.className = 'repo-card';

            // Get language color
            const langColor = getLanguageColor(repo.language);

            card.innerHTML = `
                <h4>${repo.name}</h4>
                <p>${repo.description || 'No description available'}</p>
                <div class="repo-meta">
                    ${repo.language ?
                    `<span class="language"><span class="lang-color" style="background-color: ${langColor}"></span>${repo.language}</span>` :
                    ''}
                </div>
                <div class="repo-links">
                    <a href="${repo.html_url}" target="_blank" class="btn btn-secondary">
                        <i class="fab fa-github"></i> View on GitHub
                    </a>
                </div>
            `;

            reposContainer.appendChild(card);
        });

    } catch (error) {
        console.error('Error fetching GitHub repos:', error);
        reposContainer.innerHTML = '<p>Could not load GitHub projects.</p>';
    }
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
    };

    return colors[language] || '#8e8e8e';
}