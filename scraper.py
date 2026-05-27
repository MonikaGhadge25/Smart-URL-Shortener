# cat > /home/claude/smart-url-shortener/scraper.py << 'EOF'
import httpx
from bs4 import BeautifulSoup

async def scrape_metadata(url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0 SmartURLBot/1.0"}
            response = await client.get(url, headers=headers)
            soup = BeautifulSoup(response.text, "html.parser")
            title = ""
            if soup.title:
                title = soup.title.string or ""
            desc = ""
            meta = soup.find("meta", attrs={"name": "description"})
            if meta:
                desc = meta.get("content", "")
            return {"title": title.strip()[:255], "description": desc.strip()[:500]}
    except Exception:
        return {"title": "", "description": ""}
# EOF

