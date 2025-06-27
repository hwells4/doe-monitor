#!/usr/bin/env python3
"""
Test script to verify URL parsing fixes work correctly
"""

import re

def clean_extracted_url(url):
    """Clean and validate extracted URLs"""
    if not url:
        return ''
    
    # Remove common trailing artifacts step by step
    url = url.strip()
    
    # Remove markdown link artifacts like [1], [2] etc.
    url = re.sub(r'\[\d+\]\.?$', '', url)
    
    # Remove trailing punctuation and brackets
    url = re.sub(r'[\)\]\}\.,:;!?]+$', '', url)
    
    # Remove any remaining trailing whitespace
    url = url.strip()
    
    # Validate URL format
    if url and url.startswith('http') and len(url) > 10:
        # Basic URL validation - must have a domain with TLD
        if re.match(r'https?://[^\s<>"]+\.[a-zA-Z]{2,}', url):
            return url
    
    return ''

def extract_urls_from_text(text):
    """Extract and clean URLs from text with improved patterns"""
    urls = set()  # Use set to avoid duplicates
    
    # Multiple URL extraction patterns in order of preference
    url_patterns = [
        # Markdown links [text](url) - highest priority
        (r'\[([^\]]+)\]\((https?://[^\)\s]+)\)', 2),
        # URLs after common prefixes
        (r'(?:URL|Link|Website|Source):\s*(https?://[^\s<>"\]\)]+)', 1),
        # URLs in parentheses (but not markdown links)
        (r'(?<!\])\((https?://[^\)\s]+)\)', 1),
        # Standard URLs in text
        (r'(?:^|\s)(https?://[^\s<>"\]\)]+)', 1),
    ]
    
    for pattern, group_index in url_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                # Take the URL part from tuple matches
                url = match[group_index - 1] if len(match) >= group_index else match[0]
            else:
                url = match
            
            clean_url = clean_extracted_url(url)
            if clean_url:
                urls.add(clean_url)
    
    return list(urls)

# Test cases with problematic URLs that were reported
test_cases = [
    "https://tealprod.tea.state.tx.us/GrantOpportunities/forms/GrantProgramSearch.aspx)[1].",
    "Visit (https://www.fldoe.org/grants) for more info.",
    "URL: https://example.com/grants[2]",
    "Check out [Texas Grants](https://tea.texas.gov/grants) for details.",
    "Source: https://www.cde.ca.gov/fg/fo/)",
]

print("Testing URL cleaning function:")
print("=" * 50)

for i, test_url in enumerate(test_cases, 1):
    print(f"Test {i}: {test_url}")
    cleaned = clean_extracted_url(test_url)
    print(f"Cleaned: {cleaned}")
    print(f"Valid: {'✓' if cleaned else '✗'}")
    print()

# Test full text extraction
test_text = """
For current K-12 education funding opportunities, grants, and RFPs available in Texas for 2025, here are some key programs:

1. **Texas Education Agency Grants** - Visit https://tea.texas.gov/finance-and-grants/grants for comprehensive information.

2. **STEM Education Funding** - Check (https://tealprod.tea.state.tx.us/GrantOpportunities/forms/GrantProgramSearch.aspx)[1] for current opportunities.

3. **Mathematics Initiative** - URL: https://www.texasgateway.org/grants[2].

4. For more information, see [Texas Grant Portal](https://www.comptroller.texas.gov/economy/fiscal-notes/grants/).
"""

print("Testing full text URL extraction:")
print("=" * 50)
print(f"Input text: {test_text[:200]}...")
print()

extracted_urls = extract_urls_from_text(test_text)
print(f"Extracted {len(extracted_urls)} URLs:")
for i, url in enumerate(extracted_urls, 1):
    print(f"{i}. {url}")
    
print("\nAll URLs are valid:", all(url.startswith('http') and '.' in url for url in extracted_urls))