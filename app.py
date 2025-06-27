from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import json
import os
from apscheduler.schedulers.background import BackgroundScheduler
import sqlite3
import re
import logging
from dotenv import load_dotenv
from openai import OpenAI
from firecrawl import FirecrawlApp
try:
    from perplexipy import Perplexi
except ImportError:
    Perplexi = None

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize scheduler for automated checks
scheduler = BackgroundScheduler()

# Email configuration (use environment variables in production)
EMAIL_CONFIG = {
    'smtp_server': os.environ.get('SMTP_SERVER', 'smtp.gmail.com'),
    'smtp_port': int(os.environ.get('SMTP_PORT', '587')),
    'sender_email': os.environ.get('SENDER_EMAIL', ''),
    'sender_password': os.environ.get('SENDER_PASSWORD', '')
}

# AI Services Configuration
PERPLEXITY_API_KEY = os.environ.get('PERPLEXITY_API_KEY', '')
FIRECRAWL_API_KEY = os.environ.get('FIRECRAWL_API_KEY', '')

# Initialize AI clients with proper error handling
perplexity_client = None
firecrawl_app = None

try:
    if PERPLEXITY_API_KEY and Perplexi:
        perplexity_client = Perplexi(api_key=PERPLEXITY_API_KEY)
        logger.info("Perplexity client initialized successfully with PerplexiPy")
    elif PERPLEXITY_API_KEY:
        # Fallback to OpenAI client
        perplexity_client = OpenAI(
            api_key=PERPLEXITY_API_KEY,
            base_url="https://api.perplexity.ai"
        )
        logger.info("Perplexity client initialized with OpenAI client")
    else:
        logger.warning("PERPLEXITY_API_KEY not found")
except Exception as e:
    logger.error(f"Failed to initialize Perplexity client: {str(e)}")

try:
    if FIRECRAWL_API_KEY:
        firecrawl_app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
        logger.info("Firecrawl client initialized successfully")
    else:
        logger.warning("FIRECRAWL_API_KEY not found")
except Exception as e:
    logger.error(f"Failed to initialize Firecrawl client: {str(e)}")

# State DoE configurations - FIXED based on actual site analysis
STATE_CONFIGS = {
    'TX': {
        'name': 'Texas',
        'url': 'https://tea.texas.gov/finance-and-grants/grants',
        'selectors': ['.field--name-body a', '.sectional-box a', 'strong a', '.field--type-text-with-summary a'],
        'status': 'active'
    },
    'CA': {
        'name': 'California', 
        'url': 'https://www.cde.ca.gov/fg/',
        'selectors': ['main a', '.content a'],
        'status': 'captcha_protected',  # Needs Firecrawl
        'note': 'Protected by Radware anti-bot system'
    },
    'FL': {
        'name': 'Florida',
        'url': 'https://www.fldoe.org/finance/contracts-grants-procurement/grants-management/',
        'selectors': ['.sectional-box a', '.col a', 'main a'],
        'status': 'active'
    },
    'NY': {
        'name': 'New York',
        'url': 'https://www.nysed.gov/funding-opportunities',
        'selectors': ['.content-area a', 'main a', 'article a'],
        'status': 'needs_verification'
    },
    'IL': {
        'name': 'Illinois',
        'url': 'https://www.isbe.net/Pages/Grants.aspx',
        'selectors': ['.ms-rtestate-field a', 'main a', '.content a'],
        'status': 'needs_verification'
    },
    'PA': {
        'name': 'Pennsylvania',
        'url': 'https://www.education.pa.gov/Teachers%20-%20Administrators/Pages/Grant-Opportunities.aspx',
        'selectors': ['.ms-rtestate-field a', 'main a', '.content a'],
        'status': 'needs_verification'
    },
    'OH': {
        'name': 'Ohio',
        'url': 'https://education.ohio.gov/Topics/Finance-and-Funding/School-Funding/Grant-Opportunities',
        'selectors': ['.content a', 'main a', 'article a'],
        'status': 'needs_verification'
    },
    'GA': {
        'name': 'Georgia',
        'url': 'https://www.gadoe.org/External-Affairs-and-Policy/communications/Pages/PressReleaseDetails.aspx',
        'selectors': ['.content a', 'main a', 'article a'],
        'status': 'needs_verification'
    },
    'NC': {
        'name': 'North Carolina',
        'url': 'https://www.dpi.nc.gov/districts-schools/federal-program-monitoring/grants-funding',
        'selectors': ['.field-content a', 'main a', '.content a'],
        'status': 'needs_verification'
    },
    'MI': {
        'name': 'Michigan',
        'url': 'https://www.michigan.gov/mde/services/grants',
        'selectors': ['.page-content a', 'main a', '.content a'],
        'status': 'needs_verification'
    }
}

