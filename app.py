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

# Database configuration - use Railway's persistent volume
DATABASE_DIR = os.environ.get('DATABASE_DIR', '/data' if os.environ.get('RAILWAY_ENVIRONMENT') else '.')
os.makedirs(DATABASE_DIR, exist_ok=True)
DATABASE_PATH = os.path.join(DATABASE_DIR, 'funding_monitor.db')
logger.info(f"Using database at: {DATABASE_PATH}")

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

# State DoE configurations - UPDATED with verified working grant sources
STATE_CONFIGS = {
    'TX': {
        'name': 'Texas',
        'url': 'https://tea.texas.gov/finance-and-grants/grants',
        'selectors': ['.field--name-body a', '.sectional-box a', 'strong a', '.field--type-text-with-summary a'],
        'status': 'active',
        'source_type': 'state',
        'note': 'T-STEM grants and TEA funding opportunities'
    },
    'CA': {
        'name': 'California', 
        'url': 'https://www.cde.ca.gov/fg/fo/af/',
        'selectors': ['main a', '.content a', 'table a'],
        'status': 'active',  # Verified working with real grants
        'source_type': 'state',
        'note': 'Golden State Pathways Program and CDE funding opportunities'
    },
    'FL': {
        'name': 'Florida',
        'url': 'https://www.fldoe.org/academics/career-adult-edu/funding-opportunities/2024-2025-funding-opportunities/',
        'selectors': ['.content a', 'main a', 'table a'],
        'status': 'active',
        'source_type': 'state',
        'note': 'Computer Science grants and FDOE funding opportunities'
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
    },
    'VA': {
        'name': 'Virginia',
        'url': 'https://www.doe.virginia.gov/parents-students/for-parents/k-12-learning-acceleration-grants',
        'selectors': ['main a', '.content a', 'article a'],
        'source_type': 'direct_crawl',
        'status': 'active'
    },
    'CO': {
        'name': 'Colorado',
        'url': 'https://www.cde.state.co.us/cdeawards/grants',
        'selectors': ['.content a', 'main a', '.grants-list a'],
        'source_type': 'direct_crawl',
        'status': 'active'
    },
    'OR': {
        'name': 'Oregon',
        'url': 'https://www.oregon.gov/ode/schools-and-districts/grants/pages/k-12-school-funding-information.aspx',
        'selectors': ['.content a', 'main a', '.grant-links a'],
        'source_type': 'direct_crawl',
        'status': 'active'
    },
    'AZ': {
        'name': 'Arizona',
        'url': 'https://www.azed.gov/grants/',
        'selectors': ['.content a', 'main a', '.grant-opportunities a'],
        'source_type': 'direct_crawl',
        'status': 'needs_verification'
    },
    'WA': {
        'name': 'Washington',
        'url': 'https://www.k12.wa.us/about-ospi/grants-contracts',
        'selectors': ['.content a', 'main a', '.grants-list a'],
        'source_type': 'direct_crawl',
        'status': 'needs_verification'
    },
    # Federal sources - UPDATED with verified grant programs
    'NSF_DRK12': {
        'name': 'NSF Discovery Research PreK-12',
        'url': 'https://www.nsf.gov/funding/opportunities/drk-12-discovery-research-prek-12',
        'selectors': ['.content a', 'main a', '.opportunity-details a'],
        'source_type': 'federal',
        'status': 'active',
        'note': '$50M available for PreK-12 STEM education research'
    },
    'ED_EIR': {
        'name': 'Education Innovation and Research',
        'url': 'https://www.ed.gov/grants-and-programs/grants-special-populations/economically-disadvantaged-students/education-innovation-and-research',
        'selectors': ['.content a', 'main a', '.grant-details a'],
        'source_type': 'federal',
        'status': 'active',
        'note': 'Innovation grants for early-phase, mid-phase, and expansion'
    },
    'GRANTS_GOV': {
        'name': 'Grants.gov Education',
        'url': 'https://www.grants.gov/search-grants?keywords=STEM',
        'selectors': ['.grant-listing a', '.results a', '.opportunity-link'],
        'source_type': 'federal',
        'status': 'active',
        'note': 'Federal STEM grants portal'
    }
}

