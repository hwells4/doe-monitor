# K-12 Math Funding Monitor - Development Log

## Project Overview
Built a complete AI-powered web application that monitors state Department of Education websites for K-12 mathematics funding opportunities and sends automated email alerts to subscribers.

## What Was Built

### Core Application
- **Flask Backend**: Complete REST API with subscription handling, opportunity tracking, and email notifications
- **Responsive Frontend**: HTML/CSS/JS interface with AJAX form submission and real-time data display
- **SQLite Database**: Stores subscribers and opportunities with proper schema
- **Railway Deployment**: Production-ready deployment with health checks and monitoring

### AI-Powered Discovery System
- **Perplexity Integration**: Uses PerplexiPy (v1.3.1) for intelligent opportunity discovery
- **Firecrawl Integration**: Uses firecrawl-py for bypassing captchas and content extraction
- **Hybrid Approach**: AI discovery + content enhancement for maximum accuracy
- **Fallback Logic**: Traditional web scraping if AI services fail

### Key Features Implemented
- ✅ Automated daily monitoring at 9 AM
- ✅ Email subscription management with frequency preferences  
- ✅ State-specific filtering (10 states supported)
- ✅ Real-time opportunity discovery and enhancement
- ✅ REST API endpoints for manual triggering and testing
- ✅ Health monitoring and service status reporting
- ✅ Environment variable configuration for security

## Technical Architecture

### Dependencies Added
```
Flask==2.3.3
Flask-CORS==4.0.0
requests==2.31.0
beautifulsoup4==4.12.2
APScheduler==3.10.4
gunicorn==21.2.0
python-dotenv==1.0.0
lxml==4.9.3
openai>=1.40.0
firecrawl-py==0.0.16
PerplexiPy==1.3.1
```

### Environment Variables Required
```
PERPLEXITY_API_KEY=pplx-xxx
FIRECRAWL_API_KEY=fc-xxx  
SENDER_EMAIL=harrison@dododigital.ai
SENDER_PASSWORD=[gmail app password]
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
```

### API Endpoints
- `GET /` - Main dashboard page
- `POST /subscribe` - Subscribe to alerts
- `GET /api/opportunities` - Get recent opportunities (JSON)
- `GET /api/stats` - Get current statistics (JSON)
- `GET /health` - Health check endpoint
- `POST /api/scrape` - Manually trigger full scraping
- `POST /api/scrape/ai/{state}` - Test AI scraping for specific state

## Current Status: MOSTLY WORKING ✅

### ✅ What's Working
- Flask application deployed and running on Railway
- AI services (Perplexity + Firecrawl) properly initialized
- Database storing opportunities (50+ found)
- Basic opportunity discovery across states
- Health checks and monitoring
- Frontend displaying opportunities
- **FIXED: URL parsing and validation system**
- **FIXED: Clean URL extraction from Perplexity responses**

### ✅ **Recent Critical Fixes**

#### 1. **URL Parsing FIXED** ✅
- ✅ Added `clean_extracted_url()` function to properly clean URLs
- ✅ Removes markdown artifacts like `[1]`, `[2]` from URLs  
- ✅ Added `extract_urls_from_text()` with multiple URL patterns
- ✅ Improved URL validation with proper regex checks
- ✅ Test shows problematic URLs now cleaned: `https://tealprod.tea.state.tx.us/GrantOpportunities/forms/GrantProgramSearch.aspx)[1].` → `https://tealprod.tea.state.tx.us/GrantOpportunities/forms/GrantProgramSearch.aspx`
- ✅ Enhanced Perplexity prompt for structured output format

### ❌ **Remaining Issues**

#### 2. **Data Quality Improvements Needed**
- Opportunity titles sometimes truncated (need better parsing)
- Missing proper funding amounts (mostly "Amount TBD")
- Deadline information not being extracted consistently
- Firecrawl enhancement could be more effective

#### 3. **State Filtering** (Status: LIKELY FIXED)
- Previous issue: All opportunities showing as "Michigan"
- Root cause: Likely old database data before fixes
- Fix: State assignment logic is correct in current code
- Need to test with fresh database to confirm fix

#### 4. **Missing Email Functionality**
- Email notifications not tested/working
- Need Gmail app password configuration
- Welcome emails and opportunity alerts not verified

## Immediate Next Steps

### Priority 1: Test Full System ✅
- ✅ URL parsing fixes implemented and tested
- ⏳ Test live scraping to verify all fixes work
- ⏳ Clear old database data and test fresh scraping
- ⏳ Verify state distribution works correctly

### Priority 2: Improve Data Quality  
- Fix opportunity title extraction from Perplexity responses
- Enhance Firecrawl integration to extract better amounts/deadlines
- Improve content parsing for structured data
- Add data validation and cleanup

### Priority 3: Fix State Distribution
- Debug why all opportunities showing as Michigan
- Ensure proper state assignment in AI scraping
- Test individual state endpoints work correctly
- Verify state filtering in frontend

### Priority 4: Complete Email System
- Add Gmail app password to environment
- Test welcome email functionality
- Test opportunity alert emails
- Verify subscription workflow end-to-end

## Next Steps
1. **Debug and fix URL parsing in `parse_perplexity_response()`**
2. **Fix state assignment logic in `ai_powered_scrape_opportunities()`**
3. **Improve Firecrawl enhancement in `enhance_opportunity_with_firecrawl()`**
4. **Test and validate all opportunity links work**
5. **Complete email notification system setup**
6. **Test full user workflow from subscription to alert**

## Deployment Info
- **Production URL**: https://web-production-f2b68.up.railway.app
- **GitHub Repo**: https://github.com/hwells4/doe-monitor
- **Railway Project**: Connected with auto-deploy from main branch
- **Database**: SQLite with persistent storage on Railway

## Files Created/Modified
- `app.py` - Main Flask application (800+ lines)
- `requirements.txt` - Python dependencies
- `templates/` - HTML templates with Jinja2
- `static/` - CSS and JavaScript files
- `railway.toml` - Railway deployment config
- `Procfile` - Process configuration
- `.env.example` - Environment variable template
- `.gitignore` - Git ignore patterns

The core infrastructure is solid but data quality and URL validity issues need immediate attention before this can be considered production-ready for Kesley.