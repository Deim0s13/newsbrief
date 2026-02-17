/**
 * Credibility badge rendering utilities for NewsBrief
 * Issue #197 - Display source credibility indicators in UI
 */

const CredibilityUtils = {
    // Cache for credibility lookups
    _cache: {},

    /**
     * Get color classes based on credibility score
     * @param {number|null} score - Credibility score 0.0-1.0
     * @returns {object} - Object with bg, text, and border classes
     */
    getScoreColors(score) {
        if (score === null || score === undefined) {
            return {
                bg: 'bg-gray-100 dark:bg-gray-700',
                text: 'text-gray-600 dark:text-gray-400',
                border: 'border-gray-300 dark:border-gray-600',
                dot: 'bg-gray-400'
            };
        }
        if (score >= 0.85) {
            return {
                bg: 'bg-green-100 dark:bg-green-900/30',
                text: 'text-green-700 dark:text-green-400',
                border: 'border-green-300 dark:border-green-700',
                dot: 'bg-green-500'
            };
        }
        if (score >= 0.70) {
            return {
                bg: 'bg-blue-100 dark:bg-blue-900/30',
                text: 'text-blue-700 dark:text-blue-400',
                border: 'border-blue-300 dark:border-blue-700',
                dot: 'bg-blue-500'
            };
        }
        if (score >= 0.50) {
            return {
                bg: 'bg-yellow-100 dark:bg-yellow-900/30',
                text: 'text-yellow-700 dark:text-yellow-400',
                border: 'border-yellow-300 dark:border-yellow-700',
                dot: 'bg-yellow-500'
            };
        }
        if (score >= 0.30) {
            return {
                bg: 'bg-orange-100 dark:bg-orange-900/30',
                text: 'text-orange-700 dark:text-orange-400',
                border: 'border-orange-300 dark:border-orange-700',
                dot: 'bg-orange-500'
            };
        }
        return {
            bg: 'bg-red-100 dark:bg-red-900/30',
            text: 'text-red-700 dark:text-red-400',
            border: 'border-red-300 dark:border-red-700',
            dot: 'bg-red-500'
        };
    },

    /**
     * Get human-readable label for credibility score
     * @param {number|null} score - Credibility score 0.0-1.0
     * @returns {string} - Label like "Very High", "High", etc.
     */
    getScoreLabel(score) {
        if (score === null || score === undefined) return 'Unknown';
        if (score >= 0.85) return 'Very High';
        if (score >= 0.70) return 'High';
        if (score >= 0.50) return 'Mostly Factual';
        if (score >= 0.30) return 'Mixed';
        return 'Low';
    },

    /**
     * Get bias position for visual scale (0-4)
     * @param {string|null} bias - Bias value
     * @returns {number} - Position 0=left, 2=center, 4=right
     */
    getBiasPosition(bias) {
        const positions = {
            'left': 0,
            'left_center': 1,
            'center': 2,
            'right_center': 3,
            'right': 4
        };
        return positions[bias] ?? 2; // Default to center if unknown
    },

    /**
     * Get human-readable bias label
     * @param {string|null} bias - Bias value
     * @returns {string} - Human-readable label
     */
    getBiasLabel(bias) {
        const labels = {
            'left': 'Left',
            'left_center': 'Left-Center',
            'center': 'Center',
            'right_center': 'Right-Center',
            'right': 'Right'
        };
        return labels[bias] || 'Unknown';
    },

    /**
     * Extract domain from URL
     * @param {string} url - Full URL
     * @returns {string} - Domain without protocol/path
     */
    extractDomain(url) {
        try {
            const parsed = new URL(url);
            let domain = parsed.hostname.toLowerCase();
            // Strip common prefixes
            domain = domain.replace(/^(www\.|m\.|mobile\.|amp\.|news\.)/, '');
            return domain;
        } catch {
            return url;
        }
    },

    /**
     * Fetch credibility data for domains (with caching)
     * @param {string[]} domains - Array of domains to look up
     * @returns {Promise<object>} - Map of domain -> credibility data
     */
    async fetchCredibility(domains) {
        // Filter out cached domains
        const uncached = domains.filter(d => !this._cache[d]);

        if (uncached.length > 0) {
            try {
                const response = await fetch(`/api/credibility/lookup?domains=${uncached.join(',')}`);
                if (response.ok) {
                    const data = await response.json();
                    // Merge into cache
                    Object.assign(this._cache, data);
                }
            } catch (error) {
                console.error('Failed to fetch credibility data:', error);
            }
        }

        // Return requested domains from cache
        const result = {};
        for (const d of domains) {
            if (this._cache[d]) {
                result[d] = this._cache[d];
            }
        }
        return result;
    },

    /**
     * Render a loading placeholder
     * @returns {string} - HTML string for loading state
     */
    renderLoading() {
        return `
            <span class="inline-flex items-center px-2 py-0.5 rounded text-xs text-gray-400 dark:text-gray-500">
                <svg class="animate-spin h-3 w-3 mr-1" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Loading...
            </span>
        `;
    },

    /**
     * Render a "not rated" placeholder for unknown sources
     * @returns {string} - HTML string for not rated state
     */
    renderNotRated() {
        return `
            <span class="inline-flex items-center px-2 py-0.5 rounded text-xs bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 cursor-help"
                  title="This source has not been rated by MBFC">
                <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                Not Rated
            </span>
        `;
    },

    /**
     * Render a compact credibility badge
     * @param {object} cred - Credibility data object
     * @returns {string} - HTML string for badge
     */
    renderBadge(cred) {
        if (!cred) {
            return this.renderNotRated();
        }

        const colors = this.getScoreColors(cred.credibility_score);
        const label = this.getScoreLabel(cred.credibility_score);
        const scorePercent = cred.credibility_score !== null
            ? Math.round(cred.credibility_score * 100)
            : '?';

        // Build tooltip content
        const tooltipParts = [];
        if (cred.name) tooltipParts.push(cred.name);
        if (cred.factual_reporting) tooltipParts.push(`Factual: ${cred.factual_reporting.replace('_', ' ')}`);
        if (cred.bias) tooltipParts.push(`Bias: ${this.getBiasLabel(cred.bias)}`);
        if (cred.source_type && cred.source_type !== 'news') {
            tooltipParts.push(`Type: ${cred.source_type.replace('_', ' ')}`);
        }
        const tooltip = tooltipParts.join(' | ');

        return `
            <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors.bg} ${colors.text} cursor-help"
                  title="${tooltip}"
                  ${cred.provider_url ? `onclick="window.open('${cred.provider_url}', '_blank')"` : ''}>
                <span class="w-1.5 h-1.5 rounded-full ${colors.dot} mr-1.5"></span>
                ${label}
            </span>
        `;
    },

    /**
     * Render a detailed credibility card with bias scale
     * @param {object} cred - Credibility data object
     * @returns {string} - HTML string for detailed card
     */
    renderDetailedBadge(cred) {
        if (!cred) {
            return '';
        }

        const colors = this.getScoreColors(cred.credibility_score);
        const label = this.getScoreLabel(cred.credibility_score);
        const biasPos = this.getBiasPosition(cred.bias);

        // Eligibility warning
        const eligibilityWarning = !cred.is_eligible_for_synthesis
            ? `<div class="mt-1 text-xs text-red-600 dark:text-red-400">
                 <svg class="inline w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                   <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                 </svg>
                 Not used in synthesis
               </div>`
            : '';

        return `
            <div class="inline-flex flex-col p-2 rounded-lg border ${colors.border} ${colors.bg}">
                <div class="flex items-center justify-between mb-1">
                    <span class="text-xs font-medium ${colors.text}">${label}</span>
                    ${cred.provider_url
                        ? `<a href="${cred.provider_url}" target="_blank" class="text-xs text-blue-600 hover:underline ml-2">MBFC</a>`
                        : ''}
                </div>

                <!-- Bias Scale -->
                ${cred.bias ? `
                <div class="flex items-center space-x-0.5 mt-1" title="Political Bias: ${this.getBiasLabel(cred.bias)}">
                    <span class="text-[10px] text-gray-500 dark:text-gray-400 w-4">L</span>
                    ${[0, 1, 2, 3, 4].map(i => `
                        <div class="w-3 h-2 rounded-sm ${i === biasPos ? 'bg-gray-800 dark:bg-gray-200' : 'bg-gray-300 dark:bg-gray-600'}"></div>
                    `).join('')}
                    <span class="text-[10px] text-gray-500 dark:text-gray-400 w-4 text-right">R</span>
                </div>
                ` : ''}

                ${eligibilityWarning}
            </div>
        `;
    },

    /**
     * Render a mini dot indicator
     * @param {object} cred - Credibility data object
     * @returns {string} - HTML string for mini indicator
     */
    renderDot(cred) {
        if (!cred) return '';

        const colors = this.getScoreColors(cred.credibility_score);
        const label = this.getScoreLabel(cred.credibility_score);

        return `
            <span class="inline-flex items-center cursor-help" title="Credibility: ${label}">
                <span class="w-2 h-2 rounded-full ${colors.dot}"></span>
            </span>
        `;
    }
};

// Export for module systems if available
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CredibilityUtils;
}
