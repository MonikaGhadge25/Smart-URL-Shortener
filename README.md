# 🔗 LinkAI — Smart URL Shortener

An AI-powered URL shortener that auto-categorizes links and detects spam using Claude AI.

## Features
- 🔗 Shorten any URL with a unique short code
- 🏷️ **AI Auto-tagging** — Claude categorizes each URL (Tech, News, Shopping, etc.)
- 🚨 **Spam Detection** — AI scans for phishing and suspicious content
- ⚠️ Warning page before redirecting to flagged URLs
- 📊 Dashboard with click analytics and tag breakdown

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Add your Anthropic API Key
Open `ai_service.py` and add your API key to the headers:
```python
HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": "YOUR_ANTHROPIC_API_KEY",   # ← Add this line
    "anthropic-version": "2023-06-01"
}
```

### 3. Run the server
```bash
uvicorn main:app --reload
```

### 4. Open in browser
Visit: http://localhost:8000

## Project Structure
```
smart-url-shortener/
├── main.py          # FastAPI routes
├── models.py        # SQLAlchemy DB models
├── database.py      # DB connection setup
├── ai_service.py    # Claude API — tagging & spam detection
├── scraper.py       # Fetch page title & metadata
├── utils.py         # Short code generator
├── templates/
│   ├── index.html   # Home page
│   ├── dashboard.html
│   └── warning.html
└── requirements.txt
```

## Tech Stack
- **FastAPI** — Python web framework
- **SQLite + SQLAlchemy** — Database
- **Claude API** — AI tagging & spam detection
- **httpx + BeautifulSoup** — Web scraping
- **Jinja2** — HTML templating