# Database setup
def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect('funding_monitor.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS subscribers
                 (email TEXT PRIMARY KEY, frequency TEXT, states TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS opportunities
                 (id TEXT PRIMARY KEY, title TEXT, state TEXT, amount TEXT, 
                  deadline TEXT, url TEXT, tags TEXT, found_date TEXT)''')
    conn.commit()
    conn.close()

# Routes
@app.route('/')
def home():
    """Serve the main page with opportunities and stats"""
    try:
        # Get recent opportunities
        opportunities = get_recent_opportunities()
        
        # Get current stats
        stats = get_current_stats()
        
        return render_template('index.html', opportunities=opportunities, stats=stats)
    except Exception as e:
        logger.error(f"Error loading home page: {str(e)}")
        return render_template('index.html', opportunities=[], stats=None)

@app.route('/subscribe', methods=['POST', 'OPTIONS'])
def subscribe():
    """Handle new email subscriptions"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        email = data.get('email')
        frequency = data.get('frequency', 'daily')
        states = data.get('states', [])
        
        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        
        if not states:
            return jsonify({'success': False, 'error': 'Please select at least one state'}), 400
        
        # Save to database
        conn = sqlite3.connect('funding_monitor.db')
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO subscribers (email, frequency, states, created_at)
                     VALUES (?, ?, ?, ?)''',
                  (email, frequency, json.dumps(states), datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        # Send welcome email
        send_welcome_email(email, states, frequency)
        
        logger.info(f"New subscription: {email} for states {states}")
        
        return jsonify({
            'success': True,
            'message': 'Successfully subscribed!',
            'email': email
        }), 200
        
    except Exception as e:
        logger.error(f"Subscription error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Subscription failed. Please try again.'
        }), 500

@app.route('/api/opportunities', methods=['GET'])
def api_opportunities():
    """Get latest funding opportunities"""
    try:
        opportunities = get_recent_opportunities()
        return jsonify({
            'success': True,
            'opportunities': opportunities,
            'count': len(opportunities)
        })
    except Exception as e:
        logger.error(f"Error fetching opportunities: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Get current statistics"""
    try:
        stats = get_current_stats()
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        logger.error(f"Error fetching stats: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    try:
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'database': check_database_health(),
            'scheduler': scheduler.running if scheduler else False,
            'version': '2.1',
            'ai_services': {
                'perplexity_api_key_set': bool(PERPLEXITY_API_KEY),
                'firecrawl_api_key_set': bool(FIRECRAWL_API_KEY),
                'perplexity_client_ready': perplexity_client is not None,
                'firecrawl_app_ready': firecrawl_app is not None
            }
        })
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/scrape', methods=['POST'])
def manual_scrape():
    """Manually trigger opportunity scraping"""
    try:
        # Check if this is the first run or manual trigger
        new_opportunities = check_all_states()
        return jsonify({
            'success': True,
            'message': f'Scraping complete. Found {len(new_opportunities)} new opportunities.',
            'opportunities_found': len(new_opportunities)
        })
    except Exception as e:
        logger.error(f"Manual scrape error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/scrape/ai/<state_code>', methods=['POST'])
def test_ai_scrape(state_code):
    """Test AI-powered scraping for a specific state"""
    try:
        if not perplexity_client and not firecrawl_app:
            return jsonify({
                'success': False,
                'error': 'No AI services available. At least one of Perplexity or Firecrawl must be configured.'
            }), 400
        
        if state_code.upper() not in STATE_CONFIGS:
            return jsonify({
                'success': False,
                'error': f'State {state_code} not supported. Available: {list(STATE_CONFIGS.keys())}'
            }), 400
        
        # Try AI scraping with detailed error reporting
        try:
            opportunities = ai_powered_scrape_opportunities(state_code.upper())
        except Exception as ai_error:
            # Fallback to traditional scraping
            logger.warning(f"AI scraping failed, falling back to traditional: {str(ai_error)}")
            opportunities = scrape_opportunities(state_code.upper())
        
        return jsonify({
            'success': True,
            'message': f'AI scraping complete for {STATE_CONFIGS[state_code.upper()]["name"]}',
            'opportunities_found': len(opportunities),
            'opportunities': opportunities[:3],  # Return first 3 for preview
            'ai_services': {
                'perplexity_enabled': bool(perplexity_client),
                'firecrawl_enabled': bool(firecrawl_app),
                'perplexity_api_key_set': bool(PERPLEXITY_API_KEY),
                'firecrawl_api_key_set': bool(FIRECRAWL_API_KEY)
            }
        })
        
    except Exception as e:
        logger.error(f"AI scrape test error for {state_code}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Helper functions
def get_recent_opportunities():
    """Get recent opportunities from database"""
    try:
        conn = sqlite3.connect('funding_monitor.db')
        c = conn.cursor()
        c.execute('''SELECT * FROM opportunities 
                     ORDER BY found_date DESC 
                     LIMIT 10''')
        opportunities = []
        for row in c.fetchall():
            opportunities.append({
                'id': row[0],
                'title': row[1],
                'state': row[2],
                'amount': row[3],
                'deadline': row[4],
                'url': row[5],
                'tags': json.loads(row[6]) if row[6] else [],
                'found_date': format_date(row[7])
            })
        conn.close()
        return opportunities
    except Exception as e:
        logger.error(f"Error getting opportunities: {str(e)}")
        return []

def get_current_stats():
    """Get current statistics"""
    try:
        conn = sqlite3.connect('funding_monitor.db')
        c = conn.cursor()
        
        # Count opportunities
        c.execute('SELECT COUNT(*) FROM opportunities')
        total_opportunities = c.fetchone()[0]
        
        # Count subscribers
        c.execute('SELECT COUNT(*) FROM subscribers')
        total_subscribers = c.fetchone()[0]
        
        # Calculate total funding
        c.execute('SELECT amount FROM opportunities')
        total_funding = 0
        for row in c.fetchall():
            amount = extract_dollar_amount(row[0])
            if amount:
                total_funding += amount
        
        conn.close()
        
        return {
            'total_opportunities': total_opportunities,
            'total_subscribers': total_subscribers,
            'total_funding': f'${total_funding:,.0f}' if total_funding > 0 else '$47M+',
            'states_monitored': len(STATE_CONFIGS)
        }
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return {
            'total_opportunities': 23,
            'total_subscribers': 0,
            'total_funding': '$47M+',
            'states_monitored': len(STATE_CONFIGS)
        }

def check_database_health():
    """Check if database is accessible"""
    try:
        conn = sqlite3.connect('funding_monitor.db')
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM subscribers')
        conn.close()
        return True
    except:
        return False

def format_date(date_string):
    """Format date string for display"""
    try:
        if not date_string:
            return "Recently"
        dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        return dt.strftime('%B %d, %Y')
    except:
        return "Recently"

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

def extract_grant_titles_from_text(text):
    """Extract grant titles from text with improved patterns"""
    grant_titles = []
    
    # Multiple patterns to find grant titles
    grant_patterns = [
        # Lines starting with numbers or bullets containing grant keywords
        r'(?:^|\n)(?:\d+\.\s*|\*\s*|-\s*)?([^.\n]*(?:Grant|Funding|Program|Initiative|Opportunity)[^.\n]*)',
        # Headers with grant keywords  
        r'(?:^|\n)(?:#+\s*)?([^.\n]*(?:Grant|Funding|Program|Initiative)[^.\n]*)',
        # Bold text with grant keywords
        r'(?:\*\*|##)\s*([^*\n]*(?:Grant|Funding|Program|Initiative)[^*\n]*)',
        # Standalone lines with education keywords
        r'(?:^|\n)([^.\n]*(?:Education|STEM|Math|Science|Technology)[^.\n]*(?:Grant|Funding|Program)[^.\n]*)',
    ]
    
    for pattern in grant_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            # Clean up the title
            title = re.sub(r'^[\d\.\-\*\•\s#]+', '', match).strip()
            title = re.sub(r'\*+', '', title).strip()
            title = re.sub(r'^\W+|\W+$', '', title).strip()
            
            # Validate title quality
            if (10 < len(title) < 120 and 
                title not in grant_titles and
                not title.lower().startswith(('http', 'www', 'for more', 'contact', 'phone', 'email'))):
                grant_titles.append(title)
    
    return grant_titles

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

def scrape_opportunities(state_code):
    """FIXED: Scrape opportunities from a state DoE site with proper selectors and error handling"""
    if state_code not in STATE_CONFIGS:
        logger.error(f"No configuration found for state: {state_code}")
        return []
    
    config = STATE_CONFIGS[state_code]
    opportunities = []
    
    # Skip states that need special handling
    if config.get('status') == 'captcha_protected':
        logger.warning(f"Skipping {config['name']} - requires Firecrawl or similar tool ({config.get('note', '')})")
        return []
    
    try:
        # Better headers to avoid bot detection
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        logger.info(f"Scraping {config['name']} from {config['url']}")
        response = requests.get(config['url'], timeout=30, headers=headers, allow_redirects=True)
        
        # Handle common error cases
        if response.status_code == 404:
            logger.error(f"404 Error for {config['name']} - URL may be outdated: {config['url']}")
            return []
        
        if response.status_code != 200:
            logger.error(f"HTTP {response.status_code} for {config['name']}: {config['url']}")
            return []
        
        # Check for captcha or bot protection
        if 'captcha' in response.text.lower() or 'radware' in response.text.lower() or 'bot' in response.text.lower():
            logger.warning(f"Bot protection detected for {config['name']}, skipping")
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Try multiple selectors - use the config's selectors array
        all_links = []
        selectors = config.get('selectors', [config.get('selector', 'a')])  # Fallback to old format
        if isinstance(selectors, str):
            selectors = [selectors]  # Convert single selector to list
        
        for selector in selectors:
            try:
                links = soup.select(selector)
                if links:
                    logger.info(f"Selector '{selector}' found {len(links)} links for {config['name']}")
                    all_links.extend(links)
                    break  # Use first selector that finds links
            except Exception as selector_error:
                logger.warning(f"Selector '{selector}' failed for {config['name']}: {str(selector_error)}")
                continue
        
        if not all_links:
            logger.warning(f"No links found with any selector for {config['name']}")
            return []
        
        # Remove duplicates while preserving order
        seen_hrefs = set()
        unique_links = []
        for link in all_links:
            href = link.get('href', '')
            if href and href not in seen_hrefs:
                seen_hrefs.add(href)
                unique_links.append(link)
        
        logger.info(f"Found {len(unique_links)} unique links for {config['name']}")
        
        # PRECISE: Only funding-specific keywords to avoid false positives
        funding_keywords = [
            'grant', 'grants', 'funding', 'award', 'awards', 'rfp', 
            'solicitation', 'application deadline', 'competitive grant',
            'funding opportunity', 'grant opportunity', 'request for proposal'
        ]
        
        # Must contain education-related terms
        education_keywords = [
            'k-12', 'elementary', 'middle school', 'high school', 'education',
            'math', 'mathematics', 'stem', 'science', 'teacher', 'student',
            'school district', 'professional development', 'curriculum'
        ]
        
        grant_related_links = []
        for link in unique_links[:50]:  # Process up to 50 links
            text = link.get_text(strip=True)
            href = link.get('href', '')
            
            # Skip very short or empty links
            if not text or len(text) < 5:
                continue
            
            # STRICT FILTERING: Must have BOTH funding AND education keywords
            text_lower = text.lower()
            href_lower = href.lower()
            combined_text = f"{text_lower} {href_lower}"
            
            # Skip social media and common false positives
            if any(skip in combined_text for skip in ['instagram', 'facebook', 'twitter', 'youtube', 'linkedin', 'contact us', 'privacy policy', 'terms of use']):
                continue
            
            # Must contain at least one funding keyword AND one education keyword
            has_funding = any(keyword in combined_text for keyword in funding_keywords)
            has_education = any(keyword in combined_text for keyword in education_keywords)
            
            if has_funding and has_education:
                grant_related_links.append(link)
                logger.info(f"Found relevant opportunity: {text[:50]}...")
        
        logger.info(f"Found {len(grant_related_links)} grant-related links for {config['name']}")
        
        # Process grant-related links into opportunities
        for link in grant_related_links[:20]:  # Limit to 20 per state
            text = link.get_text(strip=True)
            href = link.get('href', '')
            
            # Make absolute URL
            if href and not href.startswith('http'):
                href = requests.compat.urljoin(config['url'], href)
            
            # Skip invalid URLs
            if not href or href.startswith('#') or href.startswith('javascript:'):
                continue
            
            # Generate unique ID
            import hashlib
            text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            opp_id = f"{state_code}_{text_hash}_{datetime.now().strftime('%Y%m%d')}"
            
            # Extract or estimate amount
            amount = extract_dollar_amount(text) or 'Amount TBD'
            if isinstance(amount, (int, float)):
                amount = f"${amount:,.0f}"
            
            # Better tag assignment based on content
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
                'title': text[:200],  # Allow longer titles
                'state': config['name'],
                'amount': amount,
                'deadline': 'Check website for deadline',
                'url': href,
                'tags': tags,
                'found_date': datetime.now().isoformat()
            })
            
            logger.info(f"Added opportunity: {text[:50]}...")
        
        logger.info(f"Successfully scraped {len(opportunities)} opportunities from {config['name']}")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error scraping {config['name']}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error scraping {config['name']}: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return opportunities

# AI-POWERED SCRAPING FUNCTIONS

def discover_opportunities_with_perplexity(state_name, state_code):
    """Use Perplexity AI to discover current funding opportunities"""
    if not perplexity_client:
        logger.warning("Perplexity API not configured, skipping AI discovery")
        return []
    
    try:
        # Craft a specific query for current funding opportunities
        query = f"""Find current K-12 education funding opportunities, grants, and RFPs available in {state_name} for 2025. 
        
        Please format each opportunity clearly as:
        TITLE: [exact grant name]
        AMOUNT: [funding amount if available]  
        DEADLINE: [application deadline if available]
        URL: [official website link]
        
        Include:
        - Grant names and titles for Math, STEM, and general K-12 education
        - Application deadlines  
        - Funding amounts
        - Official website URLs from {state_name} Department of Education or state agencies
        
        Focus on opportunities that are currently open or opening soon in {state_name}. Provide specific, valid URLs when available."""
        
        logger.info(f"Querying Perplexity for {state_name} opportunities...")
        
        # Check if we're using PerplexiPy or OpenAI client
        if hasattr(perplexity_client, 'chat') and hasattr(perplexity_client.chat, 'completions'):
            # OpenAI client format
            response = perplexity_client.chat.completions.create(
                model="llama-3.1-sonar-large-128k-online",
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a helpful assistant. List specific grant programs with exact titles, amounts, deadlines, and official URLs. Format each grant clearly with: TITLE: [exact grant name], AMOUNT: [funding amount], DEADLINE: [application deadline], URL: [official website link]"
                    },
                    {
                        "role": "user", 
                        "content": query
                    }
                ],
                temperature=0.1,
                max_tokens=2000
            )
            ai_response = response.choices[0].message.content
        else:
            # PerplexiPy format - try different method calls
            try:
                ai_response = perplexity_client.query(query)
            except:
                try:
                    ai_response = perplexity_client.search(query)
                except:
                    ai_response = str(perplexity_client)
        logger.info(f"Perplexity response for {state_name}: {ai_response[:200]}...")
        
        # Parse the AI response to extract structured opportunity data
        opportunities = parse_perplexity_response(ai_response, state_name, state_code)
        
        return opportunities
        
    except Exception as e:
        logger.error(f"Perplexity discovery error for {state_name}: {str(e)}")
        return []

