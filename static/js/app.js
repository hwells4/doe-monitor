// Handle "All States" checkbox
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