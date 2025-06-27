#!/usr/bin/env python3
"""Test the fixed scraper to see if it now finds opportunities"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the fixed scrape function from app.py
from app import scrape_opportunities, STATE_CONFIGS
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_scraper():
    """Test the fixed scraper on a few states"""
    print("🔍 Testing FIXED scraper...")
    print("=" * 60)
    
    # Test states in order of expected success
    test_states = ['TX', 'FL']  # Skip CA for now due to captcha
    
    total_found = 0
    
    for state_code in test_states:
        config = STATE_CONFIGS.get(state_code, {})
        print(f"\n🏛️  Testing {config.get('name', state_code)} ({state_code})")
        print(f"URL: {config.get('url', 'Unknown')}")
        print(f"Status: {config.get('status', 'unknown')}")
        print("-" * 60)
        
        if config.get('status') == 'captcha_protected':
            print("⚠️  SKIPPING - Protected by captcha/anti-bot system")
            continue
        
        try:
            opportunities = scrape_opportunities(state_code)
            
            if opportunities:
                print(f"✅ SUCCESS! Found {len(opportunities)} opportunities:")
                for i, opp in enumerate(opportunities[:5], 1):  # Show first 5
                    print(f"  {i}. {opp['title'][:80]}...")
                    print(f"     💰 {opp['amount']} | 🏷️  {', '.join(opp['tags'])}")
                    print(f"     🔗 {opp['url'][:80]}...")
                    print()
                
                if len(opportunities) > 5:
                    print(f"     ... and {len(opportunities) - 5} more opportunities")
                
                total_found += len(opportunities)
            else:
                print("❌ No opportunities found")
                
        except Exception as e:
            print(f"💥 ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print(f"🎯 FINAL RESULTS: Found {total_found} total opportunities!")
    
    if total_found > 0:
        print("✅ SUCCESS! The scraper is now working!")
        print("🚀 Ready to deploy the fixed version.")
    else:
        print("❌ Still having issues. May need Firecrawl or other tools.")
        print("🔧 Consider using alternative scraping methods.")

if __name__ == "__main__":
    test_scraper()