// NewsBrief Web Interface JavaScript
// v0.3.5.1 Foundation & Navigation

console.log('JavaScript file loaded successfully!');

// Pagination state
let currentPage = 1;
let articlesPerPage = 50;
let totalPages = 1;
let totalArticles = 0;
let currentTopic = ''; // Track current topic filter

document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, initializing NewsBrief...');
    initializeDarkMode();
    initializeViewMode();
    setupEventListeners();
    
    // Load dashboard data if we're on the home page
    if (window.location.pathname === '/') {
        loadDashboardData();
    }
});

// Setup all event listeners
function setupEventListeners() {
    console.log('Setting up event listeners...');
    
    // Dark mode toggle
    const darkModeToggle = document.getElementById('dark-mode-toggle');
    if (darkModeToggle) {
        darkModeToggle.addEventListener('click', toggleDarkMode);
    }
    
    // Topic filter
    const topicFilter = document.getElementById('topic-filter');
    console.log('Topic filter element:', topicFilter);
    if (topicFilter) {
        topicFilter.addEventListener('change', function() {
            currentTopic = this.value;
            console.log('Topic filter changed to:', currentTopic);
            currentPage = 1; // Reset to first page
            loadArticles(currentTopic);
        });
    }
    
    // Per page selector
    const perPageSelector = document.getElementById('per-page-selector');
    console.log('Per page selector element:', perPageSelector);
    if (perPageSelector) {
        perPageSelector.addEventListener('change', function() {
            console.log('Per page selector changed to:', this.value);
            articlesPerPage = parseInt(this.value);
            currentPage = 1; // Reset to first page
            console.log('Loading articles with perPage:', articlesPerPage, 'currentPage:', currentPage);
            loadArticles(currentTopic);
        });
    }
    
    // Pagination buttons
    const prevPageBtn = document.getElementById('prev-page');
    const nextPageBtn = document.getElementById('next-page');
    
    console.log('Prev page button:', prevPageBtn);
    console.log('Next page button:', nextPageBtn);
    
    if (prevPageBtn) {
        prevPageBtn.addEventListener('click', function() {
            console.log('Previous page clicked');
            if (currentPage > 1) {
                currentPage--;
                loadArticles(currentTopic);
            }
        });
    }
    
    if (nextPageBtn) {
        nextPageBtn.addEventListener('click', function() {
            console.log('Next page clicked. Current page:', currentPage, 'Total pages:', totalPages);
            if (currentPage < totalPages) {
                currentPage++;
                console.log('Loading page:', currentPage);
                loadArticles(currentTopic);
            } else {
                console.log('Already at last page');
            }
        });
    }
    
    // View toggle buttons
    const skimViewBtn = document.getElementById('skim-view');
    const fullViewBtn = document.getElementById('full-view');
    
    if (skimViewBtn && fullViewBtn) {
        skimViewBtn.addEventListener('click', function() {
            toggleViewMode('skim');
        });
        
        fullViewBtn.addEventListener('click', function() {
            toggleViewMode('full');
        });
    }
    
    console.log('Event listeners setup complete');
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
    console.log('toggleDarkMode() called');
    const html = document.documentElement;
    const isDark = html.classList.contains('dark');
    
    console.log('Current mode:', isDark ? 'dark' : 'light');
    
    if (isDark) {
        // Switch to light mode
        html.classList.remove('dark');
        localStorage.setItem('newsbrief-theme', 'light');
        console.log('Switched to light mode');
        showNotification('Switched to light mode', 'info');
    } else {
        // Switch to dark mode
        html.classList.add('dark');
        localStorage.setItem('newsbrief-theme', 'dark');
        console.log('Switched to dark mode');
        showNotification('Switched to dark mode', 'info');
    }
    
    // Force DOM reflow to ensure styles are applied
    void html.offsetHeight;
}

function getCurrentTheme() {
    return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
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

// Utility functions
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    
    if (diffHours < 1) return 'Just now';
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString();
}

function getHealthClass(score) {
    if (score >= 90) return 'health-excellent';
    if (score >= 70) return 'health-good';
    return 'health-poor';
}

// ===== PAGINATION AND ARTICLE FUNCTIONS =====

async function loadDashboardData() {
    try {
        console.log('Loading dashboard data...');
        // Load feeds data
        const feedsResponse = await fetch('/feeds');
        console.log('Feeds response status:', feedsResponse.status);
        const feeds = await feedsResponse.json();
        console.log('Feeds data:', feeds);
        
        // Update stats
        const totalArticles = feeds.reduce((sum, f) => sum + (f.total_articles || 0), 0);
        const activeFeeds = feeds.filter(f => !f.disabled).length;
        
        document.getElementById('total-articles').textContent = totalArticles.toLocaleString();
        document.getElementById('active-feeds').textContent = activeFeeds;
        
        // Load articles
        console.log('About to load articles...');
        await loadArticles(currentTopic);
        console.log('Articles loaded successfully');
        
    } catch (error) {
        console.error('Error loading dashboard data:', error);
        document.getElementById('total-articles').textContent = 'Error';
        document.getElementById('active-feeds').textContent = 'Error';
        
        // Hide loading spinner
        const container = document.getElementById('articles-container');
        if (container) {
            container.innerHTML = `
                <div class="text-center py-8 text-red-500">
                    <p>Error loading articles: ${error.message}</p>
                </div>
            `;
        }
    }
}

