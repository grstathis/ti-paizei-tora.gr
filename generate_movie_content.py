"""
Generate unique movie landing page content using Gemini API.
Processes ALL movies from movies.json, outputs JSON + HTML to generated_content/.
Uses source-based caching to skip unchanged movies on re-runs.
Includes showtimes from cinemas.json when available.
"""

import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "generated_content")

os.makedirs(OUTPUT_DIR, exist_ok=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or open(
    os.path.join(BASE_DIR, "gemini_api"), "r"
).read().strip()

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def normalize(text):
    if not text:
        return ""
    text = text.lower().strip()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )
    return text


# --- Data Loading ---


def load_all_data():
    """Load movies, flix ratings, lifo ratings, and cinemas into indexed structures."""
    movies_path = os.path.join(BASE_DIR, "movies.json")
    with open(movies_path, encoding="utf-8") as f:
        movies_raw = json.load(f)

    # Flatten: each group is a list with one movie dict
    movies = []
    for group in movies_raw:
        if group and isinstance(group, list) and len(group) > 0:
            movies.append(group[0])

    # Load cinemas data (parallel arrays with movies)
    cinemas_path = os.path.join(BASE_DIR, "cinemas.json")
    cinemas_raw = []
    if os.path.exists(cinemas_path):
        with open(cinemas_path, encoding="utf-8") as f:
            cinemas_raw = json.load(f)

    # Build flix index keyed by normalized title
    flix_index = {}
    flix_path = os.path.join(BASE_DIR, "flix_ratings.json")
    if os.path.exists(flix_path):
        with open(flix_path, encoding="utf-8") as f:
            for item in json.load(f):
                key = normalize(item.get("title", ""))
                if key:
                    flix_index[key] = {"url": item.get("url"), "rating": item.get("rating")}

    # Build lifo index keyed by normalized title
    lifo_index = {}
    lifo_path = os.path.join(BASE_DIR, "lifo_ratings.json")
    if os.path.exists(lifo_path):
        with open(lifo_path, encoding="utf-8") as f:
            for item in json.load(f):
                key = normalize(item.get("title", ""))
                if key:
                    lifo_index[key] = {"url": item.get("url"), "rating": item.get("rating")}

    return movies, cinemas_raw, flix_index, lifo_index


def lookup_flix(movie_db, flix_index):
    """Find flix URL and rating for a movie."""
    for title_field in ("greek_title", "original_title"):
        key = normalize(movie_db.get(title_field, ""))
        if key and key in flix_index:
            entry = flix_index[key]
            return entry.get("url"), entry.get("rating")
    return None, None


def lookup_lifo(movie_db, lifo_index):
    """Find lifo URL and rating for a movie."""
    for title_field in ("greek_title", "original_title"):
        key = normalize(movie_db.get(title_field, ""))
        if key and key in lifo_index:
            entry = lifo_index[key]
            return entry.get("url"), entry.get("rating")
    return None, None


# --- Cache Logic ---


def should_regenerate(slug, movie_db, flix_index, lifo_index, force=False):
    """Check if we have new sources that weren't used in the last generation."""
    if force:
        return True

    json_path = os.path.join(OUTPUT_DIR, f"{slug}.json")
    if not os.path.exists(json_path):
        return True

    try:
        with open(json_path, encoding="utf-8") as f:
            existing = json.load(f)
    except (json.JSONDecodeError, OSError):
        return True

    stored_sources = existing.get("sources", {})

    # Check what sources are currently available
    flix_url, _ = lookup_flix(movie_db, flix_index)
    lifo_url, _ = lookup_lifo(movie_db, lifo_index)

    # If a source is now available but wasn't used before → regenerate
    if flix_url and not stored_sources.get("flix_url"):
        return True
    if lifo_url and not stored_sources.get("lifo_url"):
        return True
    if movie_db.get("athinorama_link") and not stored_sources.get("athinorama_url"):
        return True
    if movie_db.get("imdb_link") and not stored_sources.get("imdb_url"):
        return True

    return False


# --- Showtime Parsing ---


def parse_showtime(showtime_str):
    """Parse showtime string like 'Κυριακή 07 Δεκ. 16:00' to extract date and time."""
    match = re.search(
        r"(\d{1,2})\s+([Α-Ωα-ωάέίόήύώΆΈΉΊΌΎΏϊΐϋΰ\.]+)\s+(\d{2}):(\d{2})",
        showtime_str,
    )
    if not match:
        return None

    day = match.group(1).zfill(2)
    month_str = match.group(2).replace(".", "").strip()
    hour = match.group(3)
    minute = match.group(4)

    greek_months = {
        "Ιαν": "01", "Φεβ": "02", "Μαρ": "03", "Απρ": "04",
        "Μαΐ": "05", "Μαϊ": "05", "Ιουν": "06", "Ιουλ": "07",
        "Αυγ": "08", "Σεπ": "09", "Οκτ": "10", "Νοε": "11", "Δεκ": "12",
    }
    month = greek_months.get(month_str, "01")
    current_year = datetime.now(ZoneInfo("Europe/Athens")).year

    return {
        "date": f"{current_year}-{month}-{day}",
        "time": f"{hour}-{minute}",
        "hour": int(hour),
        "minute": int(minute),
        "day": int(day),
        "month": int(month),
        "year": current_year,
        "full": showtime_str,
    }


def is_future_showtime(parsed_showtime):
    """Check if a showtime is in the future (with 15-min grace period)."""
    if not parsed_showtime:
        return False

    now = datetime.now(ZoneInfo("Europe/Athens"))
    today_date = now.date()
    showtime_date = datetime(
        parsed_showtime["year"], parsed_showtime["month"], parsed_showtime["day"]
    ).date()

    if showtime_date < today_date:
        return False
    if showtime_date == today_date:
        showtime_mins = parsed_showtime["hour"] * 60 + parsed_showtime["minute"]
        now_mins = now.hour * 60 + now.minute
        if showtime_mins < (now_mins - 15):
            return False
    return True


def get_cinema_screenings(cinema_list):
    """Extract valid future showtimes from a cinema list for one movie."""
    cinema_screenings = []

    for cinema in cinema_list:
        if not cinema.get("region") or not cinema.get("cinema"):
            continue
        timetable = cinema.get("timetable")
        if not timetable:
            continue

        valid_showtimes = []
        for showtime_list in timetable:
            if not showtime_list:
                continue
            for showtime in showtime_list:
                if not showtime or not showtime.strip():
                    continue
                parsed = parse_showtime(showtime)
                if parsed and is_future_showtime(parsed):
                    valid_showtimes.append(parsed)

        if valid_showtimes:
            valid_showtimes.sort(key=lambda x: (x["date"], x["time"]))
            cinema_screenings.append({"cinema": cinema, "showtimes": valid_showtimes})

    return cinema_screenings


GREEK_TO_LATIN = {
    "α": "a", "ά": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "έ": "e",
    "ζ": "z", "η": "i", "ή": "i", "θ": "th", "ι": "i", "ί": "i", "ϊ": "i",
    "ΐ": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x", "ο": "o",
    "ό": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "y",
    "ύ": "y", "ϋ": "y", "ΰ": "y", "φ": "f", "χ": "x", "ψ": "ps", "ω": "o", "ώ": "o",
    "Α": "a", "Ά": "a", "Β": "v", "Γ": "g", "Δ": "d", "Ε": "e", "Έ": "e",
    "Ζ": "z", "Η": "i", "Ή": "i", "Θ": "th", "Ι": "i", "Ί": "i", "Ϊ": "i",
    "Κ": "k", "Λ": "l", "Μ": "m", "Ν": "n", "Ξ": "x", "Ο": "o", "Ό": "o",
    "Π": "p", "Ρ": "r", "Σ": "s", "Τ": "t", "Υ": "y", "Ύ": "y", "Ϋ": "y",
    "Φ": "f", "Χ": "x", "Ψ": "ps", "Ω": "o", "Ώ": "o",
}


