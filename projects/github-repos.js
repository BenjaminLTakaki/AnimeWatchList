// Function to fetch and display GitHub repositories 
async function fetchAndDisplayRepos() {
    const githubUsername = 'BenjaminLTakaki';
    const reposContainer = document.getElementById('github-repos');

    if (!reposContainer) return;

    try {
        // Make request to GitHub API
        const response = await fetch(`https://api.github.com/users/${githubUsername}/repos?sort=updated&per_page=10`);

        if (!response.ok) {
            throw new Error(`GitHub API error: ${response.status}`);
        }

        const repos = await response.json();

        // Remove loading indicator
        reposContainer.innerHTML = '';

        // Filter out repos that are forks or empty
        const filteredRepos = repos.filter(repo =>
            !repo.fork &&
            repo.name.toLowerCase() !== 'benjaminltakaki' &&
            repo.name.toLowerCase() !== 'portfoliowebsite'
        );

        if (filteredRepos.length === 0) {
            reposContainer.innerHTML = '<p class="no-repos">No repositories found.</p>';
            return;
        }

        // Sort repos by last updated date
        filteredRepos.sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));

        // Display up to 6 repositories
        filteredRepos.slice(0, 6).forEach(repo => {
            const repoCard = document.createElement('div');
            repoCard.className = 'repo';

            // Format created date
            const createdDate = new Date(repo.created_at);
            const formattedDate = createdDate.toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'short'
            });

            // Determine if has a demo link
            const hasDemo = repo.homepage || (repo.has_pages && repo.name);
            const demoUrl = repo.homepage || (repo.has_pages ? `https://${githubUsername}.github.io/${repo.name}` : null);

            // Get language color
            const languageColor = getLanguageColor(repo.language);

            // Limit description length
            const description = repo.description
                ? (repo.description.length > 100 ? repo.description.substring(0, 100) + '...' : repo.description)
                : 'No description available.';

            repoCard.innerHTML = `
                <h3>
                    <a href="${repo.html_url}" target="_blank" rel="noopener noreferrer">
                        ${repo.name}
                    </a>
                </h3>
                <p>${description}</p>
                <div class="repo-meta">
                    <span class="repo-language">
                        ${repo.language ?
                    `<span class="repo-language-color" style="background-color: ${languageColor}"></span>
                            ${repo.language}` :
                    'N/A'}
                    </span>
                    <span class="repo-date">Created: ${formattedDate}</span>
                </div>
                <div class="project-links">
                    <a href="${repo.html_url}" target="_blank" rel="noopener noreferrer" class="btn-secondary">
                        <i class="fab fa-github"></i> View Code
                    </a>
                    ${hasDemo ?
                    `<a href="${demoUrl}" target="_blank" rel="noopener noreferrer" class="btn-primary">
                            <i class="fas fa-external-link-alt"></i> Live Demo
                        </a>` :
                    ''}
                </div>
            `;

            reposContainer.appendChild(repoCard);
        });

    } catch (error) {
        console.error('Error fetching GitHub repositories:', error);
        reposContainer.innerHTML = `
            <div class="error-message">
                <p><i class="fas fa-exclamation-triangle"></i> Unable to load GitHub repositories. Please try again later.</p>
                <p class="error-details">${error.message}</p>
            </div>
        `;
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
        'Swift': '#ffac45',
        'Kotlin': '#F18E33',
        'Dart': '#00B4AB',
        'Rust': '#dea584'
    };

    return colors[language] || '#8e8e8e';
}

// Call this function when DOM is loaded
document.addEventListener('DOMContentLoaded', fetchAndDisplayRepos);