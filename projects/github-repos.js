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