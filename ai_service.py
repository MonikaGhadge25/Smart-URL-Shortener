import os
import httpx
import json
import re
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

CATEGORIES = [
    "Technology", "News", "Shopping", "Social Media",
    "Finance", "Education", "Entertainment", "Health",
    "Travel", "Sports", "Other"
]

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


async def analyze_url(url: str, title: str, description: str) -> dict:
    """
    Uses Google Gemini to categorize a URL and detect if it's suspicious.
    Falls back to keyword-based tagging if API key is missing or call fails.
    """
    if not GEMINI_API_KEY:
        return _keyword_fallback(url, title)

    prompt = f"""Analyze this URL and its metadata and respond ONLY with a valid JSON object.

URL: {url}
Title: {title}
Description: {description}

Respond with ONLY this JSON (no markdown, no explanation):
{{
  "category": "<one of: {', '.join(CATEGORIES)}>",
  "is_suspicious": <true or false>,
  "reason": "<short reason if suspicious, else empty string>"
}}"""

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 200,
                    }
                }
            )
            data = resp.json()

            # Extract text from Gemini response
            text = data["candidates"][0]["content"]["parts"][0]["text"]

            # Strip markdown code blocks if present
            text = re.sub(r"```json|```", "", text).strip()

            result = json.loads(text)

            # Validate category
            if result.get("category") not in CATEGORIES:
                result["category"] = "Other"

            return result

    except Exception as e:
        print(f"Gemini API error: {e}")
        return _keyword_fallback(url, title)


def _keyword_fallback(url: str, title: str) -> dict:
    """
    Simple keyword-based categorization as fallback.
    No API needed — works offline.
    """
    url_lower = url.lower()
    title_lower = title.lower() if title else ""
    combined = url_lower + " " + title_lower

    # Domain-based rules
    domain_map = {
        "youtube.com": "Entertainment",
        "youtu.be": "Entertainment",
        "netflix.com": "Entertainment",
        "spotify.com": "Entertainment",
        "twitch.tv": "Entertainment",
        "twitter.com": "Social Media",
        "x.com": "Social Media",
        "facebook.com": "Social Media",
        "instagram.com": "Social Media",
        "linkedin.com": "Social Media",
        "reddit.com": "Social Media",
        "tiktok.com": "Social Media",
        "amazon.com": "Shopping",
        "flipkart.com": "Shopping",
        "ebay.com": "Shopping",
        "etsy.com": "Shopping",
        "meesho.com": "Shopping",
        "myntra.com": "Shopping",
        "bbc.com": "News",
        "cnn.com": "News",
        "ndtv.com": "News",
        "timesofindia.com": "News",
        "reuters.com": "News",
        "theguardian.com": "News",
        "github.com": "Technology",
        "stackoverflow.com": "Technology",
        "medium.com": "Technology",
        "dev.to": "Technology",
        "techcrunch.com": "Technology",
        "coursera.org": "Education",
        "udemy.com": "Education",
        "khanacademy.org": "Education",
        "wikipedia.org": "Education",
        "edx.org": "Education",
        "booking.com": "Travel",
        "airbnb.com": "Travel",
        "makemytrip.com": "Travel",
        "tripadvisor.com": "Travel",
        "healthline.com": "Health",
        "webmd.com": "Health",
        "mayoclinic.org": "Health",
        "espn.com": "Sports",
        "cricbuzz.com": "Sports",
        "sports.ndtv.com": "Sports",
        "investing.com": "Finance",
        "moneycontrol.com": "Finance",
        "zerodha.com": "Finance",
        "bloomberg.com": "Finance",
    }

    for domain, category in domain_map.items():
        if domain in url_lower:
            return {"category": category, "is_suspicious": False, "reason": ""}

    # Keyword-based rules
    keyword_map = {
        "Technology": ["github", "code", "programming", "software", "tech", "developer", "api", "python", "javascript"],
        "News":       ["news", "breaking", "headlines", "report", "journalist", "press"],
        "Shopping":   ["shop", "buy", "cart", "product", "store", "sale", "discount", "price"],
        "Finance":    ["stock", "invest", "crypto", "bitcoin", "finance", "bank", "loan", "trading"],
        "Education":  ["learn", "course", "tutorial", "study", "education", "university", "college", "lecture"],
        "Health":     ["health", "medical", "doctor", "hospital", "fitness", "diet", "wellness"],
        "Travel":     ["travel", "hotel", "flight", "vacation", "trip", "tour", "holiday"],
        "Sports":     ["sport", "cricket", "football", "tennis", "ipl", "match", "game", "player"],
        "Entertainment": ["movie", "music", "video", "entertainment", "stream", "podcast", "song", "film"],
        "Social Media": ["social", "profile", "follow", "post", "share", "community"],
    }

    for category, keywords in keyword_map.items():
        if any(kw in combined for kw in keywords):
            return {"category": category, "is_suspicious": False, "reason": ""}

    # Basic spam detection
    spam_signals = ["free money", "click here", "winner", "lottery", "prize", "urgent", "verify account", "suspicious"]
    is_suspicious = any(signal in combined for signal in spam_signals)

    return {
        "category": "Other",
        "is_suspicious": is_suspicious,
        "reason": "Suspicious keywords detected" if is_suspicious else ""
    }