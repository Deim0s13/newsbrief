// NewsBrief Stories Page JavaScript
// Handles story listing, filtering, and display

document.addEventListener('DOMContentLoaded', function() {
    loadStories();
    setupEventListeners();
});

// Setup all event listeners
function setupEventListeners() {
    // Filter changes
    const statusFilter = document.getElementById('status-filter');
    const sortFilter = document.getElementById('sort-filter');
    const topicFilter = document.getElementById('topic-filter');
    const interestsToggle = document.getElementById('interests-toggle');

    if (statusFilter) {
        statusFilter.addEventListener('change', loadStories);
    }
    if (sortFilter) {
        sortFilter.addEventListener('change', loadStories);
    }
    if (topicFilter) {
        topicFilter.addEventListener('change', loadStories);
    }
    if (interestsToggle) {
        interestsToggle.addEventListener('change', loadStories);
    }

    // Load more button
    const loadMoreBtn = document.getElementById('load-more-btn');
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', loadMoreStories);
    }
}

async function loadStories() {
    const container = document.getElementById('stories-container');
    const loading = document.getElementById('loading');
    const statsDiv = document.getElementById('story-stats');
    const countText = document.getElementById('story-count-text');

    try {
        loading.classList.remove('hidden');
        container.innerHTML = '';
        statsDiv.classList.add('hidden');

        // Get filter values
        const status = document.getElementById('status-filter').value;
        const orderBy = document.getElementById('sort-filter').value;
        const topic = document.getElementById('topic-filter')?.value || '';
        const applyInterests = document.getElementById('interests-toggle')?.checked ?? true;

        // Build API URL
        const params = new URLSearchParams({
            limit: '20',
            offset: '0',
            status: status,
            order_by: orderBy,
            apply_interests: applyInterests.toString()
        });

        // Add topic filter if selected
        if (topic) {
            params.set('topic', topic);
        }

        const apiUrl = `/stories?${params.toString()}`;
        console.log('Loading stories from:', apiUrl);

        const response = await fetch(apiUrl);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        console.log('Loaded stories:', data);

        loading.classList.add('hidden');

        // Show stats
        if (data.total !== undefined) {
            countText.textContent = `Showing ${data.stories.length} of ${data.total} stories`;
            statsDiv.classList.remove('hidden');
        }

        if (data.stories.length === 0) {
            container.innerHTML = `
                <div class="text-center py-12 text-gray-500 dark:text-gray-400">
                    <svg class="mx-auto h-16 w-16 mb-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z"></path>
                    </svg>
                    <p class="text-lg font-medium mb-2">No stories yet</p>
                    <p class="text-sm mb-4">Generate your first stories from recent articles</p>
                    <button onclick="refreshStories()" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-md">
                        Generate Stories Now
                    </button>
                </div>
            `;
            return;
        }

        data.stories.forEach(story => {
            const storyElement = createStoryElement(story);
            container.appendChild(storyElement);
        });

        // Show load more button if there are more stories
        if (data.stories.length === 20 && data.total > 20) {
            document.getElementById('load-more-container').classList.remove('hidden');
        } else {
            document.getElementById('load-more-container').classList.add('hidden');
        }

    } catch (error) {
        loading.classList.add('hidden');
        container.innerHTML = `
            <div class="text-center py-12">
                <div class="text-red-500 mb-4">
                    <svg class="mx-auto h-12 w-12 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <p class="font-medium">Error loading stories</p>
                    <p class="text-sm mt-1">${error.message}</p>
                </div>
                <button onclick="loadStories()" class="text-blue-600 hover:text-blue-800 underline">Retry</button>
            </div>
        `;
        console.error('Error loading stories:', error);
    }
}

