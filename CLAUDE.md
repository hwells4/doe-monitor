# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a professional-grade K-12 education funding monitor that automatically discovers grant opportunities from official state Department of Education websites and federal sources. The system uses a sophisticated multi-layered architecture with Firecrawl for reliable content extraction, Perplexity AI as fallback, and traditional web scraping as final fallback.

## Core Architecture

### Triple-Fallback Discovery System
The system uses a cascade approach for maximum reliability:
1. **Primary**: `crawl_official_sources()` → `firecrawl_crawl_source()` (Firecrawl on known official sources)
2. **Fallback**: `discover_opportunities_with_perplexity()` (AI-powered discovery)  
3. **Final**: `scrape_opportunities()` (Traditional BeautifulSoup scraping)

### Database Schema Evolution
The system has two database schemas:
- **Legacy**: Basic fields (id, title, state, amount, deadline, url, tags, found_date)
- **Professional**: Enhanced with (eligibility, description, contact_info, source_type, quality_score, application_process, source_reliability)

The `get_recent_opportunities()` function handles both schemas gracefully with length checks.

### State Configuration System
`STATE_CONFIGS` dictionary contains 17 sources:
- **15 State DoE websites** (TX, CA, FL, NY, IL, PA, OH, GA, NC, MI, VA, CO, OR, AZ, WA)
- **2 Federal sources** (FEDERAL_ED, GRANTS_GOV)
- Each config includes: name, url, CSS selectors, status, source_type, notes

Status types: `'active'`, `'needs_verification'`, `'captcha_protected'`, `'inactive'`

## Development Commands

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (debug mode)
python app.py

# Access at http://localhost:5000
```

### Testing API Endpoints
```bash
# Test full system scrape
curl -X POST http://localhost:5000/api/scrape

# Test specific state (Firecrawl-first approach)
curl -X POST http://localhost:5000/api/scrape/ai/TX

# Get opportunities with professional fields
curl "http://localhost:5000/api/opportunities?limit=5" | python -m json.tool

# Check system health and AI service status
curl http://localhost:5000/health | python -m json.tool

# Check database stats
curl http://localhost:5000/api/stats | python -m json.tool
```

### Database Operations
```bash
# Database auto-initializes on first run via init_db()
# Local: ./funding_monitor.db
# Railway: /data/funding_monitor.db (persistent volume)

# Clear opportunities for fresh test
# No direct command - use Railway logs or manual deletion
```

## Key Architecture Components

### AI Services Integration
- **Firecrawl**: Primary content extraction with `formats=['markdown', 'html']`
- **Perplexity**: Uses PerplexiPy OR OpenAI client as fallback
- **Quality Filtering**: `is_high_quality_opportunity()` rejects PDFs, archives, summaries

### Content Enhancement Pipeline
1. **Discovery**: Find grant URLs from official pages
2. **Extraction**: Extract title, amount, deadline from surrounding text
3. **Enhancement**: `enhance_opportunity_with_firecrawl()` extracts professional details
4. **Quality Scoring**: Rates 1-10 based on completeness and source reliability

### Automated Scheduling
- **Schedule**: Twice weekly (Tuesdays & Fridays at 9 AM)
- **Function**: `check_all_states()` iterates through all STATE_CONFIGS
- **Production Only**: `if not app.debug` prevents scheduler in development

## Environment Variables

### Required for Production
```bash
PERPLEXITY_API_KEY=pplx-xxx         # Perplexity AI API access
FIRECRAWL_API_KEY=fc-xxx            # Firecrawl API for content extraction  
SENDER_EMAIL=email@domain.com       # Gmail for notifications
SENDER_PASSWORD=app_password        # Gmail app password (not regular password)
```

### Optional
```bash
SMTP_SERVER=smtp.gmail.com          # Default provided
SMTP_PORT=587                       # Default provided
DATABASE_DIR=/data                  # Railway persistent volume path
```

## Professional Data Fields

The enhanced database schema includes professional fields extracted by `enhance_opportunity_with_firecrawl()`:

- **eligibility**: Who can apply, requirements (300 char limit)
- **description**: Program overview, purpose (500 char limit)  
- **contact_info**: Email, phone, program contacts (200 char limit)
- **application_process**: How to apply instructions (300 char limit)
- **quality_score**: 1.0-10.0 rating (Federal: 8.0+, State: 7.0+, Traditional: 6.0+)
- **source_reliability**: 'high', 'medium', 'low'
- **source_type**: 'federal', 'state', 'direct_crawl', 'unknown'

## Critical Architecture Patterns

### Error Handling Philosophy
- **Graceful Degradation**: Each layer falls back to next method if previous fails
- **Never Fail Completely**: Always return empty list rather than crash
- **Comprehensive Logging**: Every failure logged with context for debugging

### URL Cleaning Pipeline
URLs go through `clean_extracted_url()` which:
1. Removes markdown artifacts `[1]`, `[2]` 
2. Strips trailing punctuation and brackets
3. Validates format with regex `https?://[^\s<>"]+\.[a-zA-Z]{2,}`