def slugify_cinema(text):
    """Slugify cinema names with Greek transliteration (matches athinorama_cinema_info.py)."""
    text = "".join(GREEK_TO_LATIN.get(ch, ch) for ch in text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def build_showtimes_html(cinema_screenings, movie_title_display, movie_data=None):
    """Build the showtimes section HTML, CSS, JS, and ScreeningEvent schema."""
    if not cinema_screenings:
        return "", "", "", ""

    # Build cinema sections
    cinema_sections_html = ""
    for cinema_group in cinema_screenings:
        cinema = cinema_group["cinema"]
        cinema_slug = slugify_cinema(cinema.get("cinema", ""))
        showtimes = cinema_group["showtimes"]

        cinema_name = cinema.get("cinema", "")
        cinema_region = cinema.get("region", "")
        cinema_addr = cinema.get("address", "")
        cinema_website = cinema.get("website", "")

        website_link = ""
        if cinema_website:
            website_link = f' - <a href="{cinema_website}" target="_blank" style="color: #667eea; text-decoration: underline;">Ιστοσελίδα</a>'

        cinema_sections_html += f'''
      <div class="cinema-section" data-cinema="{cinema_slug}">
        <h3 style="color: #667eea; margin: 20px 0 12px 0; padding-bottom: 10px; border-bottom: 2px solid #f0f0f0;">
          {cinema_name} - {cinema_region}{website_link}
        </h3>
'''
        for showtime in showtimes:
            showtime_id = f"{cinema_slug}-{showtime['date']}-{showtime['time'].replace('-', '')}"
            time_formatted = showtime["time"].replace("-", ":")
            date_formatted = showtime["full"]

            rooms_html = ""
            if cinema.get("rooms"):
                rooms_list = [r.get("room", "") for r in cinema["rooms"] if r.get("room")]
                if rooms_list:
                    rooms_html = f'<div style="color: #666; font-size: 14px;">Αίθουσα: {", ".join(rooms_list)}</div>'

            cinema_sections_html += f'''        <div class="showtime-card" id="{showtime_id}" data-cinema="{cinema_name}" data-date="{showtime['date']}" data-time="{time_formatted}">
          <div class="time" style="font-size: 16px; font-weight: bold; color: #333; margin-bottom: 4px;">{date_formatted}</div>
          <div style="color: #666; font-size: 14px; margin-bottom: 4px;">{cinema_addr}</div>
          {rooms_html}
          <div style="margin-top: 10px;">
            <button class="share-btn" data-showtime-id="{showtime_id}" style="padding: 6px 14px; background: #667eea; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500;">Κοινοποίηση</button>
          </div>
        </div>
'''
        cinema_sections_html += "      </div>\n"

    section_html = f"""    <div class="content-card showtimes-container">
      <h2>Πού παίζει;</h2>
{cinema_sections_html}    </div>"""

    section_css = """
    .showtime-card {
      padding: 14px;
      margin: 10px 0;
      border-radius: 8px;
      background: #f9f9f9;
      border: 2px solid transparent;
      transition: all 0.3s ease;
    }
    .showtime-card.featured {
      border-color: #667eea;
      background: linear-gradient(to right, #f0f4ff, #ffffff);
      box-shadow: 0 4px 20px rgba(102, 126, 234, 0.25);
    }
    .show-all-btn {
      width: 100%;
      padding: 14px;
      background: #f0f4ff;
      border: 2px dashed #667eea;
      border-radius: 8px;
      color: #667eea;
      font-size: 15px;
      font-weight: 600;
      cursor: pointer;
      margin-top: 16px;
      transition: all 0.3s;
    }
    .show-all-btn:hover { background: #667eea; color: white; border-style: solid; }
    .toast {
      position: fixed; bottom: 20px; left: 50%;
      transform: translateX(-50%) translateY(100px);
      background: #28a745; color: white; padding: 12px 24px;
      border-radius: 8px; opacity: 0; transition: all 0.3s ease; z-index: 1000;
    }
    .toast.show { transform: translateX(-50%) translateY(0); opacity: 1; }"""

    # Escape the movie title for JS
    js_title = movie_title_display.replace("'", "\\'").replace('"', '\\"')
    section_js = f"""
  <script>
    window.addEventListener('DOMContentLoaded', () => {{
      const urlParams = new URLSearchParams(window.location.search);
      const showtimeId = urlParams.get('showtime');
      if (showtimeId) {{
        const targetCard = document.getElementById(showtimeId);
        if (targetCard) {{
          document.querySelectorAll('.showtime-card').forEach(card => {{
            if (card.id !== showtimeId) card.style.display = 'none';
          }});
          document.querySelectorAll('.cinema-section').forEach(section => {{
            if (!section.contains(targetCard)) section.style.display = 'none';
          }});
          targetCard.classList.add('featured');
          const showAllBtn = document.createElement('button');
          showAllBtn.className = 'show-all-btn';
          showAllBtn.textContent = 'Δες όλες τις προβολές';
          showAllBtn.onclick = () => {{ window.location.href = window.location.pathname; }};
          targetCard.parentElement.insertBefore(showAllBtn, targetCard.nextSibling);
        }}
      }} else {{
        document.querySelectorAll('.cinema-section').forEach(s => s.style.display = 'none');
        const expandBtn = document.createElement('button');
        expandBtn.className = 'show-all-btn';
        expandBtn.style.cssText = 'display:block;margin:16px auto;padding:14px 28px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;border:none;border-radius:10px;font-size:16px;font-weight:600;cursor:pointer;box-shadow:0 4px 12px rgba(102,126,234,0.3);';
        expandBtn.textContent = 'Δες Όλες τις Προβολές';
        expandBtn.onclick = () => {{
          document.querySelectorAll('.cinema-section').forEach(s => s.style.display = 'block');
          expandBtn.style.display = 'none';
        }};
        const heading = document.querySelector('.showtimes-container h2');
        if (heading) heading.after(expandBtn);
      }}
    }});
    document.querySelectorAll('.share-btn').forEach(btn => {{
      btn.addEventListener('click', async (e) => {{
        const id = e.target.dataset.showtimeId;
        const url = `${{window.location.origin}}${{window.location.pathname}}?showtime=${{id}}`;
        const card = document.getElementById(id);
        const cinema = card.dataset.cinema;
        const time = card.querySelector('.time').textContent;
        try {{
          if (navigator.share) {{
            await navigator.share({{ title: '{js_title} - ' + cinema, text: 'Θες να πάμε; ' + time, url }});
          }} else {{
            await navigator.clipboard.writeText(url);
            showToast('Ο σύνδεσμος αντιγράφηκε!');
          }}
        }} catch (err) {{}}
      }});
    }});
    function showToast(msg) {{
      const t = document.createElement('div'); t.className = 'toast'; t.textContent = msg;
      document.body.appendChild(t);
      setTimeout(() => t.classList.add('show'), 100);
      setTimeout(() => {{ t.classList.remove('show'); setTimeout(() => t.remove(), 300); }}, 2000);
    }}
  </script>"""

    schema_tag = _build_screening_schema(cinema_screenings, movie_data)

    return section_html, section_css, section_js, schema_tag


def _build_screening_schema(cinema_screenings, movie_data):
    """Build Movie + ScreeningEvent JSON-LD schema."""
    if not cinema_screenings or not movie_data:
        return ""

    movie = movie_data.get("movie", {})
    omdb = movie_data.get("omdb", {})

    title_gr = movie.get("title_gr", "")
    poster = omdb.get("poster", "")
    plot = omdb.get("plot", "")
    year = movie.get("year", "")
    runtime = omdb.get("runtime", "")
    imdb_link = omdb.get("imdb_link", "")

    # Build ScreeningEvents
    screening_events = []
    for cinema_group in cinema_screenings:
        cinema = cinema_group["cinema"]
        cinema_slug = slugify_cinema(cinema.get("cinema", ""))

        for showtime in cinema_group["showtimes"]:
            showtime_id = f"{cinema_slug}-{showtime['date']}-{showtime['time'].replace('-', '')}"
            event = {
                "@type": "ScreeningEvent",
                "@id": showtime_id,
                "name": f"{title_gr} στο {cinema.get('cinema', '')}",
                "startDate": f"{showtime['year']}-{showtime['month']:02d}-{showtime['day']:02d}T{showtime['hour']:02d}:{showtime['minute']:02d}:00+03:00",
                "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
                "eventStatus": "https://schema.org/EventScheduled",
            }

            location_obj = {"@type": "MovieTheater", "name": cinema.get("cinema", "")}
            if cinema.get("address"):
                location_obj["address"] = {
                    "@type": "PostalAddress",
                    "streetAddress": cinema["address"],
                    "addressLocality": "Αθήνα",
                    "addressCountry": "GR",
                }
            if cinema.get("lat") and cinema.get("lon"):
                location_obj["geo"] = {
                    "@type": "GeoCoordinates",
                    "latitude": str(cinema["lat"]),
                    "longitude": str(cinema["lon"]),
                }
            if cinema.get("website"):
                location_obj["url"] = cinema["website"]

            event["location"] = location_obj
            screening_events.append(event)

    # Build Movie schema
    movie_schema = {
        "@context": "https://schema.org",
        "@type": "Movie",
        "name": movie.get("title_en") or title_gr,
        "image": poster,
        "description": plot,
    }

    if imdb_link:
        movie_schema["@id"] = imdb_link

    if title_gr and title_gr != movie_schema["name"]:
        movie_schema["alternateName"] = title_gr

    if year:
        movie_schema["datePublished"] = str(year)

    if runtime:
        minutes = re.search(r"(\d+)", runtime)
        if minutes:
            movie_schema["duration"] = f"PT{minutes.group(1)}M"

    if omdb.get("genre"):
        movie_schema["genre"] = [g.strip() for g in omdb["genre"].split(",")]

    if omdb.get("director") and omdb["director"] != "N/A":
        directors = [d.strip() for d in omdb["director"].split(",")]
        if len(directors) == 1:
            movie_schema["director"] = {"@type": "Person", "name": directors[0]}
        else:
            movie_schema["director"] = [{"@type": "Person", "name": d} for d in directors]

    if omdb.get("actors") and omdb["actors"] != "N/A":
        actors = [a.strip() for a in omdb["actors"].split(",")]
        movie_schema["actor"] = [{"@type": "Person", "name": a} for a in actors[:5]]

    if omdb.get("imdb_rating") and omdb["imdb_rating"] != "N/A":
        try:
            rating_val = float(omdb["imdb_rating"])
        except (ValueError, TypeError):
            rating_val = 0
        votes = omdb.get("imdb_votes", "").replace(",", "") if omdb.get("imdb_votes") else ""
        if votes and 1 <= rating_val <= 10:
            rating_obj = {
                "@type": "AggregateRating",
                "ratingValue": omdb["imdb_rating"],
                "bestRating": "10",
                "worstRating": "1",
                "ratingCount": votes,
            }
            movie_schema["aggregateRating"] = rating_obj

    if screening_events:
        movie_schema["subEvent"] = screening_events

    return f"""
  <script type="application/ld+json">
  {json.dumps(movie_schema, ensure_ascii=False, indent=2)}
  </script>"""


# --- Review Fetching ---


def fetch_athinorama_review(athinorama_url):
    """Fetch Athinorama main page, extract movie data + follow full review link."""
    print(f"    Fetching Athinorama: {athinorama_url}")
    response = requests.get(athinorama_url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")

    data = {}

    scripts = soup.find_all("script", type="application/ld+json")
    for s in scripts:
        try:
            schema = json.loads(s.string)
            if schema.get("@type") == "Movie":
                data["title_gr"] = schema.get("name", "")
                data["title_en"] = schema.get("alternateName", "")
                data["year"] = schema.get("copyrightYear", "")
                data["genre"] = schema.get("genre", "")
                data["duration"] = schema.get("duration", "")
                data["director"] = schema.get("director", {}).get("name", "")
                data["actors"] = [a["name"] for a in schema.get("actor", [])]

                review = schema.get("review", {})
                data["review_body"] = review.get("reviewBody", "")
                data["reviewer"] = review.get("author", {}).get("name", "")
                rating = review.get("reviewRating", {})
                data["rating"] = f"{rating.get('ratingValue', '')}/{rating.get('bestRating', '')}"
        except (json.JSONDecodeError, TypeError):
            continue

    full_review_link = soup.find("a", class_="full-summary")
    if full_review_link and full_review_link.get("href"):
        href = full_review_link["href"]
        if href.startswith("/"):
            full_review_url = f"https://www.athinorama.gr{href}"
        else:
            full_review_url = href

        print(f"    Following full review: {full_review_url}")
        data["full_review"] = fetch_athinorama_full_review(full_review_url)
        data["full_review_url"] = full_review_url
    else:
        data["full_review"] = ""
        data["full_review_url"] = ""

    return data


def fetch_athinorama_full_review(url):
    """Fetch the full review page from Athinorama and extract article text."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        article = soup.find("article")
        if article:
            paragraphs = article.find_all("p")
        else:
            paragraphs = soup.find_all("p")

        review_paragraphs = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            if len(text) > 80 and "€" not in text and "cookie" not in text.lower():
                review_paragraphs.append(text)

        return "\n\n".join(review_paragraphs)
    except Exception as e:
        print(f"    Error fetching full review: {e}")
        return ""


def fetch_flix_review(url):
    """Fetch Flix review page and extract review text."""
    if not url:
        return {"review_text": "", "rating": None}

    print(f"    Fetching Flix: {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        rating = None
        tag = soup.find("span", itemprop="aggregateRating")
        if tag and tag.has_attr("title"):
            match = re.search(r"(\d+)\s*στα\s*10", tag["title"])
            if match:
                rating = int(match.group(1))

        review_text = []
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if len(text) > 100:
                if any(skip in text.lower() for skip in ["cookie", "newsletter", "subscribe"]):
                    continue
                review_text.append(text)

        return {
            "review_text": "\n\n".join(review_text[:8]),
            "rating": rating,
        }
    except Exception as e:
        print(f"    Error fetching Flix review: {e}")
        return {"review_text": "", "rating": None}


def fetch_lifo_review(url):
    """Fetch LIFO review page and extract review text."""
    if not url:
        return {"review_text": "", "rating": None}

    print(f"    Fetching LIFO: {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        rating = None
        parent = soup.find("div", class_="lifoRating fs-9-v-lg fs-7-v")
        if parent:
            rating_div = parent.find("div", class_="ratings")
            if rating_div:
                rating_class = next(
                    (c for c in rating_div["class"] if c.startswith("rating-")), None
                )
                if rating_class:
                    rating = int(rating_class.split("-")[-1])

        review_text = []
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if len(text) > 100:
                if any(skip in text.lower() for skip in ["cookie", "newsletter", "subscribe"]):
                    continue
                review_text.append(text)

        return {
            "review_text": "\n\n".join(review_text[:6]),
            "rating": rating,
        }
    except Exception as e:
        print(f"    Error fetching LIFO review: {e}")
        return {"review_text": "", "rating": None}


# --- Content Generation ---


def generate_movie_content(athinorama_data, flix_data, lifo_data, omdb_data):
    """Call Gemini to generate unique movie landing page content."""

    omdb_section = ""
    if omdb_data:
        omdb_section = f"""
=== IMDB / TMDB ΠΛΗΡΟΦΟΡΙΕΣ ===
Τίτλος (Αγγλικά): {omdb_data.get('omdb_title', '')}
IMDb Rating: {omdb_data.get('omdb_rating', '')} ({omdb_data.get('omdb_votes', '')} ψήφοι)
Σκηνοθεσία: {omdb_data.get('omdb_director', '')}
Ηθοποιοί: {omdb_data.get('omdb_actors', '')}
Είδος: {omdb_data.get('omdb_genre', '')}
Διάρκεια: {omdb_data.get('omdb_runtime', '')}
Υπόθεση (Αγγλικά): {omdb_data.get('omdb_plot', '')}
Γλώσσα: {omdb_data.get('omdb_language', '')}
Χώρα: {omdb_data.get('omdb_country', '')}
"""

    lifo_section = ""
    if lifo_data.get("review_text"):
        lifo_rating = f" ({lifo_data['rating']}/10)" if lifo_data.get("rating") else ""
        lifo_section = f"""
=== ΚΡΙΤΙΚΗ LIFO{lifo_rating} ===
{lifo_data['review_text']}
"""

    prompt = f"""Είσαι ο συντάκτης περιεχομένου για το ti-paizei-tora.gr, έναν ελληνικό ιστότοπο
που βοηθά τους χρήστες να βρουν ταινίες στα σινεμά της Αθήνας.

Βασισμένο στις παρακάτω κριτικές και πληροφορίες, δημιούργησε ΠΡΩΤΟΤΥΠΟ περιεχόμενο
για τη σελίδα της ταινίας. ΜΗΝ αντιγράψεις κείμενο — δημιούργησε δικό σου, μοναδικό περιεχόμενο.

=== ΣΤΟΙΧΕΙΑ ΤΑΙΝΙΑΣ ===
Τίτλος (Ελληνικά): {athinorama_data.get('title_gr', '')}
Τίτλος (Αγγλικά): {athinorama_data.get('title_en', '')}
Σκηνοθεσία: {athinorama_data.get('director', '')}
Ηθοποιοί: {', '.join(athinorama_data.get('actors', []))}
Έτος: {athinorama_data.get('year', '')}
Είδος: {athinorama_data.get('genre', '')}
Διάρκεια: {athinorama_data.get('duration', '')}
{omdb_section}
=== ΚΡΙΤΙΚΗ ATHINORAMA ({athinorama_data.get('rating', '')}) ===
{athinorama_data.get('full_review') or athinorama_data.get('review_body', '')}

=== ΚΡΙΤΙΚΗ FLIX ({flix_data.get('rating', '')}/10) ===
{flix_data.get('review_text', '')}
{lifo_section}
=== ΟΔΗΓΙΕΣ ===
Δημιούργησε JSON με τα εξής πεδία:

1. "synopsis" — Σύνοψη ταινίας σε 2-3 προτάσεις. Ζωντανή, χωρίς spoilers.
2. "review_summary" — Περίληψη κριτικών σε 2-3 προτάσεις. Τι λένε οι κριτικοί, ποιο είναι το consensus.
3. "highlights" — Array με 3-4 bullet points. Τα δυνατά σημεία (σκηνοθεσία, ερμηνείες, μουσική κλπ).
4. "mood_tags" — Array με 3-5 tags που περιγράφουν τη «διάθεση» (π.χ. "Συγκινητική", "Ατμοσφαιρική").
5. "who_will_enjoy" — Σε 1 πρόταση: ποιο κοινό θα απολαύσει αυτή την ταινία.
6. "one_liner" — Μία πιασάρικη φράση / tagline στα Ελληνικά.

ΣΗΜΑΝΤΙΚΟ:
- Γράψε σε φυσικά, σύγχρονα Ελληνικά
- Ύφος: φιλικό, ενθουσιώδες αλλά ειλικρινές, σαν σύσταση φίλου
- ΜΗΝ χρησιμοποιήσεις emojis
- Λάβε υπόψη και τις τρεις κριτικές για μια πιο ολοκληρωμένη εικόνα
- Απάντησε ΜΟΝΟ με valid JSON, χωρίς markdown formatting
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }

    response = requests.post(GEMINI_URL, json=payload)

    if response.status_code != 200:
        print(f"    Gemini API error: {response.status_code}")
        print(f"    {response.text[:200]}")
        return None

    result = response.json()
    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"    Error parsing Gemini response: {e}")
        return None