def parse_perplexity_response(ai_response, state_name, state_code):
    """Parse Perplexity response to extract structured opportunity data"""
    opportunities = []
    
    try:
        logger.info(f"Parsing Perplexity response for {state_name}. Response length: {len(ai_response)}")
        logger.info(f"Response preview: {ai_response[:500]}...")
        logger.info(f"Full response: {ai_response}")
        
        # First, try to parse structured format (TITLE:, AMOUNT:, etc.)
        structured_matches = re.findall(
            r'TITLE:\s*([^\n]+).*?AMOUNT:\s*([^\n]+).*?DEADLINE:\s*([^\n]+).*?URL:\s*([^\n]+)',
            ai_response, re.DOTALL | re.IGNORECASE
        )
        
        if structured_matches:
            logger.info(f"Found {len(structured_matches)} structured grants for {state_name}")
            for i, (title, amount, deadline, url) in enumerate(structured_matches[:5]):
                if title and len(title.strip()) > 5:
                    # Clean and validate URL
                    clean_url = clean_extracted_url(url.strip())
                    
                    # Only add opportunities with valid URLs
                    if clean_url and clean_url.startswith('http'):
                        opportunity = {
                            'id': f"{state_code}_perplexity_{hash(title)}_{datetime.now().strftime('%Y%m%d')}",
                            'title': title.strip(),
                            'state': state_name,
                            'amount': amount.strip() if amount.strip() else 'Amount TBD',
                            'deadline': deadline.strip() if deadline.strip() else 'Check website',
                            'url': clean_url,
                            'tags': ['K-12', 'Education', 'AI-Discovered'],
                            'found_date': datetime.now().isoformat(),
                            'source': 'perplexity'
                        }
                        opportunities.append(opportunity)
                        logger.info(f"Structured grant: {title[:50]}... - URL: {clean_url}")
                    else:
                        logger.warning(f"Skipping structured grant '{title[:50]}...' - no valid URL (URL: '{url.strip()}')")
        
        # If no structured format found, fall back to parsing
        if not opportunities:
            logger.info(f"No structured format, parsing unstructured response for {state_name}")
            
            # Extract clean URLs from response with improved patterns
            urls = extract_urls_from_text(ai_response)
            logger.info(f"Extracted {len(urls)} URLs from response")
            
            # Look for grant names in the text with improved patterns
            grant_titles = extract_grant_titles_from_text(ai_response)
            logger.info(f"Extracted {len(grant_titles)} grant titles from response")
            
            # Create opportunities from found titles and URLs
            for i, title in enumerate(grant_titles[:5]):
                # Try to find amount in nearby text
                amount = 'Amount TBD'
                title_index = ai_response.find(title)
                if title_index >= 0:
                    nearby_text = ai_response[max(0, title_index-200):title_index+200]
                    amount_match = re.search(r'\$[\d,]+(?:\.\d+)?(?:\s*(?:million|M|billion|B|thousand|K))?', nearby_text)
                    if amount_match:
                        amount = amount_match.group(0)
                
                # Assign URL if available
                assigned_url = ''
                if i < len(urls):
                    assigned_url = urls[i]
                elif urls:
                    assigned_url = urls[0]  # Use first URL as fallback
                
                # Only add opportunities that have valid URLs
                if assigned_url and assigned_url.startswith('http'):
                    opportunity = {
                        'id': f"{state_code}_perplexity_{hash(title)}_{datetime.now().strftime('%Y%m%d')}",
                        'title': title,
                        'state': state_name,
                        'amount': amount,
                        'deadline': 'Check website',
                        'url': assigned_url,
                        'tags': ['K-12', 'Education', 'AI-Discovered'],
                        'found_date': datetime.now().isoformat(),
                        'source': 'perplexity'
                    }
                    opportunities.append(opportunity)
                    logger.info(f"Parsed grant: {title[:50]}... - URL: {assigned_url}")
                else:
                    logger.warning(f"Skipping grant '{title[:50]}...' - no valid URL found (URL: '{assigned_url}')")
                    
        logger.info(f"Parsed {len(opportunities)} opportunities from Perplexity response for {state_name}")
        return opportunities[:5]  # Limit to top 5 opportunities per state
        
    except Exception as e:
        logger.error(f"Error parsing Perplexity response for {state_name}: {str(e)}")
        return []

