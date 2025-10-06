// NewsBrief Web Interface JavaScript
// v0.3.5.1 Foundation & Navigation

document.addEventListener('DOMContentLoaded', function() {
    initializeDarkMode();
    setupEventListeners();
});

// Setup all event listeners
function setupEventListeners() {
    // Dark mode toggle
    const darkModeToggle = document.getElementById('dark-mode-toggle');
    if (darkModeToggle) {
        darkModeToggle.addEventListener('click', toggleDarkMode);
    }
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