# --- HTML Generation ---


def format_athinorama_display(rating_stars):
    """Format rating_stars float for HTML display: 2.5 -> '2,5/5'"""
    if rating_stars is None:
        return None
    if rating_stars == int(rating_stars):
        return f"{int(rating_stars)}/5"
    return f"{str(rating_stars).replace('.', ',')}/5"


def generate_html(data, cinema_screenings=None):
    """Generate a rich HTML page from the movie content data."""
    movie = data.get("movie", {})
    ratings = data.get("ratings", {})
    omdb = data.get("omdb", {})
    sources = data.get("sources", {})
    content = data.get("generated_content", {})

    title_gr = movie.get("title_gr", "")
    title_en = movie.get("title_en", "")
    year = movie.get("year", "")
    genre = movie.get("genre", "")
    director = omdb.get("director") or movie.get("director", "")
    runtime = omdb.get("runtime", "").replace(" min", "'") if omdb.get("runtime") else ""
    poster = omdb.get("poster", "")
    plot_en = omdb.get("plot", "")
    language = omdb.get("language", "")
    imdb_link = omdb.get("imdb_link", "")
    actors_str = omdb.get("actors", "")
    actors = [a.strip() for a in actors_str.split(",")] if actors_str else movie.get("actors", [])

    one_liner = content.get("one_liner", "")
    synopsis = content.get("synopsis", "")
    review_summary = content.get("review_summary", "")
    highlights = content.get("highlights", [])
    mood_tags = content.get("mood_tags", [])
    who_will_enjoy = content.get("who_will_enjoy", "")

    # Page title
    page_title = title_gr
    if title_en:
        page_title += f" ({title_en})"

    # Genre tags from OMDB
    omdb_genres = [g.strip() for g in omdb.get("genre", "").split(",")] if omdb.get("genre") else []

    # Rating pills HTML
    rating_pills_html = ""
    if ratings.get("athinorama") and sources.get("athinorama_url"):
        rating_pills_html += f'        <a href="{sources["athinorama_url"]}" target="_blank" rel="noopener" class="rating-pill athinorama">Athinorama {ratings["athinorama"]}</a>\n'
    if ratings.get("flix") and sources.get("flix_url"):
        rating_pills_html += f'        <a href="{sources["flix_url"]}" target="_blank" rel="noopener" class="rating-pill flix">Flix {ratings["flix"]}</a>\n'
    if ratings.get("lifo") and sources.get("lifo_url"):
        rating_pills_html += f'        <a href="{sources["lifo_url"]}" target="_blank" rel="noopener" class="rating-pill lifo">Lifo {ratings["lifo"]}</a>\n'
    if ratings.get("imdb") and imdb_link:
        rating_pills_html += f'        <a href="{imdb_link}" target="_blank" rel="noopener" class="rating-pill imdb">IMDb {ratings["imdb"]}</a>\n'

    # Highlights HTML
    highlights_html = "\n".join(f"          <li>{h}</li>" for h in highlights)

    # Mood tags HTML
    mood_html = "\n".join(f'        <span class="mood-tag">{t}</span>' for t in mood_tags)

    # Genre tags HTML
    genre_tags_html = "\n".join(f'            <span class="genre-tag">{g}</span>' for g in omdb_genres)

    # Cast chips HTML
    cast_html = ""
    if director:
        cast_html += f'        <span class="cast-chip director">Σκηνοθεσία: {director}</span>\n'
    for actor in actors[:5]:
        if actor:
            cast_html += f'        <span class="cast-chip">{actor}</span>\n'

    # Sources HTML
    sources_html = ""
    if sources.get("athinorama_url"):
        sources_html += f'        <li><span class="source-label">Athinorama</span> <a href="{sources["athinorama_url"]}" target="_blank" rel="noopener">Σελίδα ταινίας</a>'
        if sources.get("athinorama_review_url"):
            sources_html += f' · <a href="{sources["athinorama_review_url"]}" target="_blank" rel="noopener">Κριτική</a>'
        sources_html += "</li>\n"
    if sources.get("flix_url"):
        sources_html += f'        <li><span class="source-label">Flix</span> <a href="{sources["flix_url"]}" target="_blank" rel="noopener">Κριτική</a></li>\n'
    if sources.get("lifo_url"):
        sources_html += f'        <li><span class="source-label">Lifo</span> <a href="{sources["lifo_url"]}" target="_blank" rel="noopener">Κριτική</a></li>\n'
    if imdb_link:
        sources_html += f'        <li><span class="source-label">IMDb</span> <a href="{imdb_link}" target="_blank" rel="noopener">{imdb_link}</a></li>\n'

    # Meta info spans
    meta_spans = ""
    if genre:
        meta_spans += f"            <span>{genre}</span>\n"
    if runtime:
        meta_spans += f"            <span>{runtime}</span>\n"
    if director:
        meta_spans += f"            <span>{director}</span>\n"
    if language:
        meta_spans += f"            <span>{language.upper()}</span>\n"

    # Poster HTML
    poster_html = ""
    if poster and poster != "N/A":
        poster_html = f'        <img class="hero-poster" src="{poster}" alt="{title_gr} poster">'

    # Tagline section
    tagline_html = ""
    if plot_en:
        tagline_html = f"""      <div class="tagline-en">
        <q>{plot_en}</q>
      </div>"""

    # Conditional sections
    ratings_section = ""
    if rating_pills_html:
        ratings_section = f"""    <div class="content-card">
      <h2>Βαθμολογίες Κριτικών</h2>
      <div class="ratings-row">
{rating_pills_html}      </div>
      {"<p>" + review_summary + "</p>" if review_summary else ""}
    </div>"""

    synopsis_section = ""
    if synopsis:
        synopsis_section = f"""      <div class="content-card">
        <h2>Υπόθεση</h2>
        <p>{synopsis}</p>
      </div>"""

    highlights_section = ""
    if highlights:
        highlights_section = f"""      <div class="content-card">
        <h2>Γιατί αξίζει να τη δεις</h2>
        <ul class="highlights-list">
{highlights_html}
        </ul>
      </div>"""

    mood_section = ""
    if mood_tags:
        mood_section = f"""    <div class="content-card">
      <h2>Διάθεση</h2>
      <div class="mood-tags">
{mood_html}
      </div>
    </div>"""

    audience_section = ""
    if who_will_enjoy:
        audience_section = f"""    <div class="content-card">
      <h2>Ποιοι θα την απολαύσουν</h2>
      <div class="audience-box">
        {who_will_enjoy}
      </div>
    </div>"""

    cast_section = ""
    if cast_html:
        cast_section = f"""    <div class="content-card">
      <h2>Συντελεστές</h2>
      <div class="cast-grid">
{cast_html}      </div>
    </div>"""

    sources_section = ""
    if sources_html:
        sources_section = f"""    <div class="content-card" style="margin-top: 20px;">
      <h2>Πηγές</h2>
      <ul class="sources-list">
{sources_html}      </ul>
    </div>"""

    # Showtimes section
    showtimes_section = ""
    showtimes_css = ""
    showtimes_js = ""
    showtimes_schema = ""
    if cinema_screenings:
        showtimes_section, showtimes_css, showtimes_js, showtimes_schema = build_showtimes_html(
            cinema_screenings, page_title, data
        )

    html = f"""<!DOCTYPE html>
<html lang="el">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{page_title} - Σινεμά Αθήνας | ti-paizei-tora.gr</title>
  <meta name="description" content="{one_liner} Δες πού παίζει στα σινεμά της Αθήνας.">
  <link rel="icon" type="image/svg+xml" href="/ti_paizei_tora_logo.svg">{showtimes_schema}
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      line-height: 1.6;
      color: #333;
      background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
      min-height: 100vh;
      padding: 20px;
    }}
    .container {{ max-width: 900px; margin: 0 auto; }}
    .back-link {{
      display: inline-block;
      margin-bottom: 16px;
      color: #667eea;
      text-decoration: none;
      font-weight: 600;
      font-size: 0.95em;
    }}
    .back-link:hover {{ text-decoration: underline; }}
    .movie-hero {{
      background: white;
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 4px 20px rgba(0,0,0,0.1);
      margin-bottom: 20px;
    }}
    .hero-gradient {{
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      padding: 32px;
      color: white;
      display: flex;
      gap: 24px;
      align-items: flex-start;
    }}
    .hero-poster {{
      width: 140px;
      height: 200px;
      border-radius: 10px;
      object-fit: cover;
      box-shadow: 0 4px 15px rgba(0,0,0,0.3);
      flex-shrink: 0;
    }}
    .hero-info {{ flex: 1; }}
    .hero-info h1 {{ font-size: 1.8em; margin-bottom: 4px; line-height: 1.2; }}
    .hero-info .subtitle {{ font-size: 1.1em; opacity: 0.85; margin-bottom: 12px; }}
    .hero-meta {{ display: flex; gap: 12px; flex-wrap: wrap; font-size: 0.9em; opacity: 0.9; }}
    .hero-meta span {{ background: rgba(255,255,255,0.15); padding: 4px 10px; border-radius: 6px; }}
    .genre-tags {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }}
    .genre-tag {{ background: rgba(255,255,255,0.2); padding: 4px 12px; border-radius: 14px; font-size: 0.82em; font-weight: 500; }}
    .one-liner {{
      padding: 20px 32px;
      font-size: 1.15em;
      font-style: italic;
      color: #555;
      border-bottom: 1px solid #f0f0f0;
      text-align: center;
    }}
    .tagline-en {{ padding: 12px 32px 16px; font-size: 0.95em; color: #888; text-align: center; }}
    .tagline-en q {{ font-style: italic; }}
    .content-grid {{ display: grid; gap: 20px; margin-bottom: 20px; }}
    .content-card {{
      background: white;
      border-radius: 12px;
      padding: 24px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.06);
      margin-bottom: 20px;
    }}
    .content-card h2 {{
      font-size: 1.1em;
      color: #667eea;
      margin-bottom: 12px;
      padding-bottom: 8px;
      border-bottom: 2px solid #f0f0f0;
    }}
    .content-card p {{ color: #444; line-height: 1.7; }}
    .highlights-list {{ list-style: none; padding: 0; }}
    .highlights-list li {{
      padding: 10px 0 10px 28px;
      position: relative;
      color: #444;
      border-bottom: 1px solid #f8f8f8;
    }}
    .highlights-list li:last-child {{ border-bottom: none; }}
    .highlights-list li::before {{
      content: '';
      position: absolute;
      left: 0;
      top: 16px;
      width: 10px;
      height: 10px;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      border-radius: 50%;
    }}
    .mood-tags {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    .mood-tag {{
      background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
      border: 1px solid #e0e0e0;
      padding: 8px 16px;
      border-radius: 20px;
      font-size: 0.9em;
      font-weight: 500;
      color: #555;
    }}
    .ratings-row {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }}
    .rating-pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 14px;
      border-radius: 10px;
      font-weight: 600;
      font-size: 0.9em;
      color: white;
      text-decoration: none;
      box-shadow: 0 2px 8px rgba(0,0,0,0.15);
      transition: transform 0.15s, box-shadow 0.15s;
    }}
    .rating-pill:hover {{ transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.2); }}
    .rating-pill.athinorama {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }}
    .rating-pill.flix {{ background: linear-gradient(135deg, #00BCD4 0%, #0097A7 100%); }}
    .rating-pill.lifo {{ background: linear-gradient(135deg, #E91E63 0%, #C2185B 100%); }}
    .rating-pill.imdb {{ background: linear-gradient(135deg, #F5C518 0%, #DDB00E 100%); color: #000; }}
    .audience-box {{
      background: linear-gradient(135deg, #f0f9f4 0%, #e8f5e9 100%);
      border-left: 4px solid #28a745;
      padding: 16px 20px;
      border-radius: 0 10px 10px 0;
      font-size: 1em;
      color: #2e7d32;
    }}
    .cast-grid {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    .cast-chip {{
      background: #f8f9fa;
      border: 1px solid #e9ecef;
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 0.88em;
      color: #555;
    }}
    .cast-chip.director {{
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      border: none;
    }}
    .sources-list {{ list-style: none; padding: 0; }}
    .sources-list li {{ padding: 8px 0; border-bottom: 1px solid #f0f0f0; }}
    .sources-list li:last-child {{ border-bottom: none; }}
    .sources-list a {{ color: #667eea; text-decoration: none; font-weight: 500; font-size: 0.92em; }}
    .sources-list a:hover {{ text-decoration: underline; }}
    .sources-list .source-label {{ display: inline-block; min-width: 100px; color: #888; font-size: 0.85em; font-weight: 400; }}
    .cta-section {{
      text-align: center;
      padding: 24px;
      background: white;
      border-radius: 12px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.06);
    }}
    .cta-btn {{
      display: inline-block;
      padding: 14px 32px;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      text-decoration: none;
      border-radius: 10px;
      font-weight: 700;
      font-size: 1.05em;
      box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
      transition: transform 0.2s, box-shadow 0.2s;
    }}
    .cta-btn:hover {{
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
    }}
    @media (max-width: 768px) {{
      body {{ padding: 12px; }}
      .hero-gradient {{
        flex-direction: column;
        align-items: center;
        text-align: center;
        padding: 24px;
      }}
      .hero-poster {{ width: 120px; height: 170px; }}
      .hero-info h1 {{ font-size: 1.5em; }}
      .hero-meta {{ justify-content: center; }}
      .content-card {{ padding: 20px; }}
    }}{showtimes_css}
  </style>
</head>
<body>
  <div class="container">
    <a href="/" class="back-link">&larr; Πίσω στο πρόγραμμα</a>

    <div class="movie-hero">
      <div class="hero-gradient">
{poster_html}
        <div class="hero-info">
          <h1>{title_gr}</h1>
          <div class="subtitle">{title_en} ({year})</div>
          <div class="hero-meta">
{meta_spans}          </div>
          <div class="genre-tags">
{genre_tags_html}
          </div>
        </div>
      </div>
      <div class="one-liner">
        {one_liner}
      </div>
{tagline_html}
    </div>

{ratings_section}

    <div class="content-grid">
{synopsis_section}

{highlights_section}
    </div>

{mood_section}

{audience_section}

{cast_section}

{showtimes_section}

    <div class="cta-section">
      <p style="margin-bottom: 14px; color: #666;">Δες πού παίζει τώρα στην Αθήνα</p>
      <a href="/" class="cta-btn">Βρες Προβολές</a>
    </div>

{sources_section}
  </div>
{showtimes_js}
</body>
</html>"""

    return html


