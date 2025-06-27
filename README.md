# K-12 Math Funding Monitor

An automated web application that monitors state Department of Education websites for K-12 mathematics funding opportunities and sends email alerts to subscribers.

## Features

- 🔍 **Automated Monitoring**: Scrapes 10+ state DoE websites daily for new funding opportunities
- 📧 **Email Alerts**: Sends personalized notifications based on subscriber preferences
- 🗂️ **Database Storage**: Tracks opportunities and subscribers using SQLite
- 📊 **Real-time Dashboard**: Displays current statistics and recent opportunities
- 🎯 **Smart Filtering**: Focuses on K-12 mathematics and STEM funding
- 🚀 **Production Ready**: Configured for Railway deployment with health checks

## Quick Deploy to Railway

1. **Fork this repository**
2. **Connect to Railway**: Visit [railway.app](https://railway.app) and connect your GitHub
3. **Deploy**: Select this repository and Railway will auto-deploy
4. **Set Environment Variables** in Railway dashboard:
   ```
   SENDER_EMAIL=your_email@gmail.com
   SENDER_PASSWORD=your_app_password
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   ```
5. **Done!** Your app will be live at your Railway URL

## Local Development

### Prerequisites
- Python 3.8+
- pip

### Setup

1. **Clone the repository**:
   ```bash
   git clone <your-repo>
   cd doe-for-kesley
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your email credentials
   ```

4. **Run the application**:
   ```bash
   python app.py
   ```

5. **Visit** `http://localhost:5000`

## Email Configuration

For email notifications to work, you need:

1. **Gmail App Password** (recommended):
   - Enable 2FA on your Gmail account
   - Generate an App Password: https://myaccount.google.com/apppasswords
   - Use the App Password in `SENDER_PASSWORD`

2. **Or use another SMTP provider**:
   - Update `SMTP_SERVER` and `SMTP_PORT` accordingly

## Project Structure

```
doe-for-kesley/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── railway.toml       # Railway deployment config
├── Procfile          # Process configuration
├── templates/        # HTML templates
│   ├── base.html    # Base template
│   └── index.html   # Main page
├── static/          # Static assets
│   ├── css/style.css # Styles
│   └── js/app.js    # JavaScript
└── README.md        # This file
```

## API Endpoints

- `GET /` - Main dashboard page
- `POST /subscribe` - Subscribe to alerts
- `GET /api/opportunities` - Get recent opportunities (JSON)
- `GET /api/stats` - Get current statistics (JSON)
- `GET /health` - Health check endpoint

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SENDER_EMAIL` | Email address for sending alerts | Required |
| `SENDER_PASSWORD` | Email password or app password | Required |
| `SMTP_SERVER` | SMTP server hostname | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP server port | `587` |
| `FLASK_ENV` | Flask environment | `production` |

## Monitored States

Currently monitoring these states for K-12 math funding:
- Texas (TX)
- California (CA) 
- Florida (FL)
- New York (NY)
- Illinois (IL)
- Pennsylvania (PA)
- Ohio (OH)
- Georgia (GA)
- North Carolina (NC)
- Michigan (MI)

## Scheduling

The application automatically checks for new opportunities daily at 9 AM using APScheduler. The scheduler:
- Scrapes all configured state websites
- Filters for K-12 math-related content
- Stores new opportunities in the database
- Sends email alerts to relevant subscribers

## Database

Uses SQLite with two main tables:
- `subscribers`: Email, frequency, states, signup date
- `opportunities`: ID, title, state, amount, deadline, URL, tags, found date

## Security Notes

- Never commit `.env` files to version control
- Use App Passwords for Gmail rather than your main password
- Environment variables are automatically secured in Railway
- CORS is enabled for API endpoints

## Troubleshooting

**Email not working?**
- Check your email credentials in environment variables
- Ensure 2FA is enabled and you're using an App Password for Gmail
- Check Railway logs for error messages

**Scraping not working?**
- Some state websites may have changed their structure
- Check the `STATE_CONFIGS` in `app.py` and update selectors if needed
- View logs to see specific scraping errors

**Database errors?**
- Railway provides persistent storage automatically
- For local development, the SQLite file is created automatically

## Built With

- **Flask** - Web framework
- **BeautifulSoup** - Web scraping
- **APScheduler** - Background task scheduling
- **SQLite** - Database
- **Railway** - Deployment platform

## License

This project is for demonstration purposes as part of Dodo Digital's automation capabilities.

---

**Built by Harrison from Dodo Digital**