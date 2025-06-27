import requests
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def analyze_page_structure(url, name):
    """Deep analysis of page structure to find the right selectors"""
    print(f"\n{'='*60}")
    print(f"DEEP ANALYSIS: {name}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        print(f"Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"ERROR: Status code {response.status_code}")
            return
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Check page structure
        print(f"\nPAGE STRUCTURE:")
        print(f"- Title: {soup.title.string if soup.title else 'No title'}")
        
        # Find main content areas
        main_areas = []
        for selector in ['main', 'article', '.content', '.main-content', '#content', '.page-content', 'body']:
            elements = soup.select(selector)
            if elements:
                main_areas.append((selector, len(elements)))
        
        print(f"- Main content areas found:")
        for selector, count in main_areas:
            print(f"  {selector}: {count} elements")
        
        # Count all links by parent container
        all_links = soup.find_all('a')
        print(f"- Total links: {len(all_links)}")
        
        # Group links by their parent containers
        container_stats = {}
        for link in all_links:
            text = link.get_text(strip=True)
            if not text or len(text) < 5:
                continue
                
            # Find meaningful parent containers
            parent = link.parent
            parent_classes = []
            parent_ids = []
            
            # Walk up the tree to find containers with class/id
            current = parent
            for _ in range(5):  # Max 5 levels up
                if current and current.name:
                    if current.get('class'):
                        parent_classes.extend(current.get('class'))
                    if current.get('id'):
                        parent_ids.append(current.get('id'))
                    current = current.parent
                else:
                    break
            
            # Create a key for this container type
            key = f"Parent: {parent.name if parent else 'None'}"
            if parent_classes:
                key += f" .{' .'.join(set(parent_classes[:3]))}"
            if parent_ids:
                key += f" #{' #'.join(set(parent_ids))}"
            
            if key not in container_stats:
                container_stats[key] = []
            container_stats[key].append(text)
        
        print(f"\nLINKS BY CONTAINER:")
        for container, texts in sorted(container_stats.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
            print(f"- {container}: {len(texts)} links")
            # Show some examples
            for text in texts[:3]:
                if any(keyword in text.lower() for keyword in ['grant', 'funding', 'opportunity']):
                    print(f"  ★ {text[:60]}...")  # Star indicates potential grant link
                else:
                    print(f"    {text[:60]}...")
        
        # Look for grant-related content specifically
        print(f"\nGRANT-RELATED CONTENT ANALYSIS:")
        grant_keywords = ['grant', 'funding', 'opportunity', 'rfp', 'application', 'solicitation']
        page_text = soup.get_text().lower()
        
        for keyword in grant_keywords:
            count = page_text.count(keyword)
            if count > 0:
                print(f"- '{keyword}': {count} occurrences in page text")
        
        # Find links that contain grant keywords
        grant_links = []
        for link in all_links:
            text = link.get_text(strip=True)
            href = link.get('href', '')
            
            if any(keyword in text.lower() or keyword in href.lower() for keyword in grant_keywords):
                grant_links.append((text, href))
        
        print(f"\nGRANT-RELATED LINKS FOUND: {len(grant_links)}")
        for i, (text, href) in enumerate(grant_links[:10]):
            print(f"  {i+1}. {text[:80]}...")
            print(f"     URL: {href[:80]}...")
        
        if len(grant_links) == 0:
            print("  ⚠️  NO GRANT-RELATED LINKS FOUND!")
            print("  This suggests the page either:")
            print("    1. Uses AJAX/JavaScript to load content")
            print("    2. Links are in a different format than expected")
            print("    3. Page is just informational, real grants are elsewhere")
            
            # Look for form elements that might indicate grant applications
            forms = soup.find_all('form')
            if forms:
                print(f"  Found {len(forms)} forms on page - might have applications")
            
            # Look for external links that might lead to grant systems
            external_domains = set()
            for link in all_links:
                href = link.get('href', '')
                if href.startswith('http') and url not in href:
                    from urllib.parse import urlparse
                    domain = urlparse(href).netloc
                    external_domains.add(domain)
            
            if external_domains:
                print(f"  External domains linked: {list(external_domains)[:5]}")
        
    except Exception as e:
        print(f"ERROR analyzing {name}: {str(e)}")
        import traceback
        traceback.print_exc()

# Analyze key state websites
test_sites = [
    ('https://tea.texas.gov/finance-and-grants/grants', 'Texas DoE'),
    ('https://www.cde.ca.gov/fg/', 'California DoE Main Funding'),
    ('https://www.fldoe.org/finance/', 'Florida DoE Finance'),
]

for url, name in test_sites:
    analyze_page_structure(url, name)