def generate_minimal_html(data, cinema_screenings=None):
    """Generate a clean HTML page with only OMDB/TMDB data (no Gemini content)."""
    movie = data.get("movie", {})
    ratings = data.get("ratings", {})
    omdb = data.get("omdb", {})
    sources = data.get("sources", {})

    title_gr = movie.get("title_gr", "")
    title_en = movie.get("title_en", "")
    year = movie.get("year", "")
    genre = movie.get("genre", "")
    director = omdb.get("director") or movie.get("director", "")
    runtime = omdb.get("runtime", "").replace(" min", "'") if omdb.get("runtime") else ""
    poster = omdb.get("poster", "")
    plot_en = omdb.get("plot", "")
    language = omdb.get("language", "")
    imdb_link = omdb.get("imdb_link", "")
    actors_str = omdb.get("actors", "")
    actors = [a.strip() for a in actors_str.split(",")] if actors_str else movie.get("actors", [])

    page_title = title_gr
    if title_en:
        page_title += f" ({title_en})"

    omdb_genres = [g.strip() for g in omdb.get("genre", "").split(",")] if omdb.get("genre") else []

    # Rating pills
    rating_pills_html = ""
    if ratings.get("athinorama") and sources.get("athinorama_url"):
        rating_pills_html += f'        <a href="{sources["athinorama_url"]}" target="_blank" rel="noopener" class="rating-pill athinorama">Athinorama {ratings["athinorama"]}</a>\n'
    if ratings.get("flix") and sources.get("flix_url"):
        rating_pills_html += f'        <a href="{sources["flix_url"]}" target="_blank" rel="noopener" class="rating-pill flix">Flix {ratings["flix"]}</a>\n'
    if ratings.get("lifo") and sources.get("lifo_url"):
        rating_pills_html += f'        <a href="{sources["lifo_url"]}" target="_blank" rel="noopener" class="rating-pill lifo">Lifo {ratings["lifo"]}</a>\n'
    if ratings.get("imdb") and imdb_link:
        rating_pills_html += f'        <a href="{imdb_link}" target="_blank" rel="noopener" class="rating-pill imdb">IMDb {ratings["imdb"]}</a>\n'

    genre_tags_html = "\n".join(f'            <span class="genre-tag">{g}</span>' for g in omdb_genres)

    cast_html = ""
    if director:
        cast_html += f'        <span class="cast-chip director">Σκηνοθεσία: {director}</span>\n'
    for actor in actors[:5]:
        if actor:
            cast_html += f'        <span class="cast-chip">{actor}</span>\n'

    meta_spans = ""
    if genre:
        meta_spans += f"            <span>{genre}</span>\n"
    if runtime:
        meta_spans += f"            <span>{runtime}</span>\n"
    if director:
        meta_spans += f"            <span>{director}</span>\n"
    if language:
        meta_spans += f"            <span>{language.upper()}</span>\n"

    poster_html = ""
    if poster and poster != "N/A":
        poster_html = f'        <img class="hero-poster" src="{poster}" alt="{title_gr} poster">'

    # Plot section (OMDB plot as synopsis)
    plot_section = ""
    if plot_en:
        plot_section = f"""    <div class="content-card">
      <h2>Υπόθεση</h2>
      <p>{plot_en}</p>
    </div>"""

    # Ratings section
    ratings_section = ""
    if rating_pills_html:
        ratings_section = f"""    <div class="content-card">
      <h2>Βαθμολογίες</h2>
      <div class="ratings-row">
{rating_pills_html}      </div>
    </div>"""

    # Cast section
    cast_section = ""
    if cast_html:
        cast_section = f"""    <div class="content-card">
      <h2>Συντελεστές</h2>
      <div class="cast-grid">
{cast_html}      </div>
    </div>"""

    # Sources
    sources_html = ""
    if sources.get("athinorama_url"):
        sources_html += f'        <li><span class="source-label">Athinorama</span> <a href="{sources["athinorama_url"]}" target="_blank" rel="noopener">Σελίδα ταινίας</a></li>\n'
    if sources.get("flix_url"):
        sources_html += f'        <li><span class="source-label">Flix</span> <a href="{sources["flix_url"]}" target="_blank" rel="noopener">Κριτική</a></li>\n'
    if sources.get("lifo_url"):
        sources_html += f'        <li><span class="source-label">Lifo</span> <a href="{sources["lifo_url"]}" target="_blank" rel="noopener">Κριτική</a></li>\n'
    if imdb_link:
        sources_html += f'        <li><span class="source-label">IMDb</span> <a href="{imdb_link}" target="_blank" rel="noopener">{imdb_link}</a></li>\n'

    sources_section = ""
    if sources_html:
        sources_section = f"""    <div class="content-card">
      <h2>Πηγές</h2>
      <ul class="sources-list">
{sources_html}      </ul>
    </div>"""

    # Showtimes section
    showtimes_section = ""
    showtimes_css = ""
    showtimes_js = ""
    showtimes_schema = ""
    if cinema_screenings:
        showtimes_section, showtimes_css, showtimes_js, showtimes_schema = build_showtimes_html(
            cinema_screenings, page_title, data
        )

    html = f"""<!DOCTYPE html>
<html lang="el">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{page_title} - Σινεμά Αθήνας | ti-paizei-tora.gr</title>
  <meta name="description" content="Δες πού παίζει {title_gr} στα σινεμά της Αθήνας.">
  <link rel="icon" type="image/svg+xml" href="/ti_paizei_tora_logo.svg">{showtimes_schema}
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      line-height: 1.6;
      color: #333;
      background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
      min-height: 100vh;
      padding: 20px;
    }}
    .container {{ max-width: 900px; margin: 0 auto; }}
    .back-link {{
      display: inline-block;
      margin-bottom: 16px;
      color: #667eea;
      text-decoration: none;
      font-weight: 600;
      font-size: 0.95em;
    }}
    .back-link:hover {{ text-decoration: underline; }}
    .movie-hero {{
      background: white;
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 4px 20px rgba(0,0,0,0.1);
      margin-bottom: 20px;
    }}
    .hero-gradient {{
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      padding: 32px;
      color: white;
      display: flex;
      gap: 24px;
      align-items: flex-start;
    }}
    .hero-poster {{
      width: 140px;
      height: 200px;
      border-radius: 10px;
      object-fit: cover;
      box-shadow: 0 4px 15px rgba(0,0,0,0.3);
      flex-shrink: 0;
    }}
    .hero-info {{ flex: 1; }}
    .hero-info h1 {{ font-size: 1.8em; margin-bottom: 4px; line-height: 1.2; }}
    .hero-info .subtitle {{ font-size: 1.1em; opacity: 0.85; margin-bottom: 12px; }}
    .hero-meta {{ display: flex; gap: 12px; flex-wrap: wrap; font-size: 0.9em; opacity: 0.9; }}
    .hero-meta span {{ background: rgba(255,255,255,0.15); padding: 4px 10px; border-radius: 6px; }}
    .genre-tags {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }}
    .genre-tag {{ background: rgba(255,255,255,0.2); padding: 4px 12px; border-radius: 14px; font-size: 0.82em; font-weight: 500; }}
    .content-card {{
      background: white;
      border-radius: 12px;
      padding: 24px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.06);
      margin-bottom: 20px;
    }}
    .content-card h2 {{
      font-size: 1.1em;
      color: #667eea;
      margin-bottom: 12px;
      padding-bottom: 8px;
      border-bottom: 2px solid #f0f0f0;
    }}
    .content-card p {{ color: #444; line-height: 1.7; }}
    .ratings-row {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }}
    .rating-pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 14px;
      border-radius: 10px;
      font-weight: 600;
      font-size: 0.9em;
      color: white;
      text-decoration: none;
      box-shadow: 0 2px 8px rgba(0,0,0,0.15);
      transition: transform 0.15s, box-shadow 0.15s;
    }}
    .rating-pill:hover {{ transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.2); }}
    .rating-pill.athinorama {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }}
    .rating-pill.flix {{ background: linear-gradient(135deg, #00BCD4 0%, #0097A7 100%); }}
    .rating-pill.lifo {{ background: linear-gradient(135deg, #E91E63 0%, #C2185B 100%); }}
    .rating-pill.imdb {{ background: linear-gradient(135deg, #F5C518 0%, #DDB00E 100%); color: #000; }}
    .cast-grid {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    .cast-chip {{
      background: #f8f9fa;
      border: 1px solid #e9ecef;
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 0.88em;
      color: #555;
    }}
    .cast-chip.director {{
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      border: none;
    }}
    .sources-list {{ list-style: none; padding: 0; }}
    .sources-list li {{ padding: 8px 0; border-bottom: 1px solid #f0f0f0; }}
    .sources-list li:last-child {{ border-bottom: none; }}
    .sources-list a {{ color: #667eea; text-decoration: none; font-weight: 500; font-size: 0.92em; }}
    .sources-list a:hover {{ text-decoration: underline; }}
    .sources-list .source-label {{ display: inline-block; min-width: 100px; color: #888; font-size: 0.85em; font-weight: 400; }}
    .cta-section {{
      text-align: center;
      padding: 24px;
      background: white;
      border-radius: 12px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.06);
    }}
    .cta-btn {{
      display: inline-block;
      padding: 14px 32px;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      text-decoration: none;
      border-radius: 10px;
      font-weight: 700;
      font-size: 1.05em;
      box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
      transition: transform 0.2s, box-shadow 0.2s;
    }}
    .cta-btn:hover {{
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
    }}
    @media (max-width: 768px) {{
      body {{ padding: 12px; }}
      .hero-gradient {{
        flex-direction: column;
        align-items: center;
        text-align: center;
        padding: 24px;
      }}
      .hero-poster {{ width: 120px; height: 170px; }}
      .hero-info h1 {{ font-size: 1.5em; }}
      .hero-meta {{ justify-content: center; }}
      .content-card {{ padding: 20px; }}
    }}{showtimes_css}
  </style>
</head>
<body>
  <div class="container">
    <a href="/" class="back-link">&larr; Πίσω στο πρόγραμμα</a>

    <div class="movie-hero">
      <div class="hero-gradient">
{poster_html}
        <div class="hero-info">
          <h1>{title_gr}</h1>
          <div class="subtitle">{title_en} ({year})</div>
          <div class="hero-meta">
{meta_spans}          </div>
          <div class="genre-tags">
{genre_tags_html}
          </div>
        </div>
      </div>
    </div>

{ratings_section}

{plot_section}

{cast_section}

{showtimes_section}

    <div class="cta-section">
      <p style="margin-bottom: 14px; color: #666;">Δες πού παίζει τώρα στην Αθήνα</p>
      <a href="/" class="cta-btn">Βρες Προβολές</a>
    </div>

{sources_section}
  </div>
{showtimes_js}
</body>
</html>"""

    return html