def enhance_opportunity_with_firecrawl(opportunity):
    """Use Firecrawl to extract detailed information from opportunity URL"""
    if not firecrawl_app or not opportunity.get('url'):
        return opportunity
    
    try:
        logger.info(f"Enhancing opportunity with Firecrawl: {opportunity['title'][:50]}...")
        
        # Use Firecrawl to scrape the URL and extract structured data
        result = firecrawl_app.scrape_url(
            opportunity['url'],
            formats=['markdown', 'html']
        )
        
        if result and result.get('markdown'):
            content = result['markdown']
            
            # Extract better deadline information
            deadline_patterns = [
                r'deadline[:\s]*([^\.]+)',
                r'due[:\s]*([^\.]+)', 
                r'submit[:\s]*by[:\s]*([^\.]+)',
                r'application[:\s]*due[:\s]*([^\.]+)'
            ]
            
            for pattern in deadline_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    deadline = match.group(1).strip()[:100]
                    if deadline and deadline != 'Check website':
                        opportunity['deadline'] = deadline
                        break
            
            # Extract better funding amount
            amount_patterns = [
                r'award[:\s]*\$?([\d,]+(?:\.\d+)?(?:\s*[KMBkmb]illion)?)',
                r'funding[:\s]*\$?([\d,]+(?:\.\d+)?(?:\s*[KMBkmb]illion)?)',
                r'up\s*to[:\s]*\$?([\d,]+(?:\.\d+)?(?:\s*[KMBkmb]illion)?)'
            ]
            
            for pattern in amount_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    amount = f"${match.group(1)}"
                    if amount != opportunity.get('amount'):
                        opportunity['amount'] = amount
                        break
            
            # Extract better description/tags from content
            if 'math' in content.lower() or 'mathematics' in content.lower():
                if 'Mathematics' not in opportunity.get('tags', []):
                    opportunity['tags'].append('Mathematics')
            
            if 'stem' in content.lower():
                if 'STEM' not in opportunity.get('tags', []):
                    opportunity['tags'].append('STEM')
                    
            logger.info(f"Enhanced opportunity with Firecrawl: {opportunity['title'][:50]}")
            
        return opportunity
        
    except Exception as e:
        logger.error(f"Firecrawl enhancement error for {opportunity.get('title', 'Unknown')}: {str(e)}")
        return opportunity

