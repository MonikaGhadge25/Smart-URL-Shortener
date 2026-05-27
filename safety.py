# cat > /home/claude/smart-url-shortener/safety.py << 'EOF'
import os
import httpx
from dotenv import load_dotenv

load_dotenv()
SAFE_BROWSING_KEY = os.getenv("GOOGLE_SAFE_BROWSING_API_KEY", "")

async def check_google_safe_browsing(url: str) -> dict:
    if not SAFE_BROWSING_KEY:
        return {"is_safe": True, "threats": []}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={SAFE_BROWSING_KEY}",
                json={
                    "client": {"clientId": "smart-url-shortener", "clientVersion": "1.0"},
                    "threatInfo": {
                        "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
                        "platformTypes": ["ANY_PLATFORM"],
                        "threatEntryTypes": ["URL"],
                        "threatEntries": [{"url": url}]
                    }
                }
            )
            data = resp.json()
            threats = data.get("matches", [])
            return {"is_safe": len(threats) == 0, "threats": [t.get("threatType") for t in threats]}
    except Exception:
        return {"is_safe": True, "threats": []}
# EOF

# echo "Service files written"
# Output

# Service files written