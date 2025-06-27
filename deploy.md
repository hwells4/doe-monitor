# Deployment Instructions

## Quick Railway Deployment

1. **Push to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Initial commit - K-12 Math Funding Monitor"
   git branch -M main
   git remote add origin https://github.com/yourusername/doe-funding-monitor.git
   git push -u origin main
   ```

2. **Deploy to Railway**:
   - Go to [railway.app](https://railway.app)
   - Click "Start a New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository
   - Railway will automatically detect Flask and deploy

3. **Set Environment Variables** in Railway dashboard:
   ```
   SENDER_EMAIL=your_email@gmail.com
   SENDER_PASSWORD=your_gmail_app_password
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   ```

4. **Get Gmail App Password**:
   - Enable 2-Factor Authentication on Gmail
   - Go to Google Account settings > Security > App passwords
   - Generate password for "Mail"
   - Use this 16-character password in `SENDER_PASSWORD`

## Alternative: Deploy to Vercel (Serverless)

Note: Vercel doesn't support background jobs, so the automated scraping won't work. Better to use Railway.

## Alternative: Deploy to Replit

1. Upload files to Replit
2. Install dependencies: `pip install -r requirements.txt`
3. Set secrets in Replit for email config
4. Run with `python app.py`

## Testing the Deployment

Once deployed, test these endpoints:
- `https://your-app.railway.app/` - Main page
- `https://your-app.railway.app/health` - Health check
- `https://your-app.railway.app/api/stats` - API test

## Setting up for Kesley

1. Deploy the app
2. Send Kesley the URL
3. She can subscribe with her email
4. Add her states of interest
5. She'll start receiving daily alerts

The automation runs daily at 9 AM and will find relevant funding opportunities without any manual work from her.