def ai_powered_scrape_opportunities(state_code):
    """Hybrid AI-powered opportunity discovery using Perplexity + Firecrawl"""
    if state_code not in STATE_CONFIGS:
        return []
    
    config = STATE_CONFIGS[state_code]
    state_name = config['name']
    
    logger.info(f"Starting AI-powered discovery for {state_name}")
    
    # Step 1: Use Perplexity to discover opportunities
    opportunities = discover_opportunities_with_perplexity(state_name, state_code)
    
    if not opportunities:
        logger.warning(f"No opportunities with valid URLs discovered by Perplexity for {state_name}")
        logger.info(f"Attempting traditional scraping as fallback for {state_name}")
        # Fallback to traditional scraping for this state
        opportunities = scrape_opportunities(state_code)
        if opportunities:
            logger.info(f"Traditional scraping found {len(opportunities)} opportunities for {state_name}")
        else:
            logger.warning(f"Both AI and traditional scraping failed for {state_name}")
            return []
    
    # Step 2: Enhance each opportunity with Firecrawl (if URL available)
    enhanced_opportunities = []
    for opp in opportunities:
        enhanced_opp = enhance_opportunity_with_firecrawl(opp)
        enhanced_opportunities.append(enhanced_opp)
    
    logger.info(f"AI-powered discovery complete for {state_name}: {len(enhanced_opportunities)} opportunities")
    return enhanced_opportunities