function toggleViewMode(mode) {
    console.log('toggleViewMode called with mode:', mode);
    const skimBtn = document.getElementById('skim-view');
    const fullBtn = document.getElementById('full-view');
    
    if (!skimBtn || !fullBtn) {
        console.error('View mode buttons not found');
        return;
    }
    
    // Save preference to localStorage
    localStorage.setItem('newsbrief-view-mode', mode);
    
    if (mode === 'skim') {
        // Update button styles - skim active
        skimBtn.className = 'px-3 py-1 text-sm font-medium bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm rounded-md transition-colors';
        fullBtn.className = 'px-3 py-1 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors';
        
        // Apply skim view styles
        document.body.classList.add('skim-view');
        console.log('Skim view activated');
    } else {
        // Update button styles - full active
        fullBtn.className = 'px-3 py-1 text-sm font-medium bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm rounded-md transition-colors';
        skimBtn.className = 'px-3 py-1 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors';
        
        // Remove skim view styles
        document.body.classList.remove('skim-view');
        console.log('Full view activated');
    }
}

function initializeViewMode() {
    // Get saved preference or default to 'full'
    const savedMode = localStorage.getItem('newsbrief-view-mode') || 'full';
    console.log('Initializing view mode:', savedMode);
    toggleViewMode(savedMode);
}

function formatArticleContent(content) {
    if (!content) return 'No content available';
    
    // If content contains HTML tags, strip them and return plain text
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = content;
    const plainText = tempDiv.textContent || tempDiv.innerText || '';
    
    // Truncate if too long
    if (plainText.length > 200) {
        return plainText.substring(0, 200) + '...';
    }
    
    return plainText;
}

function formatArticleSummary(article) {
    // Priority: AI summary > structured summary > fallback summary > original summary
    if (article.ai_summary) {
        return formatArticleContent(article.ai_summary);
    }
    
    if (article.structured_summary && article.structured_summary.bullets) {
        const bullets = article.structured_summary.bullets.slice(0, 3); // Show first 3 bullets
        return bullets.map(bullet => `• ${bullet}`).join('<br>');
    }
    
    if (article.fallback_summary) {
        return formatArticleContent(article.fallback_summary);
    }
    
    if (article.summary) {
        return formatArticleContent(article.summary);
    }
    
    return 'No summary available. Click "Read Full Article" to view the complete content.';
}

function getTopicDisplayName(topic) {
    const topics = {
        'ai-ml': 'AI/ML',
        'cloud-k8s': 'Cloud/K8s',
        'security': 'Security',
        'devtools': 'DevTools',
        'chips-hardware': 'Chips/Hardware',
        'general': 'General News'
    };
    return topics[topic] || topic;
}

function getTopicBadgeClasses(topic) {
    const classes = {
        'ai-ml': 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
        'cloud-k8s': 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
        'security': 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
        'devtools': 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
        'chips-hardware': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
        'general': 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200'
    };
    return classes[topic] || 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200';
}

async function loadArticles(selectedTopic = '') {
    try {
        console.log('loadArticles called with topic:', selectedTopic, 'page:', currentPage, 'perPage:', articlesPerPage);
        const offset = (currentPage - 1) * articlesPerPage;
        console.log('Calculated offset:', offset);
        
        // Use topic-specific endpoint if topic is selected
        let apiUrl = `/items?limit=${articlesPerPage}&offset=${offset}`;
        if (selectedTopic && selectedTopic.trim() !== '') {
            apiUrl = `/items/topic/${selectedTopic}?limit=${articlesPerPage}&offset=${offset}`;
        }
        
        console.log('API URL:', apiUrl);
        const response = await fetch(apiUrl);
        console.log('Response status:', response.status);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        let articles;
        if (selectedTopic && selectedTopic.trim() !== '') {
            // Topic endpoint returns {topic, display_name, count, items}
            const data = await response.json();
            console.log('Topic endpoint data:', data);
            articles = data.items || [];
            totalArticles = data.count || 0;
            console.log('Topic endpoint response - articles:', articles.length, 'total:', totalArticles);
        } else {
            // Main endpoint returns array directly
            articles = await response.json();
            console.log('Main endpoint response - articles:', articles.length);
            
            // Get total count for pagination
            const countResponse = await fetch('/items/count');
            if (countResponse.ok) {
                const countData = await countResponse.json();
                totalArticles = countData.count || 0;
                console.log('Total articles count:', totalArticles);
            }
        }
        
        // Calculate total pages
        totalPages = Math.ceil(totalArticles / articlesPerPage);
        console.log('Calculated total pages:', totalPages);
        
        updateArticlesDisplay(articles);
        updatePaginationControls();
        
    } catch (error) {
        console.error('Error loading articles:', error);
        showNotification('Failed to load articles', 'error');
        
        // Show error in articles container
        const container = document.getElementById('articles-container');
        if (container) {
            container.innerHTML = `
                <div class="text-center py-8 text-red-500">
                    <p>Error loading articles: ${error.message}</p>
                    <button onclick="loadArticles('${currentTopic}')" class="mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
                        Retry
                    </button>
                </div>
            `;
        }
    }
}

