// NewsBrief Web Interface JavaScript
// v0.5.1 Foundation & Navigation

document.addEventListener('DOMContentLoaded', function() {
    initializeDarkMode();
    loadArticles();
    setupEventListeners();
});

// Setup all event listeners
function setupEventListeners() {
    // Dark mode toggle
    const darkModeToggle = document.getElementById('dark-mode-toggle');
    if (darkModeToggle) {
        darkModeToggle.addEventListener('click', toggleDarkMode);
    }
    
    // Topic filter dropdown
    const topicSelect = document.querySelector('select');
    if (topicSelect) {
        topicSelect.addEventListener('change', function() {
            const selectedTopic = this.value;
            loadArticles(selectedTopic);
        });
    }
    
    // View toggle buttons (skim/detail)
    const viewButtons = document.querySelectorAll('.flex.bg-gray-100 button');
    viewButtons.forEach(button => {
        button.addEventListener('click', function() {
            // Remove active class from all buttons
            viewButtons.forEach(btn => {
                btn.className = 'px-3 py-1 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white';
            });
            // Add active class to clicked button
            this.className = 'px-3 py-1 text-sm font-medium bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm rounded-md';
            
            // TODO: Implement view switching logic
            const isSkimView = this.textContent.trim() === 'Skim';
            console.log('View switched to:', isSkimView ? 'Skim' : 'Detailed');
        });
    });
    
    // Load more button
    const loadMoreBtn = document.getElementById('load-more-btn');
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', loadMoreArticles);
    }
}

async function loadArticles(selectedTopic = '') {
    const container = document.getElementById('articles-container');
    const loading = document.getElementById('loading');
    
    try {
        loading.classList.remove('hidden');
        container.innerHTML = '';
        
        // Use topic-specific endpoint if topic is selected
        let apiUrl = '/items?limit=20';
        if (selectedTopic) {
            apiUrl = `/items/topic/${selectedTopic}?limit=20`;
        }
        
        console.log('Loading articles from:', apiUrl);
        const response = await fetch(apiUrl);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        let articles;
        if (selectedTopic) {
            // Topic endpoint returns {topic, display_name, count, items}
            const data = await response.json();
            articles = data.items || [];
        } else {
            // Main endpoint returns array directly
            articles = await response.json();
        }
        
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
                <p>Error loading articles: ${error.message}</p>
                <button onclick="loadArticles()" class="text-blue-600 hover:text-blue-800 mt-2 underline">Retry</button>
            </div>
        `;
        console.error('Error loading articles:', error);
    }
}

// Load more articles (pagination)
async function loadMoreArticles() {
    const container = document.getElementById('articles-container');
    const loadMoreBtn = document.getElementById('load-more-btn');
    const currentArticles = container.querySelectorAll('article').length;
    
    try {
        loadMoreBtn.textContent = 'Loading...';
        loadMoreBtn.disabled = true;
        
        const response = await fetch(`/items?limit=20&offset=${currentArticles}`);
        const articles = await response.json();
        
        articles.forEach(article => {
            const articleElement = createArticleElement(article);
            container.appendChild(articleElement);
        });
        
        if (articles.length < 20) {
            loadMoreBtn.style.display = 'none';
        } else {
            loadMoreBtn.textContent = 'Load More Articles';
            loadMoreBtn.disabled = false;
        }
        
    } catch (error) {
        loadMoreBtn.textContent = 'Error - Try Again';
        loadMoreBtn.disabled = false;
        showNotification('Failed to load more articles', 'error');
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
    
    // Set title with link to detail page
    const titleLink = element.querySelector('.article-title-link');
    titleLink.textContent = article.title || 'Untitled';
    titleLink.href = `/article/${article.id}`;
    
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
    
    // Set article detail link
    const articleDetailLink = element.querySelector('.article-detail-link');
    articleDetailLink.href = `/article/${article.id}`;
    
    // Set external article link
    const articleExternalLink = element.querySelector('.article-external-link');
    articleExternalLink.href = article.url;
    articleExternalLink.target = '_blank';
    
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
    console.log('refreshFeeds() called');
    const refreshBtn = document.querySelector('button[onclick="refreshFeeds()"]');
    
    if (!refreshBtn) {
        console.error('Refresh button not found');
        return;
    }
    
    const originalText = refreshBtn.innerHTML;
    
    refreshBtn.innerHTML = `
        <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
        <span>Refreshing...</span>
    `;
    refreshBtn.disabled = true;
    
    try {
        console.log('Calling /refresh API...');
        const response = await fetch('/refresh', { method: 'POST' });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const result = await response.json();
        console.log('Refresh result:', result);
        
        // Show success notification
        showNotification(`Refreshed! Added ${result.items_added || 0} new articles`, 'success');
        
        // Reload articles with current topic filter
        const topicSelect = document.querySelector('select');
        const currentTopic = topicSelect ? topicSelect.value : '';
        
        setTimeout(() => {
            loadArticles(currentTopic);
        }, 1000);
        
    } catch (error) {
        console.error('Refresh error:', error);
        showNotification(`Failed to refresh feeds: ${error.message}`, 'error');
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

// ===== DARK MODE FUNCTIONALITY =====

function initializeDarkMode() {
    // Check for saved theme preference or default to light mode
    const savedTheme = localStorage.getItem('newsbrief-theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    // Determine initial theme
    const initialTheme = savedTheme || (prefersDark ? 'dark' : 'light');
    
    // Apply theme
    if (initialTheme === 'dark') {
        document.documentElement.classList.add('dark');
    } else {
        document.documentElement.classList.remove('dark');
    }
    
    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (!localStorage.getItem('newsbrief-theme')) {
            // Only auto-switch if user hasn't set a preference
            if (e.matches) {
                document.documentElement.classList.add('dark');
            } else {
                document.documentElement.classList.remove('dark');
            }
        }
    });
}

function toggleDarkMode() {
    const html = document.documentElement;
    const isDark = html.classList.contains('dark');
    
    if (isDark) {
        // Switch to light mode
        html.classList.remove('dark');
        localStorage.setItem('newsbrief-theme', 'light');
        showNotification('Switched to light mode', 'info');
    } else {
        // Switch to dark mode
        html.classList.add('dark');
        localStorage.setItem('newsbrief-theme', 'dark');
        showNotification('Switched to dark mode', 'info');
    }
}

function getCurrentTheme() {
    return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
}