// Load more stories (pagination)
async function loadMoreStories() {
    const container = document.getElementById('stories-container');
    const loadMoreBtn = document.getElementById('load-more-btn');
    const currentStories = container.querySelectorAll('article').length;

    try {
        loadMoreBtn.textContent = 'Loading...';
        loadMoreBtn.disabled = true;

        const status = document.getElementById('status-filter').value;
        const orderBy = document.getElementById('sort-filter').value;
        const topic = document.getElementById('topic-filter')?.value || '';
        const applyInterests = document.getElementById('interests-toggle')?.checked ?? true;

        const params = new URLSearchParams({
            limit: '20',
            offset: currentStories.toString(),
            status: status,
            order_by: orderBy,
            apply_interests: applyInterests.toString()
        });

        // Add topic filter if selected
        if (topic) {
            params.set('topic', topic);
        }

        const response = await fetch(`/stories?${params.toString()}`);
        const data = await response.json();

        data.stories.forEach(story => {
            const storyElement = createStoryElement(story);
            container.appendChild(storyElement);
        });

        if (data.stories.length < 20 || container.querySelectorAll('article').length >= data.total) {
            document.getElementById('load-more-container').classList.add('hidden');
        } else {
            loadMoreBtn.textContent = 'Load More Stories';
            loadMoreBtn.disabled = false;
        }

        // Update count
        document.getElementById('story-count-text').textContent =
            `Showing ${container.querySelectorAll('article').length} of ${data.total} stories`;

    } catch (error) {
        loadMoreBtn.textContent = 'Error - Try Again';
        loadMoreBtn.disabled = false;
        console.error('Failed to load more stories:', error);
    }
}

function createStoryElement(story) {
    const template = document.getElementById('story-template');
    const element = template.content.cloneNode(true);

    // Title
    element.querySelector('.story-title').textContent = story.title;

    // Synthesis preview (first 200 chars)
    const synthesisDiv = element.querySelector('.story-synthesis');
    synthesisDiv.textContent = story.synthesis.length > 200
        ? story.synthesis.substring(0, 200) + '...'
        : story.synthesis;

    // Topics (show first 3)
    const topicsSpan = element.querySelector('.story-topics');
    if (story.topics && story.topics.length > 0) {
        const topicBadges = story.topics.slice(0, 3).map(topic => {
            const color = getTopicColor(topic);
            return `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${color}">${topic}</span>`;
        }).join(' ');
        topicsSpan.innerHTML = topicBadges;
    }

    // Article count
    element.querySelector('.article-count-number').textContent = `${story.article_count} sources`;

    // Scores
    const scoresSpan = element.querySelector('.story-scores');
    scoresSpan.textContent = `I:${(story.importance_score * 100).toFixed(0)} F:${(story.freshness_score * 100).toFixed(0)}`;
    scoresSpan.title = `Importance: ${(story.importance_score * 100).toFixed(0)}%, Freshness: ${(story.freshness_score * 100).toFixed(0)}%`;

    // Time
    const timeElement = element.querySelector('.story-time');
    timeElement.textContent = formatTimeAgo(story.generated_at);
    timeElement.title = new Date(story.generated_at).toLocaleString();

    // Key points (show first 2)
    const keyPointsList = element.querySelector('.story-key-points ul');
    if (story.key_points && story.key_points.length > 0) {
        story.key_points.slice(0, 2).forEach(point => {
            const li = document.createElement('li');
            li.className = 'flex items-start';
            li.innerHTML = `
                <svg class="h-4 w-4 text-blue-600 dark:text-blue-400 mr-2 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>
                </svg>
                <span>${point}</span>
            `;
            keyPointsList.appendChild(li);
        });

        // Add "more" indicator if there are more points
        if (story.key_points.length > 2) {
            const li = document.createElement('li');
            li.className = 'text-xs text-gray-500 dark:text-gray-400 ml-6';
            li.textContent = `+${story.key_points.length - 2} more key points`;
            keyPointsList.appendChild(li);
        }
    }

    // Why it matters
    const whyMattersDiv = element.querySelector('.story-why-matters');
    const whyMattersText = element.querySelector('.why-matters-text');
    if (story.why_it_matters && story.why_it_matters.trim()) {
        whyMattersText.textContent = story.why_it_matters;
        whyMattersDiv.classList.remove('hidden');
    }

    // Entities (show first 5)
    const entitiesSpan = element.querySelector('.story-entities');
    if (story.entities && story.entities.length > 0) {
        const entityList = story.entities.slice(0, 5).join(', ');
        entitiesSpan.innerHTML = `<strong>Entities:</strong> ${entityList}${story.entities.length > 5 ? '...' : ''}`;
    }

    // Link to story detail
    const storyLink = element.querySelector('.story-link');
    storyLink.href = `/story/${story.id}`;

    // Make entire card clickable
    const article = element.querySelector('article');
    article.addEventListener('click', function(e) {
        // Don't navigate if clicking the link directly
        if (e.target.closest('.story-link')) {
            return;
        }
        window.location.href = `/story/${story.id}`;
    });

    return element;
}

