// Global variables for pagination and filtering
let currentOffset = 0;
let currentState = 'ALL';
let isLoading = false;
let hasMore = true;

// Handle page initialization
document.addEventListener('DOMContentLoaded', function() {
    const allStatesCheckbox = document.getElementById('all');
    const stateCheckboxes = document.querySelectorAll('input[name="states"]:not(#all)');
    
    if (allStatesCheckbox) {
        allStatesCheckbox.addEventListener('change', function() {
            stateCheckboxes.forEach(cb => cb.checked = this.checked);
        });
    }

    // Handle individual state checkboxes
    stateCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const allChecked = document.querySelectorAll('input[name="states"]:not(#all):checked').length === 
                             stateCheckboxes.length;
            if (allStatesCheckbox) {
                allStatesCheckbox.checked = allChecked;
            }
        });
    });

    // Handle form submission
    const alertForm = document.getElementById('alertForm');
    if (alertForm) {
        alertForm.addEventListener('submit', handleFormSubmission);
    }

    // Initialize opportunities and state filter
    loadStates();
    loadOpportunities(true);
});

async function handleFormSubmission(e) {
    e.preventDefault();
    
    const submitBtn = document.querySelector('.submit-btn');
    const successMessage = document.getElementById('successMessage');
    const errorMessage = document.getElementById('errorMessage') || createErrorMessage();
    
    // Reset messages
    successMessage.style.display = 'none';
    errorMessage.style.display = 'none';
    
    // Show loading state
    const originalText = submitBtn.textContent;
    submitBtn.textContent = 'Subscribing...';
    submitBtn.disabled = true;
    
    try {
        const email = document.getElementById('email').value;
        const frequency = document.querySelector('input[name="frequency"]:checked').value;
        const states = Array.from(document.querySelectorAll('input[name="states"]:checked'))
                            .map(cb => cb.value)
                            .filter(val => val !== 'all');
        
        if (states.length === 0) {
            throw new Error('Please select at least one state to monitor');
        }
        
        const formData = {
            email: email,
            frequency: frequency,
            states: states,
            timestamp: new Date().toISOString(),
            source: 'funding-monitor-app'
        };
        
        const response = await fetch('/subscribe', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify(formData)
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            // Show success message
            successMessage.style.display = 'block';
            successMessage.scrollIntoView({ behavior: 'smooth' });
            
            // Reset form after success
            setTimeout(() => {
                document.getElementById('alertForm').reset();
                // Re-check default states
                document.getElementById('TX').checked = true;
                document.getElementById('CA').checked = true;
                document.getElementById('FL').checked = true;
                document.getElementById('daily').checked = true;
            }, 1000);
        } else {
            throw new Error(data.message || 'Subscription failed. Please try again.');
        }
        
    } catch (error) {
        console.error('Subscription error:', error);
        errorMessage.textContent = error.message;
        errorMessage.style.display = 'block';
        errorMessage.scrollIntoView({ behavior: 'smooth' });
    } finally {
        // Reset button state
        submitBtn.textContent = originalText;
        submitBtn.disabled = false;
    }
}

function createErrorMessage() {
    const errorDiv = document.createElement('div');
    errorDiv.id = 'errorMessage';
    errorDiv.className = 'error-message';
    
    const successMessage = document.getElementById('successMessage');
    successMessage.parentNode.insertBefore(errorDiv, successMessage.nextSibling);
    
    return errorDiv;
}

// Simulate real-time updates (refresh stats periodically)
async function updateStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        
        if (data.success) {
            updateStatCards(data.stats);
        }
    } catch (error) {
        console.error('Error updating stats:', error);
    }
}

function updateStatCards(stats) {
    const statCards = document.querySelectorAll('.stat-number');
    if (statCards.length >= 3) {
        statCards[0].textContent = stats.total_funding || '$47M+';
        statCards[1].textContent = stats.total_opportunities || '23';
        statCards[2].textContent = stats.states_monitored || '12';
    }
}

// Update stats every 5 minutes
setInterval(updateStats, 300000);

