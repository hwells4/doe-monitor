import requests
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test configurations
STATE_CONFIGS = {
    'TX': {
        'name': 'Texas',
        'url': 'https://tea.texas.gov/finance-and-grants/grants',
        'selector': '.page-content a'
    },
    'CA': {
        'name': 'California', 
        'url': 'https://www.cde.ca.gov/fg/fo/',
        'selector': 'table a'
    },
    'FL': {
        'name': 'Florida',
        'url': 'https://www.fldoe.org/finance/grants/',
        'selector': '.content a'
    }
}

def test_scrape_state(state_code):
    """Test scraping a single state"""
    config = STATE_CONFIGS[state_code]
    print(f"\n{'='*50}")
    print(f"Testing {config['name']} ({state_code})")
    print(f"URL: {config['url']}")
    print(f"Selector: {config['selector']}")
    print(f"{'='*50}")
    
    try:
        # Make request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(config['url'], timeout=30, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Content Length: {len(response.content)}")
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # First, let's see what we have
        print(f"\nPage Title: {soup.title.string if soup.title else 'No title'}")
        
        # Try the configured selector
        links = soup.select(config['selector'])
        print(f"\nLinks found with selector '{config['selector']}': {len(links)}")
        
        if len(links) == 0:
            # Try some alternative selectors
            alternative_selectors = [
                'a',  # All links
                '.content a',
                '.main-content a',
                'main a',
                '#content a',
                '.page-content a',
                'article a',
                '.entry-content a',
                'div a'
            ]
            
            for alt_selector in alternative_selectors:
                alt_links = soup.select(alt_selector)
                if len(alt_links) > 0:
                    print(f"Alternative selector '{alt_selector}' found: {len(alt_links)} links")
                    # Show first 5 links
                    for i, link in enumerate(alt_links[:5]):
                        text = link.get_text(strip=True)
                        href = link.get('href', '')
                        if text and len(text) > 5:  # Skip empty or very short links
                            print(f"  {i+1}. {text[:80]}... - {href[:50]}...")
                    break
        else:
            # Show first 10 links found
            print("\nFirst 10 links found:")
            for i, link in enumerate(links[:10]):
                text = link.get_text(strip=True)
                href = link.get('href', '')
                print(f"  {i+1}. {text[:80]}... - {href[:50]}...")
        
        # Look for keywords in all text
        page_text = soup.get_text().lower()
        keywords = ['grant', 'funding', 'opportunity', 'application', 'rfp', 'math', 'stem', 'k-12']
        print(f"\nKeyword presence in page:")
        for keyword in keywords:
            count = page_text.count(keyword)
            if count > 0:
                print(f"  '{keyword}': {count} occurrences")
                
    except requests.exceptions.RequestException as e:
        print(f"Request Error: {str(e)}")
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

# Test each state
for state in ['TX', 'CA', 'FL']:
    test_scrape_state(state)