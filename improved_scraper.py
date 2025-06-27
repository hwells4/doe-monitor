import requests
from bs4 import BeautifulSoup
import logging
import re
from urllib.parse import urljoin, urlparse
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Updated state configurations with better URLs and selectors
IMPROVED_STATE_CONFIGS = {
    'TX': {
        'name': 'Texas',
        'url': 'https://tea.texas.gov/finance-and-grants/grants',
        'selectors': ['main a', 'article a', '.content a', '#content a', 'div.field-item a'],
        'keywords': ['grant', 'funding', 'opportunity', 'application', 'rfp', 'solicitation']
    },
    'CA': {
        'name': 'California',
        'url': 'https://www.cde.ca.gov/fg/fo/profile.asp?id=5578',  # Direct grants page
        'selectors': ['table a', 'main a', '.content a'],
        'keywords': ['grant', 'funding', 'opportunity', 'application'],
        'needs_advanced_scraping': True
    },
    'FL': {
        'name': 'Florida',
        'url': 'https://www.fldoe.org/finance/',  # Updated URL
        'selectors': ['main a', '.main-content a', 'article a', '.page-content a'],
        'keywords': ['grant', 'funding', 'competitive', 'application']
    },
    'NY': {
        'name': 'New York',
        'url': 'https://www.nysed.gov/grant-opportunities',  # Updated URL
        'selectors': ['main a', '.content a', 'article a'],
        'keywords': ['grant', 'funding', 'rfp', 'application']
    }
}

def get_robust_headers():
    """Return headers that look like a real browser"""
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0'
    }

def is_grant_related(text, href=''):
    """Check if a link is likely grant-related based on text and URL"""
    if not text:
        return False
    
    text_lower = text.lower()
    href_lower = href.lower() if href else ''
    
    # Strong indicators
    strong_keywords = ['grant', 'funding', 'rfp', 'solicitation', 'application', 'opportunity']
    if any(keyword in text_lower or keyword in href_lower for keyword in strong_keywords):
        return True
    
    # Check for specific patterns
    patterns = [
        r'request for proposal',
        r'competitive grant',
        r'funding opportunity',
        r'grant program',
        r'apply for',
        r'application deadline',
        r'award amount'
    ]
    
    for pattern in patterns:
        if re.search(pattern, text_lower) or re.search(pattern, href_lower):
            return True
    
    return False

def extract_grant_details(text, soup=None):
    """Try to extract grant details from link text or surrounding context"""
    details = {
        'amount': 'Amount TBD',
        'deadline': 'See website for details',
        'tags': []
    }
    
    # Try to extract amount
    amount_patterns = [
        r'\$[\d,]+(?:\.\d{2})?(?:\s*(?:million|M|billion|B|thousand|K))?',
        r'[\d,]+(?:\.\d{2})?\s*(?:million|M|billion|B|thousand|K)\s*(?:dollars?|USD)?',
        r'up to \$[\d,]+',
        r'total of \$[\d,]+'
    ]
    
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            details['amount'] = match.group(0)
            break
    
    # Try to extract deadline
    deadline_patterns = [
        r'(?:deadline|due|submit by|closes?):?\s*(\w+\s+\d{1,2},?\s+\d{4})',
        r'(?:deadline|due|submit by|closes?):?\s*(\d{1,2}/\d{1,2}/\d{2,4})',
        r'applications? (?:due|close|deadline):?\s*(\w+\s+\d{1,2})'
    ]
    
    for pattern in deadline_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            details['deadline'] = match.group(1)
            break
    
    # Extract tags based on content
    if 'k-12' in text.lower() or 'elementary' in text.lower() or 'secondary' in text.lower():
        details['tags'].append('K-12')
    if 'stem' in text.lower() or 'science' in text.lower() or 'math' in text.lower():
        details['tags'].append('STEM')
    if 'professional development' in text.lower() or 'teacher' in text.lower():
        details['tags'].append('Professional Development')
    if 'technology' in text.lower() or 'digital' in text.lower():
        details['tags'].append('Technology')
    
    if not details['tags']:
        details['tags'] = ['Education', 'Grant']
    
    return details

