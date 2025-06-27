#!/usr/bin/env python3
"""Standalone test of the fixed scraping logic"""

import requests
from bs4 import BeautifulSoup
import logging
from datetime import datetime
import hashlib
import re
from urllib.parse import urljoin

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Fixed configurations
STATE_CONFIGS = {
    'TX': {
        'name': 'Texas',
        'url': 'https://tea.texas.gov/finance-and-grants/grants',
        'selectors': ['.field--name-body a', '.sectional-box a', 'strong a', '.field--type-text-with-summary a'],
        'status': 'active'
    },
    'FL': {
        'name': 'Florida',
        'url': 'https://www.fldoe.org/finance/contracts-grants-procurement/grants-management/',
        'selectors': ['.sectional-box a', '.col a', 'main a'],
        'status': 'active'
    }
}

def extract_dollar_amount(text):
    """Extract dollar amount from text"""
    if not text:
        return None
    
    # Remove commas and convert K/M/B
    text = text.replace(',', '')
    multipliers = {'K': 1000, 'M': 1000000, 'B': 1000000000}
    
    # Try to find dollar amounts
    match = re.search(r'\$?([\d.]+)\s*([KMB])?', text, re.IGNORECASE)
    if match:
        amount = float(match.group(1))
        multiplier = match.group(2)
        if multiplier and multiplier.upper() in multipliers:
            amount *= multipliers[multiplier.upper()]
        return amount
    return None

def scrape_opportunities_standalone(state_code, config):
    """Standalone version of the fixed scraper"""
    opportunities = []
    
    if config.get('status') == 'captcha_protected':
        logger.warning(f"Skipping {config['name']} - requires Firecrawl or similar tool")
        return []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        
        logger.info(f"Scraping {config['name']} from {config['url']}")
        response = requests.get(config['url'], timeout=30, headers=headers, allow_redirects=True)
        
        if response.status_code == 404:
            logger.error(f"404 Error for {config['name']} - URL may be outdated")
            return []
        
        if response.status_code != 200:
            logger.error(f"HTTP {response.status_code} for {config['name']}")
            return []
        
        if 'captcha' in response.text.lower() or 'radware' in response.text.lower():
            logger.warning(f"Bot protection detected for {config['name']}")
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Try multiple selectors
        all_links = []
        selectors = config.get('selectors', ['a'])
        
        for selector in selectors:
            try:
                links = soup.select(selector)
                if links:
                    logger.info(f"Selector '{selector}' found {len(links)} links")
                    all_links.extend(links)
                    break  # Use first selector that works
            except Exception as e:
                logger.warning(f"Selector '{selector}' failed: {str(e)}")
                continue
        
        if not all_links:
            logger.warning(f"No links found for {config['name']}")
            return []
        
        # Remove duplicates
        seen_hrefs = set()
        unique_links = []
        for link in all_links:
            href = link.get('href', '')
            if href and href not in seen_hrefs:
                seen_hrefs.add(href)
                unique_links.append(link)
        
        logger.info(f"Found {len(unique_links)} unique links")
        
        # Broad keyword matching
        keywords = [
            'grant', 'grants', 'funding', 'opportunity', 'opportunities', 
            'rfp', 'solicitation', 'application', 'apply', 'award', 'awards',
            'competitive', 'program', 'programs', 'k-12', 'education', 
            'school', 'district', 'teacher', 'student', 'math', 'mathematics', 
            'stem', 'science', 'elementary', 'middle', 'high school', 'literacy',
            'professional development', 'curriculum', 'technology', 'digital'
        ]
        
        grant_related_links = []
        for link in unique_links[:50]:
            text = link.get_text(strip=True)
            href = link.get('href', '')
            
            if not text or len(text) < 5:
                continue
            
            text_lower = text.lower()
            href_lower = href.lower()
            
            if any(keyword in text_lower or keyword in href_lower for keyword in keywords):
                grant_related_links.append(link)
        
        logger.info(f"Found {len(grant_related_links)} grant-related links")
        
        # Process into opportunities
        for link in grant_related_links[:20]:
            text = link.get_text(strip=True)
            href = link.get('href', '')
            
            if href and not href.startswith('http'):
                href = urljoin(config['url'], href)
            
            if not href or href.startswith('#') or href.startswith('javascript:'):
                continue
            
            # Generate ID
            text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            opp_id = f"{state_code}_{text_hash}_{datetime.now().strftime('%Y%m%d')}"
            
            # Extract amount
            amount = extract_dollar_amount(text) or 'Amount TBD'
            if isinstance(amount, (int, float)):
                amount = f"${amount:,.0f}"
            
            # Assign tags
            tags = ['Education']
            text_lower = text.lower()
            if any(word in text_lower for word in ['k-12', 'elementary', 'middle', 'secondary', 'school']):
                tags.append('K-12')
            if any(word in text_lower for word in ['stem', 'math', 'science', 'technology']):
                tags.append('STEM')
            if any(word in text_lower for word in ['teacher', 'professional development', 'training']):
                tags.append('Professional Development')
            
            opportunities.append({
                'id': opp_id,
                'title': text[:200],
                'state': config['name'],
                'amount': amount,
                'deadline': 'Check website for deadline',
                'url': href,
                'tags': tags,
                'found_date': datetime.now().isoformat()
            })
            
            logger.info(f"Added: {text[:50]}...")
        
        logger.info(f"Successfully found {len(opportunities)} opportunities")
        
    except Exception as e:
        logger.error(f"Error scraping {config['name']}: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return opportunities

def main():
    """Test the standalone scraper"""
    print("🔍 Testing STANDALONE FIXED scraper...")
    print("=" * 60)
    
    total_found = 0
    
    for state_code, config in STATE_CONFIGS.items():
        print(f"\n🏛️  Testing {config['name']} ({state_code})")
        print(f"URL: {config['url']}")
        print("-" * 60)
        
        opportunities = scrape_opportunities_standalone(state_code, config)
        
        if opportunities:
            print(f"✅ SUCCESS! Found {len(opportunities)} opportunities:")
            for i, opp in enumerate(opportunities[:5], 1):
                print(f"  {i}. {opp['title'][:80]}...")
                print(f"     💰 {opp['amount']} | 🏷️  {', '.join(opp['tags'])}")
                print(f"     🔗 {opp['url'][:80]}...")
                print()
            
            if len(opportunities) > 5:
                print(f"     ... and {len(opportunities) - 5} more")
            
            total_found += len(opportunities)
        else:
            print("❌ No opportunities found")
    
    print("\n" + "=" * 60)
    print(f"🎯 FINAL RESULTS: Found {total_found} total opportunities!")
    
    if total_found > 0:
        print("✅ SUCCESS! The fixed scraper is working!")
    else:
        print("❌ Still having issues - may need advanced tools.")

if __name__ == "__main__":
    main()