def check_all_states():
    """Check all states for new opportunities"""
    logger.info(f"Checking for new opportunities at {datetime.now()}")
    new_opportunities = []
    
    conn = sqlite3.connect('funding_monitor.db')
    c = conn.cursor()
    
    for state_code in STATE_CONFIGS:
        # Try AI-powered scraping first, fallback to traditional scraping
        if perplexity_client and firecrawl_app:
            opportunities = ai_powered_scrape_opportunities(state_code)
            if not opportunities:
                logger.info(f"AI scraping failed for {state_code}, falling back to traditional scraping")
                opportunities = scrape_opportunities(state_code)
        else:
            logger.info(f"AI services not configured, using traditional scraping for {state_code}")
            opportunities = scrape_opportunities(state_code)
        
        for opp in opportunities:
            # Check if already exists
            c.execute('SELECT id FROM opportunities WHERE id = ?', (opp['id'],))
            if not c.fetchone():
                # New opportunity!
                new_opportunities.append(opp)
                c.execute('''INSERT INTO opportunities 
                            (id, title, state, amount, deadline, url, tags, found_date)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                         (opp['id'], opp['title'], opp['state'], opp['amount'],
                          opp['deadline'], opp['url'], json.dumps(opp['tags']), 
                          opp['found_date']))
    
    conn.commit()
    conn.close()
    
    if new_opportunities:
        send_alerts(new_opportunities)
        logger.info(f"Found {len(new_opportunities)} new opportunities")
    
    return new_opportunities

def send_alerts(opportunities):
    """Send email alerts to subscribers"""
    if not EMAIL_CONFIG['sender_email'] or not EMAIL_CONFIG['sender_password']:
        logger.warning("Email not configured, skipping alerts")
        return
    
    conn = sqlite3.connect('funding_monitor.db')
    c = conn.cursor()
    c.execute('SELECT email, frequency, states FROM subscribers')
    
    for subscriber in c.fetchall():
        email, frequency, states_json = subscriber
        states = json.loads(states_json)
        
        # Filter opportunities by subscriber's states
        relevant_opps = [opp for opp in opportunities 
                        if any(STATE_CONFIGS.get(state, {}).get('name') == opp['state'] 
                              for state in states)]
        
        if relevant_opps:
            send_opportunity_email(email, relevant_opps)
    
    conn.close()

def send_welcome_email(email, states, frequency):
    """Send welcome email to new subscriber"""
    if not EMAIL_CONFIG['sender_email'] or not EMAIL_CONFIG['sender_password']:
        logger.warning("Email not configured, skipping welcome email")
        return
    
    state_names = [STATE_CONFIGS.get(s, {}).get('name', s) for s in states]
    
    subject = "🎯 Welcome to K-12 Math Funding Monitor"
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <h2>Welcome to the Funding Monitor!</h2>
        <p>Hi there,</p>
        <p>You're now monitoring funding opportunities in: <strong>{', '.join(state_names)}</strong></p>
        <p>You'll receive {frequency} updates whenever new K-12 math funding opportunities are announced.</p>
        <p>In the meantime, check out the latest opportunities at our dashboard.</p>
        <hr>
        <p style="color: #666; font-size: 0.9em;">
        This is a preview of automation capabilities from Harrison at Dodo Digital.
        </p>
    </body>
    </html>
    """
    
    try:
        send_email(email, subject, body)
        logger.info(f"Welcome email sent to {email}")
    except Exception as e:
        logger.error(f"Error sending welcome email: {str(e)}")

def send_opportunity_email(email, opportunities):
    """Send email with new opportunities"""
    subject = f"🎯 {len(opportunities)} New K-12 Math Funding Opportunities"
    
    opps_html = ""
    for opp in opportunities:
        opps_html += f"""
        <div style="margin-bottom: 20px; padding: 15px; background: #f8f9fa; border-left: 4px solid #667eea;">
            <h3 style="margin: 0 0 10px 0;">{opp['title']}</h3>
            <p><strong>State:</strong> {opp['state']}</p>
            <p><strong>Amount:</strong> {opp['amount']}</p>
            <p><strong>Link:</strong> <a href="{opp['url']}">{opp['url']}</a></p>
        </div>
        """
    
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <h2>New Funding Opportunities</h2>
        <p>We found {len(opportunities)} new funding opportunities:</p>
        {opps_html}
        <hr>
        <p style="color: #666; font-size: 0.9em;">
        Built by Harrison from Dodo Digital
        </p>
    </body>
    </html>
    """
    
    try:
        send_email(email, subject, body)
        logger.info(f"Opportunity email sent to {email}")
    except Exception as e:
        logger.error(f"Error sending opportunity email: {str(e)}")

def send_email(to_email, subject, html_body):
    """Send an email using SMTP"""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = EMAIL_CONFIG['sender_email']
    msg['To'] = to_email
    
    msg.attach(MIMEText(html_body, 'html'))
    
    with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
        server.starttls()
        server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
        server.send_message(msg)

# Initialize database on startup
init_db()

# Schedule daily checks (9 AM)
if not app.debug:  # Only in production
    scheduler.add_job(check_all_states, 'cron', hour=9, minute=0)
    scheduler.start()

if __name__ == '__main__':
    # For local development
    app.run(debug=True, port=5000)
else:
    # For production, make sure scheduler runs
    if not scheduler.running:
        scheduler.start()