### Railway Deployment Specifics
- **Persistent Volume**: `/data` mounted for SQLite database persistence
- **Health Checks**: `/health` endpoint with 300s timeout
- **Auto-restart**: `on_failure` with 3 max retries
- **Environment Detection**: `os.environ.get('RAILWAY_ENVIRONMENT')` for production logic

## Quality Control System

### Content Filtering
`is_high_quality_opportunity()` rejects:
- **Red Flag Terms**: budget, summary, legislative, archive, report, presentation
- **Bad URLs**: .pdf, /archive, /budget, /reports, /minutes
- **Missing Actionable Terms**: Must contain application, grant, funding, rfp, etc.

### Source Reliability Scoring
- **Federal Sources**: Highest quality (8.0+ score, 'high' reliability)
- **State DoE Sources**: High quality (7.0+ score, 'high' reliability)  
- **Traditional Scraping**: Medium quality (6.0+ score, 'medium' reliability)
- **Enhanced Opportunities**: +1.5 bonus if both eligibility and description found

## Frontend Integration

### AJAX Loading Pattern
- **Initial Load**: `loadOpportunities(true)` resets pagination
- **State Filter**: `filterByState()` triggers fresh load with state parameter
- **Pagination**: `loadMoreOpportunities()` appends to existing results
- **Real-time Updates**: No auto-refresh, manual trigger only

### Professional Display Fields
Frontend receives and can display all professional fields:
```javascript
// Available in opportunity objects
opp.eligibility, opp.description, opp.contact_info
opp.application_process, opp.quality_score, opp.source_reliability
```

## Troubleshooting Common Issues

### "Only Oregon Opportunities Found"
- Check other state configs have correct `'status': 'active'`
- Verify Firecrawl extraction patterns work for each state's website structure
- Review logs for specific state failures during `check_all_states()`

### "No Opportunities Found"
- Ensure AI services are configured: check `/health` endpoint
- Verify STATE_CONFIGS URLs are accessible and haven't changed
- Check if quality filters are too restrictive in `is_high_quality_opportunity()`

### "Database Persistence Issues"
- Railway: Ensure `/data` volume is properly mounted via `railway.toml`
- Local: Check write permissions in project directory
- Verify `DATABASE_PATH` logging shows correct location

### "Email Notifications Not Working"
- Use Gmail App Password, not regular password
- Verify SMTP configuration in EMAIL_CONFIG
- Check email formatting in `send_alerts()` function

## Production Deployment

The system is designed for Railway deployment with:
- **Auto-deployment** from GitHub main branch
- **Health monitoring** via `/health` endpoint  
- **Persistent database** via mounted volume
- **Environment-based configuration** for development vs production
- **Automatic scheduling** only in production environment

## Architecture Philosophy

This system prioritizes **reliability over speed** and **quality over quantity**. The triple-fallback architecture ensures something always works, while the quality filtering ensures results are professionally useful rather than academically interesting. The professional data fields transform it from a prototype into a tool that K-12 administrators can actually use to find and apply for funding.