function updateArticlesDisplay(articles) {
    console.log('updateArticlesDisplay called with', articles.length, 'articles');
    const container = document.getElementById('articles-container');
    console.log('Articles container:', container);
    
    if (articles.length === 0) {
        container.innerHTML = `
            <div class="text-center py-8 text-gray-500 dark:text-gray-400">
                <p>No articles found. Try refreshing feeds!</p>
            </div>
        `;
        return;
    }
    
    try {
        container.innerHTML = articles.map(article => `
            <article class="article-card border border-gray-200 dark:border-gray-700 rounded-lg p-6 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
                <div class="flex justify-between items-start mb-3">
                    <h3 class="font-semibold text-lg text-gray-900 dark:text-white line-clamp-2 flex-1">
                        <a href="/article/${article.id}" class="article-title-link hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
                            ${escapeHtml(article.title || 'Untitled')}
                        </a>
                    </h3>
                    <div class="flex items-center space-x-2 ml-4">
                        ${article.topic ? `<span class="topic-badge inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getTopicBadgeClasses(article.topic)}">${getTopicDisplayName(article.topic)}</span>` : '<span class="topic-badge inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200">Unclassified</span>'}
                        <span class="text-xs text-gray-500 dark:text-gray-400">
                            ${article.published ? new Date(article.published).toLocaleDateString() : 'No date'}
                        </span>
                    </div>
                </div>
                
                <div class="article-content text-gray-700 dark:text-gray-300 mb-4">
                    ${formatArticleSummary(article)}
                </div>
                
                <div class="flex justify-between items-center">
                    <div class="flex space-x-4">
                        <a href="/article/${article.id}" class="article-detail-link text-blue-600 hover:text-blue-800 dark:text-blue-400 text-sm font-medium">
                            Read Full Article →
                        </a>
                        <a href="${article.url}" target="_blank" class="article-external-link text-gray-600 hover:text-gray-800 dark:text-gray-400 text-sm">
                            Original Source
                        </a>
                    </div>
                    <div class="flex items-center space-x-2">
                        <span class="text-xs text-gray-500 dark:text-gray-400">
                            Score: ${article.ranking_score ? article.ranking_score.toFixed(3) : 'N/A'}
                        </span>
                        ${article.ai_summary ? '<span class="ai-indicator text-xs bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200 px-2 py-1 rounded">AI Summary</span>' : ''}
                    </div>
                </div>
            </article>
        `).join('');
        console.log('Articles display updated successfully');
    } catch (error) {
        console.error('Error updating articles display:', error);
        container.innerHTML = `
            <div class="text-center py-8 text-red-500">
                <p>Error displaying articles: ${error.message}</p>
            </div>
        `;
    }
}

function updatePaginationControls() {
    const prevBtn = document.getElementById('prev-page');
    const nextBtn = document.getElementById('next-page');
    const pageInfo = document.getElementById('page-info');
    const articlesCount = document.getElementById('articles-count');
    
    // Update button states
    if (prevBtn) {
        prevBtn.disabled = currentPage <= 1;
    }
    
    if (nextBtn) {
        nextBtn.disabled = currentPage >= totalPages;
    }
    
    // Update page info
    if (pageInfo) {
        pageInfo.textContent = `Page ${currentPage} of ${totalPages}`;
    }
    
    // Update articles count
    if (articlesCount) {
        articlesCount.textContent = totalArticles.toLocaleString();
    }
}

// Refresh functionality
async function refreshFeeds() {
    const refreshBtn = document.querySelector('button[onclick="refreshFeeds()"]');
    const originalText = refreshBtn.innerHTML;
    
    refreshBtn.innerHTML = `
        <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
        <span>Refreshing...</span>
    `;
    refreshBtn.disabled = true;
    
    try {
        const response = await fetch('/refresh', { method: 'POST' });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const result = await response.json();
        
        // Show success notification
        showNotification(`Refreshed! Added ${result.ingested || 0} new articles`, 'success');
        
        // Reload dashboard data
        setTimeout(() => {
            loadDashboardData();
        }, 1000);
        
    } catch (error) {
        console.error('Refresh error:', error);
        showNotification(`Failed to refresh feeds: ${error.message}`, 'error');
    } finally {
        refreshBtn.innerHTML = originalText;
        refreshBtn.disabled = false;
    }
}