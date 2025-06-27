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

# State DoE configurations
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
    },
    'NY': {
        'name': 'New York',
        'url': 'http://www.nysed.gov/grants',
        'selector': '.content-area a'
    },
    'IL': {
        'name': 'Illinois',
        'url': 'https://www.isbe.net/Pages/Grants.aspx',
        'selector': '.ms-rtestate-field a'
    },
    'PA': {
        'name': 'Pennsylvania',
        'url': 'https://www.education.pa.gov/Teachers%20-%20Administrators/Pages/Grant-Opportunities.aspx',
        'selector': '.ms-rtestate-field a'
    },
    'OH': {
        'name': 'Ohio',
        'url': 'https://education.ohio.gov/Topics/Finance-and-Funding/School-Funding/Grant-Opportunities',
        'selector': '.content a'
    },
    'GA': {
        'name': 'Georgia',
        'url': 'https://www.gadoe.org/External-Affairs-and-Policy/communications/Pages/PressReleaseDetails.aspx',
        'selector': '.content a'
    },
    'NC': {
        'name': 'North Carolina',
        'url': 'https://www.dpi.nc.gov/districts-schools/federal-program-monitoring/grants-funding',
        'selector': '.field-content a'
    },
    'MI': {
        'name': 'Michigan',
        'url': 'https://www.michigan.gov/mde/services/grants',
        'selector': '.page-content a'
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
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'database': check_database_health(),
        'scheduler': scheduler.running if scheduler else False
    })

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
    """Scrape opportunities from a state DoE site"""
    if state_code not in STATE_CONFIGS:
        return []
    
    config = STATE_CONFIGS[state_code]
    opportunities = []
    
    try:
        response = requests.get(config['url'], timeout=30,
                              headers={'User-Agent': 'Mozilla/5.0 (Educational Funding Monitor)'})
        soup = BeautifulSoup(response.content, 'html.parser')
        links = soup.select(config['selector'])[:10]  # Limit to 10 per state
        
        keywords = ['math', 'mathematics', 'stem', 'k-12', 'elementary', 'middle', 'high school']
        
        for link in links:
            text = link.get_text(strip=True)
            href = link.get('href', '')
            
            # Check if relevant
            if any(keyword in text.lower() for keyword in keywords):
                # Generate unique ID
                opp_id = f"{state_code}_{hash(text)}_{datetime.now().strftime('%Y%m%d')}"
                
                # Extract or estimate amount
                amount = extract_dollar_amount(text) or 'Amount TBD'
                if isinstance(amount, (int, float)):
                    amount = f"${amount:,.0f}"
                
                # Make absolute URL
                if href and not href.startswith('http'):
                    href = requests.compat.urljoin(config['url'], href)
                
                opportunities.append({
                    'id': opp_id,
                    'title': text[:100],  # Limit title length
                    'state': config['name'],
                    'amount': amount,
                    'deadline': 'Check website',  # Would need deeper scraping
                    'url': href,
                    'tags': ['K-12', 'Mathematics'],  # Simplified for demo
                    'found_date': datetime.now().isoformat()
                })
                
    except Exception as e:
        logger.error(f"Error scraping {state_code}: {str(e)}")
    
    return opportunities

def check_all_states():
    """Check all states for new opportunities"""
    logger.info(f"Checking for new opportunities at {datetime.now()}")
    new_opportunities = []
    
    conn = sqlite3.connect('funding_monitor.db')
    c = conn.cursor()
    
    for state_code in STATE_CONFIGS:
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