// Refresh stories (trigger generation)
async function refreshStories() {
    const btn = document.getElementById('refresh-stories-btn');
    const originalContent = btn.innerHTML;

    try {
        // Disable button and show loading state
        btn.disabled = true;
        btn.innerHTML = `
            <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
            <span>Generating...</span>
        `;

        // Show notification
        showNotification('Generating stories from recent articles... This may take a few minutes.', 'info');

        // Trigger story generation (this may take a while)
        const response = await fetch('/stories/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                time_window_hours: 24,
                min_articles_per_story: 2,
                similarity_threshold: 0.3,
                model: "llama3.1:8b"
            })
        });

        if (!response.ok) {
            throw new Error(`Generation failed: ${response.statusText}`);
        }

        const result = await response.json();

        // v0.6.1: Show detailed message based on results
        if (result.stories_generated > 0) {
            showNotification(`Successfully generated ${result.stories_generated} stories!`, 'success');
        } else if (result.message) {
            // Show helpful message explaining why 0 stories
            showNotification(result.message, 'info');
        } else {
            showNotification(`Generation complete: ${result.stories_generated} stories created.`, 'info');
        }

        // Reload stories
        setTimeout(() => {
            loadStories();
        }, 1000);

    } catch (error) {
        console.error('Story generation error:', error);
        showNotification(`Failed to generate stories: ${error.message}`, 'error');
    } finally {
        // Re-enable button
        btn.disabled = false;
        btn.innerHTML = originalContent;
    }
}

// Helper: Get topic color
function getTopicColor(topic) {
    const colors = {
        'ai-ml': 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
        'security': 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
        'cloud-k8s': 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
        'devtools': 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
        'chips-hardware': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
        'databases': 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200',
        'programming': 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200'
    };
    return colors[topic] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200';
}

// Helper: Format time ago
function formatTimeAgo(timestamp) {
    const now = new Date();
    const past = new Date(timestamp);
    const seconds = Math.floor((now - past) / 1000);

    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
    return past.toLocaleDateString();
}

// Helper: Show notification
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 z-50 max-w-md p-4 rounded-lg shadow-lg border transition-all transform ${
        type === 'success' ? 'bg-green-50 dark:bg-green-900 border-green-200 dark:border-green-700 text-green-800 dark:text-green-200' :
        type === 'error' ? 'bg-red-50 dark:bg-red-900 border-red-200 dark:border-red-700 text-red-800 dark:text-red-200' :
        'bg-blue-50 dark:bg-blue-900 border-blue-200 dark:border-blue-700 text-blue-800 dark:text-blue-200'
    }`;

    notification.innerHTML = `
        <div class="flex items-start">
            <svg class="h-5 w-5 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                ${type === 'success' ?
                    '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>' :
                    '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>'
                }
            </svg>
            <div class="flex-1">
                <p class="text-sm font-medium">${message}</p>
            </div>
            <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-current hover:opacity-75">
                <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                </svg>
            </button>
        </div>
    `;

    document.body.appendChild(notification);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}
