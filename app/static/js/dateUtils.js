/**
 * Centralized date formatting utilities with locale support.
 *
 * Uses browser locale by default, can be overridden via localStorage.
 * Key: 'newsbrief_date_locale'
 */

const DateUtils = (function() {
    // Get user's preferred locale (from localStorage or browser)
    function getLocale() {
        // Check for user override in localStorage
        const savedLocale = localStorage.getItem('newsbrief_date_locale');
        if (savedLocale) {
            return savedLocale;
        }
        // Fall back to browser locale
        return navigator.language || navigator.userLanguage || 'en-NZ';
    }

    // Set user's preferred locale
    function setLocale(locale) {
        localStorage.setItem('newsbrief_date_locale', locale);
    }

    // Clear user's preferred locale (revert to browser default)
    function clearLocale() {
        localStorage.removeItem('newsbrief_date_locale');
    }

    // Ensure timestamp is treated as UTC if no timezone specified
    function normalizeTimestamp(timestamp) {
        if (!timestamp) return null;
        let ts = String(timestamp);
        // Add Z suffix if no timezone indicator present
        if (ts && !ts.endsWith('Z') && !ts.includes('+') && !ts.includes('-', 10)) {
            ts = ts + 'Z';
        }
        return ts;
    }

    // Parse a date string to Date object
    function parseDate(dateString) {
        if (!dateString) return null;
        const normalized = normalizeTimestamp(dateString);
        const date = new Date(normalized);
        return isNaN(date.getTime()) ? null : date;
    }

    /**
     * Format a date as a short date string (e.g., "22/01/2026" for en-NZ)
     */
    function formatShortDate(dateInput) {
        const date = dateInput instanceof Date ? dateInput : parseDate(dateInput);
        if (!date) return 'No date';

        return date.toLocaleDateString(getLocale(), {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
        });
    }

    /**
     * Format a date as a medium date string (e.g., "22 Jan 2026" for en-NZ)
     */
    function formatMediumDate(dateInput) {
        const date = dateInput instanceof Date ? dateInput : parseDate(dateInput);
        if (!date) return 'No date';

        return date.toLocaleDateString(getLocale(), {
            day: 'numeric',
            month: 'short',
            year: 'numeric'
        });
    }

    /**
     * Format a date as a long date string (e.g., "22 January 2026" for en-NZ)
     */
    function formatLongDate(dateInput) {
        const date = dateInput instanceof Date ? dateInput : parseDate(dateInput);
        if (!date) return 'No date';

        return date.toLocaleDateString(getLocale(), {
            day: 'numeric',
            month: 'long',
            year: 'numeric'
        });
    }

    /**
     * Format a date with time (e.g., "22/01/2026, 14:30" for en-NZ)
     */
    function formatDateTime(dateInput) {
        const date = dateInput instanceof Date ? dateInput : parseDate(dateInput);
        if (!date) return 'No date';

        return date.toLocaleString(getLocale(), {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    /**
     * Format a date as relative time (e.g., "3h ago", "2d ago")
     * with fallback to short date for older dates
     */
    function formatRelative(dateInput) {
        const date = dateInput instanceof Date ? dateInput : parseDate(dateInput);
        if (!date) return 'No date';

        const now = new Date();
        const diffMs = now - date;
        const diffSeconds = Math.floor(diffMs / 1000);
        const diffMinutes = Math.floor(diffSeconds / 60);
        const diffHours = Math.floor(diffMinutes / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffSeconds < 60) return 'just now';
        if (diffMinutes < 60) return `${diffMinutes}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;

        // For older dates, show the actual date
        return formatShortDate(date);
    }

    /**
     * Format a date for display, with relative for recent and date for older
     * Returns object with both relative and absolute for flexibility
     */
    function formatSmart(dateInput) {
        const date = dateInput instanceof Date ? dateInput : parseDate(dateInput);
        if (!date) return { relative: 'No date', absolute: 'No date' };

        return {
            relative: formatRelative(date),
            absolute: formatMediumDate(date),
            datetime: formatDateTime(date)
        };
    }

    // Public API
    return {
        getLocale,
        setLocale,
        clearLocale,
        parseDate,
        formatShortDate,
        formatMediumDate,
        formatLongDate,
        formatDateTime,
        formatRelative,
        formatSmart
    };
})();

// Make available globally
window.DateUtils = DateUtils;