# Database setup
def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS subscribers
                 (email TEXT PRIMARY KEY, frequency TEXT, states TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS opportunities
                 (id TEXT PRIMARY KEY, title TEXT, state TEXT, amount TEXT, 
                  deadline TEXT, url TEXT, tags TEXT, found_date TEXT,
                  eligibility TEXT, description TEXT, contact_info TEXT,
                  source_type TEXT, quality_score REAL, application_process TEXT,
                  source_reliability TEXT)''')
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
        conn = sqlite3.connect(DATABASE_PATH)
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
    """Get latest funding opportunities with filtering and pagination"""
    try:
        # Get query parameters
        state = request.args.get('state', '')
        offset = int(request.args.get('offset', 0))
        limit = int(request.args.get('limit', 10))
        
        # Get filtered opportunities
        opportunities = get_recent_opportunities(state_filter=state, offset=offset, limit=limit)
        
        # Get total count for pagination
        total_count = get_opportunities_count(state_filter=state)
        
        return jsonify({
            'success': True,
            'opportunities': opportunities,
            'count': len(opportunities),
            'total_count': total_count,
            'offset': offset,
            'limit': limit,
            'has_more': offset + len(opportunities) < total_count,
            'state_filter': state if state else 'ALL'
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

@app.route('/api/populate-verified', methods=['POST'])
def populate_verified_opportunities():
    """Populate database with verified real opportunities"""
    try:
        added_count = add_verified_opportunities()
        return jsonify({
            'success': True,
            'message': f'Added {added_count} verified opportunities to database.',
            'opportunities_added': added_count
        })
    except Exception as e:
        logger.error(f"Error populating verified opportunities: {str(e)}")
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

@app.route('/api/debug/perplexity/<state_code>', methods=['GET'])
def debug_perplexity(state_code):
    """Debug endpoint to see raw Perplexity response"""
    if state_code.upper() not in STATE_CONFIGS:
        return jsonify({'success': False, 'error': 'Invalid state code'}), 400
    
    if not perplexity_client:
        return jsonify({'success': False, 'error': 'Perplexity client not configured'}), 500
    
    try:
        config = STATE_CONFIGS[state_code.upper()]
        state_name = config['name']
        
        # Same query as the main function
        query = f"""Find current K-12 education funding opportunities, grants, and RFPs available in {state_name} for 2025. 

Return ONLY a JSON array of opportunities in this exact format:
[
  {{
    "title": "Exact grant name",
    "amount": "Funding amount or TBD",
    "deadline": "Application deadline or TBD", 
    "url": "Direct link to grant application or info page"
  }}
]

Requirements:
- Find 3-5 current opportunities for Math, STEM, or general K-12 education
- Each URL must be a direct, working link to the grant information
- Focus on {state_name} Department of Education or state agency grants
- Only include opportunities that are currently open or opening soon

Return ONLY the JSON array, no other text."""
        
        # Make the API call
        if hasattr(perplexity_client, 'chat') and hasattr(perplexity_client.chat, 'completions'):
            response = perplexity_client.chat.completions.create(
                model="llama-3.1-sonar-large-128k-online",
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a research assistant that finds funding opportunities. Always respond with valid JSON only. Never include explanatory text, just the JSON array."
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
            
            return jsonify({
                'success': True,
                'state': state_name,
                'query': query,
                'raw_response': ai_response,
                'response_length': len(ai_response),
                'client_type': 'OpenAI'
            })
        else:
            return jsonify({'success': False, 'error': 'Unexpected client type'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'error_type': type(e).__name__}), 500

@app.route('/api/states', methods=['GET'])
def api_states():
    """Get available states with opportunity counts"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''SELECT state, COUNT(*) as count 
                     FROM opportunities 
                     GROUP BY state 
                     ORDER BY state''')
        
        states = []
        total_count = 0
        for row in c.fetchall():
            state_name = row[0]
            count = row[1]
            states.append({
                'code': state_name,
                'name': state_name,
                'count': count
            })
            total_count += count
        
        conn.close()
        
        # Add "All States" option at the beginning
        states.insert(0, {
            'code': 'ALL',
            'name': 'All States',
            'count': total_count
        })
        
        return jsonify({
            'success': True,
            'states': states
        })
    except Exception as e:
        logger.error(f"Error fetching states: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Helper functions
def get_recent_opportunities(state_filter='', offset=0, limit=10):
    """Get recent opportunities from database with filtering and pagination"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        # Build query with optional state filter
        if state_filter and state_filter != 'ALL':
            query = '''SELECT * FROM opportunities 
                      WHERE state = ?
                      ORDER BY found_date DESC 
                      LIMIT ? OFFSET ?'''
            c.execute(query, (state_filter, limit, offset))
        else:
            query = '''SELECT * FROM opportunities 
                      ORDER BY found_date DESC 
                      LIMIT ? OFFSET ?'''
            c.execute(query, (limit, offset))
        
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
                'found_date': format_date(row[7]),
                'eligibility': row[8] if len(row) > 8 else '',
                'description': row[9] if len(row) > 9 else '',
                'contact_info': row[10] if len(row) > 10 else '',
                'source_type': row[11] if len(row) > 11 else 'unknown',
                'quality_score': row[12] if len(row) > 12 else 5.0,
                'application_process': row[13] if len(row) > 13 else '',
                'source_reliability': row[14] if len(row) > 14 else 'medium'
            })
        conn.close()
        return opportunities
    except Exception as e:
        logger.error(f"Error getting opportunities: {str(e)}")
        return []

def get_opportunities_count(state_filter=''):
    """Get total count of opportunities for pagination"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        if state_filter and state_filter != 'ALL':
            c.execute('SELECT COUNT(*) FROM opportunities WHERE state = ?', (state_filter,))
        else:
            c.execute('SELECT COUNT(*) FROM opportunities')
        
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Error getting opportunities count: {str(e)}")
        return 0

def get_current_stats():
    """Get current statistics"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
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
            'total_funding': f'${total_funding:,.0f}' if total_funding > 0 else 'TBD',
            'states_monitored': len(STATE_CONFIGS)
        }
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return {
            'total_opportunities': 23,
            'total_subscribers': 0,
            'total_funding': 'TBD',
            'states_monitored': len(STATE_CONFIGS)
        }

def check_database_health():
    """Check if database is accessible"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
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

def is_high_quality_opportunity(title, url, amount, deadline):
    """Filter out low-quality opportunities that aren't actionable"""
    
    # Red flags in title (budget documents, summaries, etc.)
    title_lower = title.lower()
    red_flag_terms = [
        'budget', 'summary', 'legislative', 'archive', 'report', 'overview',
        'analysis', 'appropriation', 'bill', 'legislation', 'hearing',
        'committee', 'minutes', 'agenda', 'presentation', 'slides'
    ]
    
    for term in red_flag_terms:
        if term in title_lower:
            logger.info(f"Quality check: Rejected '{title[:50]}' - contains red flag term: '{term}'")
            return False
    
    # Red flags in URL (PDFs, archives, etc.)
    url_lower = url.lower()
    url_red_flags = [
        '.pdf', '/archive', '/budget', '/legislative', '/summary',
        '/reports', '/presentations', '/minutes', '/hearing'
    ]
    
    for flag in url_red_flags:
        if flag in url_lower:
            logger.info(f"Quality check: Rejected '{title[:50]}' - URL contains red flag: '{flag}'")
            return False
    
    # Must have some indication this is actionable
    actionable_terms = [
        'application', 'apply', 'grant', 'rfp', 'request for proposal',
        'funding opportunity', 'competitive', 'solicitation', 'award'
    ]
    
    combined_text = f"{title_lower} {url_lower}"
    has_actionable = any(term in combined_text for term in actionable_terms)
    
    if not has_actionable:
        logger.info(f"Quality check: Rejected '{title[:50]}' - no actionable terms found")
        return False
    
    # Prefer opportunities with specific amounts and deadlines
    has_amount = amount and amount.lower() not in ['tbd', 'to be determined', 'varies']
    has_deadline = deadline and deadline.lower() not in ['tbd', 'to be determined', 'varies']
    
    # At least one should be specific
    if not has_amount and not has_deadline:
        logger.info(f"Quality check: Warning for '{title[:50]}' - both amount and deadline are vague")
    
    logger.info(f"Quality check: Approved '{title[:50]}' - passed all quality filters")
    return True

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

def crawl_official_sources(state_code):
    """NEW: Crawl official DoE sources using Firecrawl for reliable opportunities"""
    if state_code not in STATE_CONFIGS:
        logger.error(f"State {state_code} not in configuration")
        return []
    
    config = STATE_CONFIGS[state_code]
    state_name = config['name']
    
    # Skip inactive sources
    if config.get('status') == 'inactive':
        logger.info(f"Skipping inactive source: {state_name}")
        return []
    
    logger.info(f"Crawling official source for {state_name}: {config['url']}")
    
    opportunities = []
    
    # Use Firecrawl for reliable content extraction
    if firecrawl_app:
        opportunities = firecrawl_crawl_source(config, state_code)
    else:
        logger.warning(f"Firecrawl not available, falling back to AI discovery for {state_name}")
        opportunities = discover_opportunities_with_perplexity(state_name, state_code)
    
    return opportunities

def firecrawl_crawl_source(config, state_code):
    """Use Firecrawl to extract opportunities from official source"""
    state_name = config['name']
    url = config['url']
    
    try:
        logger.info(f"Firecrawl scraping {state_name} source: {url}")
        
        # Scrape the main grants page
        result = firecrawl_app.scrape_url(
            url,
            formats=['markdown', 'html']
        )
        
        if not result or not result.get('markdown'):
            logger.warning(f"Firecrawl returned empty result for {state_name}")
            return []
        
        content = result['markdown']
        logger.info(f"Retrieved {len(content)} characters from {state_name}")
        
        # Extract grant opportunities from the content
        opportunities = extract_opportunities_from_content(content, config, state_code)
        
        # Enhance each opportunity with detailed info
        enhanced_opportunities = []
        for opp in opportunities:
            if opp.get('url'):
                enhanced_opp = enhance_opportunity_with_firecrawl(opp)
                enhanced_opportunities.append(enhanced_opp)
            else:
                enhanced_opportunities.append(opp)
        
        logger.info(f"Firecrawl found {len(enhanced_opportunities)} opportunities for {state_name}")
        return enhanced_opportunities
        
    except Exception as e:
        logger.error(f"Firecrawl error for {state_name}: {str(e)}")
        return []

def extract_opportunities_from_content(content, config, state_code):
    """Extract structured opportunity data from scraped content"""
    state_name = config['name']
    opportunities = []
    
    # Look for grant-related patterns in the content
    grant_patterns = [
        r'(?i)([^\.]+(?:grant|funding|award|rfp|solicitation)[^\.]{10,100})',
        r'(?i)(application\s+for[^\.]{20,100})',
        r'(?i)([^\.]*\$[\d,]+[^\.]{10,100})',
    ]
    
    # Extract URLs from content (look for grant-related links)
    url_patterns = [
        r'(https?://[^\s\)]+(?:grant|funding|award|application|rfp)[^\s\)]*)',
        r'(https?://[^\s\)]+\.(?:pdf|html|aspx)[^\s\)]*)'
    ]
    
    found_urls = set()
    for pattern in url_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        found_urls.update(matches)
    
    # For each URL, try to extract opportunity info
    for url in list(found_urls)[:10]:  # Limit to 10 URLs to avoid overwhelming
        # Extract title from surrounding context
        title = extract_title_near_url(content, url)
        
        if not title:
            continue
            
        # Apply quality filters
        if not is_high_quality_opportunity(title, url, "TBD", "TBD"):
            continue
        
        opportunity = {
            'id': f"{state_code}_firecrawl_{hash(title)}_{datetime.now().strftime('%Y%m%d')}",
            'title': title,
            'state': state_name,
            'amount': 'TBD',
            'deadline': 'TBD',
            'url': url,
            'tags': ['K-12', 'Education', 'Official-Source'],
            'found_date': datetime.now().isoformat(),
            'source': 'firecrawl',
            'source_type': config.get('source_type', 'state'),
            'raw_extract': True  # Flag for later enhancement
        }
        
        opportunities.append(opportunity)
    
    return opportunities

def extract_title_near_url(content, url):
    """Extract a likely title from text near the URL"""
    # Find the URL in content and get surrounding text
    url_index = content.find(url)
    if url_index == -1:
        return None
    
    # Get text before the URL (likely title)
    start = max(0, url_index - 200)
    before_text = content[start:url_index]
    
    # Look for title patterns
    title_patterns = [
        r'(?i)([^\.]+(?:grant|funding|award|program|initiative)[^\.]*)',
        r'(?i)(\b[A-Z][^\.]{10,80})',  # Capitalized phrases
        r'(?i)(application\s+for[^\.]+)',
    ]
    
    for pattern in title_patterns:
        matches = re.findall(pattern, before_text)
        if matches:
            title = matches[-1].strip()  # Take the last (closest) match
            if len(title) > 10 and len(title) < 100:
                return title
    
    return None

def discover_opportunities_with_perplexity(state_name, state_code):
    """Use Perplexity AI to discover current funding opportunities"""
    if not perplexity_client:
        logger.warning("Perplexity API not configured, skipping AI discovery")
        return []
    
    try:
        # Craft a specific query for HIGH-QUALITY, actionable funding opportunities
        query = f"""I need current, actionable K-12 education funding opportunities that school administrators can apply for RIGHT NOW in {state_name}.

CRITICAL REQUIREMENTS:
- Must be ACTIVE grant programs with current application periods (not archived or past opportunities)
- Must have clear application processes (not just PDFs with budget information)
- Must be from official government sources ({state_name} Department of Education, federal agencies, or authorized state programs)
- Must specify funding amounts and deadlines
- Must be for K-12 mathematics, STEM education, or general school improvement

EXCLUDE:
- Budget documents, legislative summaries, or archived reports
- Programs that are "coming soon" without application details
- Private foundation grants (focus on government funding)
- Programs that require pre-qualification or multi-year commitments without current openings

Return ONLY opportunities that a school administrator could realistically apply for this month.

Format as JSON array:
[
  {{
    "title": "Official grant program name",
    "amount": "Specific funding amount (e.g., '$50,000 per school')",
    "deadline": "Exact application deadline",
    "url": "Direct link to application page or RFP"
  }}
]

Focus on finding 2-3 HIGH-QUALITY opportunities rather than many low-quality ones."""
        
        logger.info(f"Querying Perplexity for {state_name} opportunities...")
        
        # Check if we're using PerplexiPy or OpenAI client
        if hasattr(perplexity_client, 'chat') and hasattr(perplexity_client.chat, 'completions'):
            # OpenAI client format
            response = perplexity_client.chat.completions.create(
                model="llama-3.1-sonar-large-128k-online",
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a research assistant that finds funding opportunities. Always respond with valid JSON only. Never include explanatory text, just the JSON array."
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
            
            # Extract sources/citations from Perplexity response
            sources = []
            if hasattr(response, 'search_results') and response.search_results:
                sources = [result.get('url', '') for result in response.search_results if result.get('url')]
                logger.info(f"Found {len(sources)} sources from Perplexity: {sources}")
            elif hasattr(response, 'citations') and response.citations:
                sources = response.citations
                logger.info(f"Found {len(sources)} citations from Perplexity: {sources}")
            else:
                logger.warning(f"No search_results or citations found in Perplexity response for {state_name}")
                logger.info(f"Full response object keys: {list(response.__dict__.keys()) if hasattr(response, '__dict__') else 'No __dict__'}")
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
        opportunities = parse_perplexity_response(ai_response, state_name, state_code, sources if 'sources' in locals() else [])
        
        return opportunities
        
    except Exception as e:
        logger.error(f"Perplexity discovery error for {state_name}: {str(e)}")
        return []

def parse_perplexity_response(ai_response, state_name, state_code, sources=[]):
    """Parse Perplexity JSON response to extract opportunity data"""
    opportunities = []
    
    try:
        logger.info(f"Parsing Perplexity JSON response for {state_name}. Response length: {len(ai_response)}")
        logger.info(f"Raw response: {ai_response}")
        
        # Clean up the response to extract JSON
        json_text = ai_response.strip()
        
        # Remove markdown code blocks
        if json_text.startswith('```'):
            # Remove opening ```
            json_text = json_text[3:]
            if json_text.startswith('json'):
                json_text = json_text[4:]
            json_text = json_text.strip()
            
            # Remove closing ```
            if json_text.endswith('```'):
                json_text = json_text[:-3].strip()
        
        # Remove any text before the JSON array
        if '[' in json_text:
            json_text = json_text[json_text.find('['):]
        
        # Remove any text after the JSON array
        if ']' in json_text:
            # Find the last closing bracket
            last_bracket = json_text.rfind(']')
            json_text = json_text[:last_bracket + 1]
        
        logger.info(f"Cleaned JSON text: {json_text}")
        
        # Parse the JSON
        try:
            grant_data = json.loads(json_text)
            
            # Validate that we got an array
            if not isinstance(grant_data, list):
                logger.error(f"Expected JSON array, got {type(grant_data)}: {grant_data}")
                logger.info(f"Falling back to text parsing for {state_name}")
                return fallback_text_parsing(ai_response, state_name, state_code)
            
            logger.info(f"Successfully parsed JSON with {len(grant_data)} grants")
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed: {e}")
            logger.error(f"Attempted to parse: {json_text}")
            logger.info(f"Falling back to text parsing for {state_name}")
            
            # Fallback to text parsing if JSON fails
            return fallback_text_parsing(ai_response, state_name, state_code)
        
        # Convert JSON data to opportunities
        for i, grant in enumerate(grant_data[:5]):  # Limit to 5
            try:
                title = grant.get('title', '').strip()
                amount = grant.get('amount', 'Amount TBD').strip()
                deadline = grant.get('deadline', 'Check website').strip()
                url = grant.get('url', '').strip()
                
                # Validate required fields
                if not title or len(title) < 5:
                    logger.warning(f"Skipping grant {i+1} - invalid title: '{title}'")
                    continue
                
                # Clean and validate URL
                clean_url = clean_extracted_url(url)
                if not clean_url or not clean_url.startswith('http'):
                    logger.warning(f"Skipping grant '{title[:50]}...' - invalid URL: '{url}'")
                    continue
                
                # Quality validation - skip low-quality opportunities
                if not is_high_quality_opportunity(title, clean_url, amount, deadline):
                    logger.warning(f"Skipping low-quality grant '{title[:50]}...' - failed quality check")
                    continue
                
                opportunity = {
                    'id': f"{state_code}_perplexity_{hash(title)}_{datetime.now().strftime('%Y%m%d')}",
                    'title': title,
                    'state': state_name,
                    'amount': amount,
                    'deadline': deadline,
                    'url': clean_url,
                    'tags': ['K-12', 'Education', 'AI-Discovered'],
                    'found_date': datetime.now().isoformat(),
                    'source': 'perplexity'
                }
                opportunities.append(opportunity)
                logger.info(f"Added grant: {title[:50]}... - URL: {clean_url}")
                
            except Exception as grant_error:
                logger.error(f"Error processing grant {i+1}: {grant_error}")
                continue
        
        logger.info(f"Successfully parsed {len(opportunities)} opportunities from JSON for {state_name}")
        return opportunities
        
    except Exception as e:
        logger.error(f"Error parsing Perplexity JSON response for {state_name}: {str(e)}")
        logger.info(f"Falling back to text parsing for {state_name}")
        return fallback_text_parsing(ai_response, state_name, state_code)

def fallback_text_parsing(ai_response, state_name, state_code):
    """Fallback text parsing if JSON parsing fails"""
    opportunities = []
    
    try:
        logger.info(f"Using fallback text parsing for {state_name}")
        
        # Extract URLs from text
        urls = extract_urls_from_text(ai_response)
        logger.info(f"Extracted {len(urls)} URLs from response text")
        
        # Extract grant titles
        grant_titles = extract_grant_titles_from_text(ai_response)
        logger.info(f"Extracted {len(grant_titles)} grant titles from response text")
        
        # Create opportunities from titles and URLs
        for i, title in enumerate(grant_titles[:3]):  # Limit to 3 for fallback
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
            
            # Only add opportunities with valid URLs
            if assigned_url and assigned_url.startswith('http'):
                opportunity = {
                    'id': f"{state_code}_perplexity_{hash(title)}_{datetime.now().strftime('%Y%m%d')}",
                    'title': title,
                    'state': state_name,
                    'amount': amount,
                    'deadline': 'Check website',
                    'url': assigned_url,
                    'tags': ['K-12', 'Education', 'AI-Discovered', 'Text-Parsed'],
                    'found_date': datetime.now().isoformat(),
                    'source': 'perplexity_fallback'
                }
                opportunities.append(opportunity)
                logger.info(f"Fallback parsed: {title[:50]}... - URL: {assigned_url}")
            else:
                logger.warning(f"Skipping fallback grant '{title[:50]}...' - no valid URL")
        
        logger.info(f"Fallback parsing found {len(opportunities)} opportunities for {state_name}")
        return opportunities
        
    except Exception as e:
        logger.error(f"Fallback text parsing also failed for {state_name}: {str(e)}")
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
            
            # Extract professional details
            
            # Extract eligibility information
            eligibility_patterns = [
                r'eligib(?:le|ility)[:\s]*([^\.]{20,200})',
                r'who\s+can\s+apply[:\s]*([^\.]{20,200})',
                r'applicant[s]?\s+must[:\s]*([^\.]{20,200})',
                r'requirements[:\s]*([^\.]{20,200})'
            ]
            
            for pattern in eligibility_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    eligibility = match.group(1).strip()
                    if len(eligibility) > 20:
                        opportunity['eligibility'] = eligibility[:300]
                        break
            
            # Extract description
            description_patterns = [
                r'description[:\s]*([^\.]{30,300})',
                r'program\s+overview[:\s]*([^\.]{30,300})',
                r'purpose[:\s]*([^\.]{30,300})',
                r'summary[:\s]*([^\.]{30,300})'
            ]
            
            for pattern in description_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    description = match.group(1).strip()
                    if len(description) > 30:
                        opportunity['description'] = description[:500]
                        break
            
            # Extract contact information
            contact_patterns = [
                r'contact[:\s]*([^\.]{10,100})',
                r'questions[:\s]*([^\.]{10,100})',
                r'email[:\s]*([^\s]+@[^\s]+)',
                r'phone[:\s]*([0-9\-\(\)\s]{10,20})'
            ]
            
            for pattern in contact_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    contact = match.group(1).strip()
                    if len(contact) > 5:
                        opportunity['contact_info'] = contact[:200]
                        break
            
            # Extract application process
            process_patterns = [
                r'how\s+to\s+apply[:\s]*([^\.]{20,200})',
                r'application\s+process[:\s]*([^\.]{20,200})',
                r'to\s+apply[:\s]*([^\.]{20,200})',
                r'submit[:\s]*([^\.]{20,200})'
            ]
            
            for pattern in process_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    process = match.group(1).strip()
                    if len(process) > 20:
                        opportunity['application_process'] = process[:300]
                        break
            
            # Extract better description/tags from content
            if 'math' in content.lower() or 'mathematics' in content.lower():
                if 'Mathematics' not in opportunity.get('tags', []):
                    opportunity['tags'].append('Mathematics')
            
            if 'stem' in content.lower():
                if 'STEM' not in opportunity.get('tags', []):
                    opportunity['tags'].append('STEM')
            
            # Set source reliability and quality score
            if opportunity.get('source_type') == 'federal':
                opportunity['source_reliability'] = 'high'
                opportunity['quality_score'] = 8.0
            elif opportunity.get('source_type') == 'state':
                opportunity['source_reliability'] = 'high'
                opportunity['quality_score'] = 7.0
            else:
                opportunity['source_reliability'] = 'medium'
                opportunity['quality_score'] = 6.0
            
            # Increase quality score if we found detailed info
            if opportunity.get('eligibility') and opportunity.get('description'):
                opportunity['quality_score'] = min(10.0, opportunity.get('quality_score', 5.0) + 1.5)
                    
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
    
    # Step 1: Use Firecrawl to crawl official sources (with Perplexity fallback)
    opportunities = crawl_official_sources(state_code)
    
    if not opportunities:
        logger.warning(f"Official source crawling found no opportunities for {state_name}")
        logger.info(f"Attempting traditional scraping as final fallback for {state_name}")
        # Fallback to traditional scraping for this state
        opportunities = scrape_opportunities(state_code)
        if opportunities:
            logger.info(f"Traditional scraping found {len(opportunities)} opportunities for {state_name}")
        else:
            logger.warning(f"All discovery methods failed for {state_name}")
            return []
    
    # Step 2: Enhance each opportunity with Firecrawl (if URL available)
    enhanced_opportunities = []
    for opp in opportunities:
        enhanced_opp = enhance_opportunity_with_firecrawl(opp)
        enhanced_opportunities.append(enhanced_opp)
    
    logger.info(f"AI-powered discovery complete for {state_name}: {len(enhanced_opportunities)} opportunities")
    return enhanced_opportunities

def add_verified_opportunities():
    """Add the real opportunities found during research"""
    verified_opportunities = [
        {
            'id': 'CA_golden_state_pathways_2024',
            'title': 'Golden State Pathways Program - STEM Career Pathways',
            'state': 'California',
            'amount': '$470,000,000',
            'deadline': 'Rolling - Check CDE website',
            'url': 'https://www.cde.ca.gov/fg/fo/af/',
            'tags': ['STEM', 'Career Pathways', 'High School', 'K-12'],
            'found_date': datetime.now().isoformat(),
            'eligibility': 'High schools creating career pathways in STEM, education, and health care',
            'description': 'Expand dual enrollment, increase STEM career exposure through job shadowing, hire support staff for college/career planning',
            'contact_info': 'Contact California Department of Education',
            'source_type': 'state',
            'quality_score': 9.0,
            'application_process': 'Visit CDE funding opportunities page for application details',
            'source_reliability': 'high'
        },
        {
            'id': 'FL_computer_science_bonus_2025',
            'title': 'Computer Science Teacher Bonus Grant',
            'state': 'Florida',
            'amount': 'Amount TBD',
            'deadline': 'January 30, 2025',
            'url': 'https://www.fldoe.org/academics/standards/subject-areas/computer-science/funding.stml',
            'tags': ['Computer Science', 'Teacher Bonus', 'K-12', 'STEM'],
            'found_date': datetime.now().isoformat(),
            'eligibility': 'Districts for qualifying computer science teachers teaching identified CS courses',
            'description': 'Provides funding to districts for qualifying computer science teachers',
            'contact_info': 'CompSci@fldoe.org',
            'source_type': 'state',
            'quality_score': 8.5,
            'application_process': 'Upload application documents to ShareFile by deadline',
            'source_reliability': 'high'
        },
        {
            'id': 'NSF_drk12_2024',
            'title': 'NSF Discovery Research PreK-12 (DRK-12)',
            'state': 'Federal',
            'amount': 'Up to $3,000,000',
            'deadline': 'Rolling submissions',
            'url': 'https://www.nsf.gov/funding/opportunities/drk-12-discovery-research-prek-12/nsf23-596/solicitation',
            'tags': ['STEM', 'Research', 'PreK-12', 'Federal'],
            'found_date': datetime.now().isoformat(),
            'eligibility': 'Educational researchers, universities, school districts',
            'description': 'Catalyze research and development enhancing preK-12 STEM learning experiences',
            'contact_info': 'NSF Education and Human Resources Directorate',
            'source_type': 'federal',
            'quality_score': 9.5,
            'application_process': 'Submit via NSF FastLane System or Grants.gov',
            'source_reliability': 'high'
        },
        {
            'id': 'TX_tstem_planning_2025',
            'title': 'T-STEM Planning and Implementation Grant',
            'state': 'Texas',
            'amount': 'Up to $6,000',
            'deadline': 'February 2025 (estimated)',
            'url': 'https://tea.texas.gov/finance-and-grants/grants/grants-administration/grants-awarded/2022-2024-t-stem-planning-and-implementation-grant',
            'tags': ['T-STEM', 'Academy Planning', 'STEM', 'High School'],
            'found_date': datetime.now().isoformat(),
            'eligibility': 'Texas school districts developing new T-STEM Academies',
            'description': 'Develop T-STEM Academies allowing students to earn STEM endorsement and industry certifications',
            'contact_info': 'Texas Education Agency',
            'source_type': 'state',
            'quality_score': 8.0,
            'application_process': 'Check TEA Grant Opportunities portal for current application cycle',
            'source_reliability': 'high'
        },
        {
            'id': 'ED_eir_innovation_2024',
            'title': 'Education Innovation and Research (EIR) Program',
            'state': 'Federal',
            'amount': 'Various levels available',
            'deadline': 'July 2024 (next cycle TBD)',
            'url': 'https://www.ed.gov/grants-and-programs/grants-special-populations/economically-disadvantaged-students/education-innovation-and-research',
            'tags': ['Innovation', 'Research', 'Early-phase', 'Federal'],
            'found_date': datetime.now().isoformat(),
            'eligibility': 'Educational organizations, school districts, nonprofits',
            'description': 'Provides early-phase, mid-phase, and expansion grants for educational innovation',
            'contact_info': 'U.S. Department of Education',
            'source_type': 'federal',
            'quality_score': 9.0,
            'application_process': 'Submit through grants.gov during open application period',
            'source_reliability': 'high'
        },
        {
            'id': 'CA_title3_english_learner_2026',
            'title': 'Title III English Learner Student Program',
            'state': 'California',
            'amount': 'Amount varies by district',
            'deadline': 'June 30, 2025',
            'url': 'https://www.cde.ca.gov/fg/fo/profile.asp?id=6427',
            'tags': ['English Learners', 'Title III', 'K-12', 'Federal'],
            'found_date': datetime.now().isoformat(),
            'eligibility': 'California school districts serving English learner students',
            'description': 'Federal funding to support English learner students in K-12 education',
            'contact_info': 'California Department of Education',
            'source_type': 'federal',
            'quality_score': 7.5,
            'application_process': 'Apply through CDE consolidated application process',
            'source_reliability': 'high'
        }
    ]
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    
    added_count = 0
    for opp in verified_opportunities:
        # Check if already exists
        c.execute('SELECT id FROM opportunities WHERE id = ?', (opp['id'],))
        if not c.fetchone():
            c.execute('''INSERT INTO opportunities 
                        (id, title, state, amount, deadline, url, tags, found_date,
                         eligibility, description, contact_info, source_type, 
                         quality_score, application_process, source_reliability)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (opp['id'], opp['title'], opp['state'], opp['amount'],
                      opp['deadline'], opp['url'], json.dumps(opp['tags']), 
                      opp['found_date'], opp.get('eligibility', ''),
                      opp.get('description', ''), opp.get('contact_info', ''),
                      opp.get('source_type', 'unknown'), opp.get('quality_score', 5.0),
                      opp.get('application_process', ''), opp.get('source_reliability', 'medium')))
            added_count += 1
            logger.info(f"Added verified opportunity: {opp['title']}")
    
    conn.commit()
    conn.close()
    
    logger.info(f"Added {added_count} verified opportunities to database")
    return added_count

def check_all_states():
    """Check all states for new opportunities"""
    logger.info(f"Checking for new opportunities at {datetime.now()}")
    new_opportunities = []
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    
    for state_code in STATE_CONFIGS:
        # Skip if status is not active
        if STATE_CONFIGS[state_code].get('status') != 'active':
            logger.info(f"Skipping {state_code} - status: {STATE_CONFIGS[state_code].get('status')}")
            continue
            
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
                            (id, title, state, amount, deadline, url, tags, found_date,
                             eligibility, description, contact_info, source_type, 
                             quality_score, application_process, source_reliability)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (opp['id'], opp['title'], opp['state'], opp['amount'],
                          opp['deadline'], opp['url'], json.dumps(opp['tags']), 
                          opp['found_date'], opp.get('eligibility', ''),
                          opp.get('description', ''), opp.get('contact_info', ''),
                          opp.get('source_type', 'unknown'), opp.get('quality_score', 5.0),
                          opp.get('application_process', ''), opp.get('source_reliability', 'medium')))
    
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
    
    conn = sqlite3.connect(DATABASE_PATH)
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

# Schedule twice-weekly checks (Tuesdays and Fridays at 9 AM)
if not app.debug:  # Only in production
    scheduler.add_job(check_all_states, 'cron', day_of_week='tue,fri', hour=9, minute=0)
    scheduler.start()

if __name__ == '__main__':
    # For local development
    app.run(debug=True, port=5000)
else:
    # For production, make sure scheduler runs
    if not scheduler.running:
        scheduler.start()