# --- Main Processing ---


def process_single_movie(movie_db, flix_index, lifo_index, cinema_list=None):
    """Process one movie: scrape reviews, call Gemini, save JSON + HTML.
    Falls back to minimal HTML if no reviews are available or Gemini fails."""
    slug = movie_db.get("slug")
    greek_title = movie_db.get("greek_title", "")
    original_title = movie_db.get("original_title", "")
    athinorama_url = movie_db.get("athinorama_link")

    # Lookup flix and lifo
    flix_url, flix_rating = lookup_flix(movie_db, flix_index)
    lifo_url, lifo_rating = lookup_lifo(movie_db, lifo_index)

    # Build common output fields
    athinorama_stars = movie_db.get("rating_stars")
    ratings = {
        "athinorama": format_athinorama_display(athinorama_stars),
        "flix": f"{flix_rating}/10" if flix_rating else None,
        "lifo": f"{lifo_rating}/10" if lifo_rating else None,
        "imdb": f"{movie_db.get('omdb_rating')}/10" if movie_db.get("omdb_rating") else None,
    }

    sources = {
        "athinorama_url": athinorama_url,
        "athinorama_review_url": "",
        "flix_url": flix_url,
        "lifo_url": lifo_url,
        "imdb_url": movie_db.get("imdb_link", ""),
    }

    omdb = {
        "poster": movie_db.get("omdb_poster", ""),
        "plot": movie_db.get("omdb_plot", ""),
        "director": movie_db.get("omdb_director", ""),
        "actors": movie_db.get("omdb_actors", ""),
        "genre": movie_db.get("omdb_genre", ""),
        "runtime": movie_db.get("omdb_runtime", ""),
        "language": movie_db.get("omdb_language", ""),
        "country": movie_db.get("omdb_country", ""),
        "imdb_link": movie_db.get("imdb_link", ""),
        "imdb_rating": movie_db.get("omdb_rating", ""),
        "imdb_votes": movie_db.get("omdb_votes", ""),
    }

    # Always fetch reviews and call Gemini — even one source (athinorama) is enough
    content = None
    athinorama_data = {}

    if athinorama_url:
        try:
            athinorama_data = fetch_athinorama_review(athinorama_url)
            sources["athinorama_review_url"] = athinorama_data.get("full_review_url", "")
        except Exception as e:
            print(f"    Athinorama fetch failed: {e}")

    flix_data = fetch_flix_review(flix_url)
    lifo_data = fetch_lifo_review(lifo_url)

    # Generate content with Gemini
    print("    Calling Gemini API...")
    content = generate_movie_content(athinorama_data, flix_data, lifo_data, movie_db)

    if not content:
        print("    Gemini failed, falling back to minimal HTML")

    # Build output
    movie_info = {
        "title_gr": athinorama_data.get("title_gr") or greek_title,
        "title_en": athinorama_data.get("title_en") or original_title,
        "director": athinorama_data.get("director") or movie_db.get("omdb_director", ""),
        "actors": athinorama_data.get("actors") or [],
        "year": athinorama_data.get("year") or movie_db.get("year", ""),
        "genre": athinorama_data.get("genre") or movie_db.get("movie_type", ""),
        "slug": slug,
    }

    output = {
        "movie": movie_info,
        "ratings": ratings,
        "omdb": omdb,
        "sources": sources,
        "generated_content": content,
    }

    # Save JSON
    json_path = os.path.join(OUTPUT_DIR, f"{slug}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Parse showtimes from cinema data
    cinema_screenings = get_cinema_screenings(cinema_list) if cinema_list else []

    # Generate HTML - rich if we have generated content, minimal otherwise
    if content:
        html = generate_html(output, cinema_screenings)
    else:
        html = generate_minimal_html(output, cinema_screenings)

    html_path = os.path.join(OUTPUT_DIR, f"{slug}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    status = "generated (rich)" if content else "generated (minimal)"
    print(f"    Saved: {slug}.json + {slug}.html [{status}]")
    return slug


def main(force=False, limit=None):
    """Batch process all movies."""
    print("=" * 60)
    print("  Movie Content Generator — ti-paizei-tora.gr")
    print("=" * 60)
    print(f"  Output: {OUTPUT_DIR}")
    print(f"  Force regenerate: {force}")
    if limit:
        print(f"  Limit: first {limit} movies")
    print()

    movies, cinemas_raw, flix_index, lifo_index = load_all_data()
    print(f"  Loaded {len(movies)} movies, {len(cinemas_raw)} cinema groups, {len(flix_index)} flix, {len(lifo_index)} lifo\n")

    if limit:
        movies = movies[:limit]
        cinemas_raw = cinemas_raw[:limit]

    stats = {"total": 0, "generated": 0, "skipped": 0, "errors": 0}

    for i, movie_db in enumerate(movies, 1):
        slug = movie_db.get("slug", "")
        greek_title = movie_db.get("greek_title", "Unknown")
        original_title = movie_db.get("original_title", "")

        stats["total"] += 1
        print(f"[{i}/{len(movies)}] {greek_title} ({original_title}) [{slug}]")

        if not slug:
            print("  SKIP: no slug")
            stats["errors"] += 1
            continue

        if not movie_db.get("athinorama_link"):
            print("  SKIP: no athinorama_link")
            stats["errors"] += 1
            continue

        if not should_regenerate(slug, movie_db, flix_index, lifo_index, force=force):
            print("  SKIP: ratings unchanged")
            stats["skipped"] += 1
            continue

        # Get cinema list for this movie (parallel arrays)
        cinema_list = cinemas_raw[i - 1] if i - 1 < len(cinemas_raw) else []

        try:
            process_single_movie(movie_db, flix_index, lifo_index, cinema_list)
            stats["generated"] += 1
            time.sleep(2)
        except Exception as e:
            print(f"  ERROR: {e}")
            stats["errors"] += 1

    print(f"\n{'=' * 60}")
    print(f"  DONE: {stats['generated']} generated, {stats['skipped']} skipped, {stats['errors']} errors (of {stats['total']} total)")
    print(f"{'=' * 60}")

    # Cleanup: remove cached content for movies no longer in movies.json
    current_slugs = {m.get("slug") for m in movies if m.get("slug")}
    removed = 0
    for filename in os.listdir(OUTPUT_DIR):
        if filename.endswith(".json") or filename.endswith(".html"):
            slug = filename.rsplit(".", 1)[0]
            if slug not in current_slugs:
                os.remove(os.path.join(OUTPUT_DIR, filename))
                removed += 1
    if removed:
        print(f"  Cleanup: removed {removed} stale files from generated_content/")


if __name__ == "__main__":
    _force = "--force" in sys.argv
    _limit = None
    for _arg in sys.argv[1:]:
        if _arg.startswith("--limit="):
            _limit = int(_arg.split("=")[1])

    # Single movie mode
    non_flag_args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if non_flag_args:
        movies, cinemas_raw, flix_index, lifo_index = load_all_data()
        target = normalize(non_flag_args[0])
        found = None
        found_idx = None
        for idx, m in enumerate(movies):
            if normalize(m.get("greek_title", "")) == target or \
               normalize(m.get("original_title", "")) == target:
                found = m
                found_idx = idx
                break
        if found:
            cinema_list = cinemas_raw[found_idx] if found_idx < len(cinemas_raw) else []
            print(f"Processing single movie: {found.get('greek_title')}")
            process_single_movie(found, flix_index, lifo_index, cinema_list)
        else:
            print(f"Movie not found: {non_flag_args[0]}")
            sys.exit(1)
    else:
        main(force=_force, limit=_limit)
