// NewsBrief Web Interface JavaScript
// v0.5.1 Foundation & Navigation

document.addEventListener('DOMContentLoaded', function() {
    loadArticles();
});

async function loadArticles() {
    const container = document.getElementById('articles-container');
    const loading = document.getElementById('loading');
    
    try {
        loading.classList.remove('hidden');
        container.innerHTML = '';
        
        const response = await fetch('/items?limit=20');
        const articles = await response.json();
        
        loading.classList.add('hidden');
        
        if (articles.length === 0) {
            container.innerHTML = `
                <div class="text-center py-12 text-gray-500 dark:text-gray-400">
                    <p>No articles found. Try adding some RSS feeds!</p>
                    <a href="/feeds" class="text-blue-600 hover:text-blue-800 dark:text-blue-400 mt-2 inline-block">Manage Feeds</a>
                </div>
            `;
            return;
        }
        
        articles.forEach(article => {
            const articleElement = createArticleElement(article);
            container.appendChild(articleElement);
        });
        
        // Show load more button if we have full page
        if (articles.length === 20) {
            document.getElementById('load-more-container').classList.remove('hidden');
        }
        
    } catch (error) {
        loading.classList.add('hidden');
        container.innerHTML = `
            <div class="text-center py-12 text-red-500">
                <p>Error loading articles. Please try again.</p>
                <button onclick="loadArticles()" class="text-blue-600 hover:text-blue-800 mt-2">Retry</button>
            </div>
        `;
    }
}

function createArticleElement(article) {
    const template = document.getElementById('article-template');
    const element = template.content.cloneNode(true);
    
    // Set topic badge
    const topicBadge = element.querySelector('.topic-badge');
    if (article.topic) {
        topicBadge.textContent = getTopicDisplayName(article.topic);
        topicBadge.className = `topic-badge inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getTopicBadgeClasses(article.topic)}`;
    } else {
        topicBadge.style.display = 'none';
    }
    
    // Set ranking score
    const rankingScore = element.querySelector('.ranking-score');
    rankingScore.textContent = `Score: ${article.ranking_score?.toFixed(3) || 'N/A'}`;
    
    // Set published date
    const publishedDate = element.querySelector('.published-date');
    if (article.published) {
        publishedDate.textContent = new Date(article.published).toLocaleDateString();
    } else {
        publishedDate.textContent = 'No date';
    }
    
    // Set title
    const title = element.querySelector('.article-title');
    title.textContent = article.title || 'Untitled';
    
    // Set content (AI summary or fallback)
    const content = element.querySelector('.article-content');
    if (article.structured_summary) {
        // Show structured summary
        const bullets = article.structured_summary.bullets || [];
        const whyItMatters = article.structured_summary.why_it_matters || '';
        
        content.innerHTML = `
            <div class="space-y-3">
                ${bullets.length > 0 ? `
                    <div>
                        <h4 class="font-medium text-gray-900 dark:text-white mb-2">Key Points:</h4>
                        <ul class="list-disc list-inside space-y-1 text-gray-700 dark:text-gray-300 text-sm">
                            ${bullets.map(bullet => `<li>${bullet}</li>`).join('')}
                        </ul>
                    </div>
                ` : ''}
                ${whyItMatters ? `
                    <div>
                        <h4 class="font-medium text-gray-900 dark:text-gray-300 mb-2">Why it matters:</h4>
                        <p class="text-gray-700 dark:text-gray-300 text-sm">${whyItMatters}</p>
                    </div>
                ` : ''}
            </div>
        `;
        element.querySelector('.ai-indicator').classList.remove('hidden');
    } else if (article.fallback_summary) {
        content.innerHTML = `<p class="text-gray-700 dark:text-gray-300">${article.fallback_summary}</p>`;
    } else if (article.summary) {
        content.innerHTML = `<p class="text-gray-700 dark:text-gray-300">${article.summary}</p>`;
    } else {
        content.innerHTML = `<p class="text-gray-500 dark:text-gray-400 italic">No summary available</p>`;
    }
    
    // Set article link
    const articleLink = element.querySelector('.article-link');
    articleLink.href = article.url;
    articleLink.target = '_blank';
    
    // Make title clickable too
    title.onclick = () => window.open(article.url, '_blank');
    
    return element;
}

function getTopicDisplayName(topic) {
    const topics = {
        'ai-ml': 'AI/ML',
        'cloud-k8s': 'Cloud/K8s',
        'security': 'Security',
        'devtools': 'DevTools',
        'chips-hardware': 'Chips/Hardware'
    };
    return topics[topic] || topic;
}

function getTopicBadgeClasses(topic) {
    const classes = {
        'ai-ml': 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
        'cloud-k8s': 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
        'security': 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
        'devtools': 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
        'chips-hardware': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
    };
    return classes[topic] || 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200';
}

// Utility functions
function formatDate(dateString) {
    if (!dateString) return 'No date';
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffHours / 24);
    
    if (diffHours < 1) return 'Just now';
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
}

// Refresh functionality
async function refreshFeeds() {
    const refreshBtn = document.querySelector('button[onclick="refreshFeeds()"]');
    const originalText = refreshBtn.innerHTML;
    
    refreshBtn.innerHTML = `
        <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
        <span>Refreshing...</span>
    `;
    refreshBtn.disabled = true;
    
    try {
        const response = await fetch('/refresh', { method: 'POST' });
        const result = await response.json();
        
        // Show success notification
        showNotification(`Refreshed! Added ${result.items_added || 0} new articles`, 'success');
        
        // Reload articles
        setTimeout(() => {
            loadArticles();
        }, 1000);
        
    } catch (error) {
        showNotification('Failed to refresh feeds', 'error');
    } finally {
        refreshBtn.innerHTML = originalText;
        refreshBtn.disabled = false;
    }
}

// Notification system
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 px-4 py-2 rounded-md text-white text-sm font-medium z-50 ${
        type === 'success' ? 'bg-green-500' :
        type === 'error' ? 'bg-red-500' :
        'bg-blue-500'
    }`;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    // Auto-remove after 3 seconds
    setTimeout(() => {
        notification.remove();
    }, 3000);
}