// Load available states for filter dropdown
async function loadStates() {
    try {
        const response = await fetch('/api/states');
        const data = await response.json();
        
        if (data.success) {
            const stateFilter = document.getElementById('stateFilter');
            stateFilter.innerHTML = '';
            
            data.states.forEach(state => {
                const option = document.createElement('option');
                option.value = state.code;
                option.textContent = `${state.name} (${state.count})`;
                stateFilter.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading states:', error);
    }
}

// Load opportunities with filtering and pagination
async function loadOpportunities(reset = false) {
    if (isLoading) return;
    isLoading = true;
    
    try {
        if (reset) {
            currentOffset = 0;
            document.getElementById('opportunitiesContainer').innerHTML = '';
            document.getElementById('noOpportunitiesMessage')?.remove();
        }
        
        document.getElementById('loadingIndicator').style.display = 'block';
        
        const url = new URL('/api/opportunities', window.location.origin);
        url.searchParams.set('offset', currentOffset);
        url.searchParams.set('limit', 10);
        if (currentState && currentState !== 'ALL') {
            url.searchParams.set('state', currentState);
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.success) {
            const container = document.getElementById('opportunitiesContainer');
            
            if (data.opportunities.length === 0 && currentOffset === 0) {
                container.innerHTML = `
                    <div id="noOpportunitiesMessage" style="text-align: center; margin: 20px 0;">
                        <p style="color: #666;">No opportunities found for the selected filter. New opportunities are automatically scanned every Tuesday & Friday.</p>
                    </div>
                `;
            } else {
                data.opportunities.forEach(opp => {
                    container.appendChild(createOpportunityCard(opp));
                });
            }
            
            hasMore = data.has_more;
            currentOffset += data.count;
            
            // Update count badge
            document.getElementById('opportunityCount').textContent = 
                `${data.total_count} total`;
            
            // Show/hide load more button
            const loadMoreContainer = document.getElementById('loadMoreContainer');
            loadMoreContainer.style.display = hasMore ? 'block' : 'none';
        }
    } catch (error) {
        console.error('Error loading opportunities:', error);
    } finally {
        isLoading = false;
        document.getElementById('loadingIndicator').style.display = 'none';
    }
}

// Create opportunity card HTML element
function createOpportunityCard(opp) {
    const card = document.createElement('a');
    card.href = opp.url;
    card.target = '_blank';
    card.className = 'opportunity-card';
    
    const tagsHtml = opp.tags.map(tag => `<span class="tag">${tag}</span>`).join('');
    
    card.innerHTML = `
        <div class="opportunity-header">
            <div>
                <div class="opportunity-title">${opp.title}</div>
                <div class="opportunity-meta">
                    <span>📍 ${opp.state}</span>
                    <span>📅 Found ${opp.found_date}</span>
                    <span>⏰ Deadline: ${opp.deadline}</span>
                </div>
            </div>
            <div class="opportunity-amount">${opp.amount}</div>
        </div>
        <div>${tagsHtml}</div>
        <div class="link-indicator">Click to view full details →</div>
    `;
    
    return card;
}

// Handle state filter change
function filterByState() {
    const stateFilter = document.getElementById('stateFilter');
    currentState = stateFilter.value;
    loadOpportunities(true);
}

// Load more opportunities button
function loadMoreOpportunities() {
    loadOpportunities(false);
}

// Manual scrape function
async function triggerScrape() {
    const button = event.target;
    const originalText = button.textContent;
    
    try {
        button.textContent = '⏳ Scanning state websites...';
        button.disabled = true;
        
        const response = await fetch('/api/scrape', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(`Scan complete! Found ${data.opportunities_found} new opportunities.`);
            // Reload opportunities and states
            loadStates();
            loadOpportunities(true);
        } else {
            alert('Error scanning websites. Please try again.');
        }
    } catch (error) {
        console.error('Scrape error:', error);
        alert('Error scanning websites. Please try again.');
    } finally {
        button.textContent = originalText;
        button.disabled = false;
    }
}