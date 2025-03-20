emailjs.init("5XhzQ2uxmMYO1HHL_");

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

// Fetch GitHub Repositories
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

                repoCard.innerHTML = `
                    <h3><a href="${repo.html_url}" target="_blank" rel="noopener noreferrer">${repo.name}</a></h3>
                    <p>${repo.description || 'No description available.'}</p>
                    <div class="repo-meta">
                        <span class="repo-language">
                            ${repo.language ? `<span class="repo-language-color" style="background-color: ${getLanguageColor(repo.language)}"></span>${repo.language}` : 'N/A'}
                        </span>
                        <span class="repo-date">Created: ${formattedDate}</span>
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