def scrape_opportunities_improved(state_code, config=None):
    """Improved scraping function with better error handling and link detection"""
    if not config:
        config = IMPROVED_STATE_CONFIGS.get(state_code)
    
    if not config:
        logger.error(f"No configuration found for state: {state_code}")
        return []
    
    opportunities = []
    
    try:
        # Make request with robust headers
        session = requests.Session()
        session.headers.update(get_robust_headers())
        
        logger.info(f"Scraping {config['name']} from {config['url']}")
        response = session.get(config['url'], timeout=30, allow_redirects=True)
        
        # Check for common issues
        if response.status_code == 404:
            logger.error(f"404 Error for {config['name']} - URL may be outdated: {config['url']}")
            return []
        
        if response.status_code != 200:
            logger.error(f"HTTP {response.status_code} for {config['name']}")
            return []
        
        # Check for captcha or bot protection
        if 'captcha' in response.text.lower() or 'radware' in response.text.lower():
            logger.warning(f"Captcha/Bot protection detected for {config['name']}")
            if config.get('needs_advanced_scraping'):
                logger.info(f"Site {config['name']} requires advanced scraping tools like Firecrawl")
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Try multiple selectors
        all_links = []
        for selector in config.get('selectors', ['a']):
            links = soup.select(selector)
            all_links.extend(links)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_links = []
        for link in all_links:
            href = link.get('href', '')
            if href and href not in seen:
                seen.add(href)
                unique_links.append(link)
        
        logger.info(f"Found {len(unique_links)} unique links for {config['name']}")
        
        # Filter for grant-related links
        grant_links = []
        for link in unique_links:
            text = link.get_text(strip=True)
            href = link.get('href', '')
            
            if is_grant_related(text, href):
                grant_links.append(link)
        
        logger.info(f"Found {len(grant_links)} grant-related links for {config['name']}")
        
        # Process grant links
        for link in grant_links[:20]:  # Limit to 20 per state
            text = link.get_text(strip=True)
            href = link.get('href', '')
            
            # Make absolute URL
            if href and not href.startswith('http'):
                href = urljoin(config['url'], href)
            
            # Skip if it's just an anchor or javascript
            if href.startswith('#') or href.startswith('javascript:'):
                continue
            
            # Extract grant details
            details = extract_grant_details(text)
            
            # Generate unique ID
            from datetime import datetime
            import hashlib
            text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            opp_id = f"{state_code}_{text_hash}_{datetime.now().strftime('%Y%m%d')}"
            
            opportunity = {
                'id': opp_id,
                'title': text[:200],  # Limit title length
                'state': config['name'],
                'amount': details['amount'],
                'deadline': details['deadline'],
                'url': href,
                'tags': details['tags'],
                'found_date': datetime.now().isoformat(),
                'source': 'web_scraping'
            }
            
            opportunities.append(opportunity)
            logger.info(f"Found opportunity: {text[:50]}...")
        
        # If no opportunities found with links, try to find text mentions
        if not opportunities:
            page_text = soup.get_text()
            for keyword in config.get('keywords', []):
                if keyword in page_text.lower():
                    logger.info(f"Keyword '{keyword}' found in page text but no grant links detected")
                    # Could implement more sophisticated text extraction here
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error for {config['name']}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error for {config['name']}: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return opportunities

# Test the improved scraper
if __name__ == "__main__":
    print("Testing improved scraper...\n")
    
    for state_code, config in IMPROVED_STATE_CONFIGS.items():
        print(f"\n{'='*60}")
        print(f"Testing {state_code} - {config['name']}")
        print(f"{'='*60}")
        
        opportunities = scrape_opportunities_improved(state_code, config)
        
        print(f"\nFound {len(opportunities)} opportunities")
        for i, opp in enumerate(opportunities[:5]):  # Show first 5
            print(f"\n{i+1}. {opp['title'][:80]}...")
            print(f"   Amount: {opp['amount']}")
            print(f"   URL: {opp['url'][:60]}...")
            print(f"   Tags: {', '.join(opp['tags'])}")
        
        # Small delay between states to be respectful
        time.sleep(1)