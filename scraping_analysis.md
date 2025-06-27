# Funding Monitor Scraping Issues Analysis

## Key Problems Identified

### 1. **Incorrect CSS Selectors**
- Texas (TX): Uses `.page-content a` but the page doesn't have this class
- California (CA): Hit by a Radware Captcha page - anti-bot protection
- Florida (FL): The URL returns a 404 error - page doesn't exist

### 2. **Anti-Bot Protection**
- California's site uses Radware protection that blocks automated requests
- Need more sophisticated headers or tools like Firecrawl to bypass

### 3. **Outdated URLs**
- Florida's grants page has moved or been removed (404 error)
- Need to update URLs for several states

### 4. **Selector Issues**
- The selectors are too specific and don't match the actual HTML structure
- Need to use more generic selectors or analyze the actual page structure

## Immediate Fixes Needed

### 1. Update State Configurations
```python
STATE_CONFIGS = {
    'TX': {
        'name': 'Texas',
        'url': 'https://tea.texas.gov/finance-and-grants/grants',
        'selector': 'main a, article a, .content a, #content a'  # More generic
    },
    'CA': {
        'name': 'California', 
        'url': 'https://www.cde.ca.gov/fg/fo/',
        'selector': 'a',  # Generic, but needs captcha bypass
        'needs_advanced_scraping': True
    },
    'FL': {
        'name': 'Florida',
        'url': 'https://www.fldoe.org/finance/',  # Updated URL
        'selector': 'main a, .main-content a'
    }
}
```

### 2. Improve Scraping Logic
- Add better error handling for 404s, captchas
- Use more sophisticated headers
- Implement retry logic
- Consider using Firecrawl or similar tools for difficult sites

### 3. Better Link Filtering
- Current keyword matching is too restrictive
- Many grant opportunities might not contain "math" or "stem" directly
- Need to look for broader terms like "grant", "funding", "RFP", "application"

## Recommended Solutions

### Short-term (Quick Fixes):
1. Update all state URLs to verify they're still valid
2. Use more generic selectors
3. Improve keyword matching logic
4. Add better error handling and logging

### Long-term (Robust Solution):
1. Integrate Firecrawl API for better scraping
2. Use AI to analyze page content and identify grant opportunities
3. Implement a more sophisticated link following strategy
4. Add manual review/curation process for found opportunities