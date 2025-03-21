// Run when DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
    // Initialize EmailJS
    if (typeof emailjs !== 'undefined') {
        emailjs.init("5XhzQ2uxmMYO1HHL_");
    }

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

            if (typeof emailjs === 'undefined') {
                showMessage(contactForm, 'Error: EmailJS not loaded', 'error');
                return;
            }

            // Disable submit button to prevent multiple submissions
            const submitButton = contactForm.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.innerText = 'Sending...';
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
                        submitButton.innerText = 'Send Message';
                    }
                }, (error) => {
                    console.error('Error sending message:', error);
                    showMessage(contactForm, 'Failed to send message. Please try again.', 'error');

                    // Re-enable button
                    if (submitButton) {
                        submitButton.disabled = false;
                        submitButton.innerText = 'Send Message';
                    }
                });
        });
    }

    // Helper function to show messages
    function showMessage(form, text, type) {
        // Remove any existing message
        const existingMessage = form.querySelector('.success-message, .error-message');
        if (existingMessage) {
            existingMessage.remove();
        }

        // Create message element
        const messageElement = document.createElement('div');
        messageElement.className = type === 'success' ? 'success-message' : 'error-message';
        messageElement.innerText = text;
        form.appendChild(messageElement);

        // Remove message after 5 seconds
        setTimeout(() => {
            messageElement.remove();
        }, 5000);
    }

    // Fetch GitHub Repositories
    fetchGitHubRepos();

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

// Function to fetch and display GitHub repositories
async function fetchGitHubRepos() {
    const reposContainer = document.getElementById('github-repos');
    if (!reposContainer) return;

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
        'Go': '#00ADD8'
    };

    return colors[language] || '#8e8e8e';
}