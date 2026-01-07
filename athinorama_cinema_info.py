import requests
from bs4 import BeautifulSoup
import json
import unicodedata
import re
from unidecode import unidecode
import os
import shutil
from pathlib import Path
from datetime import datetime
from datetime import timezone


BASE_URL = "https://ti-paizei-tora.gr"
MOVIE_DIR = "/home/grstathis/ti-paizei-tora.gr/movie"
REGION_DIR = "/home/grstathis/ti-paizei-tora.gr/region"  # Add region directory
OUTPUT_FILE = "/home/grstathis/ti-paizei-tora.gr/sitemap.xml"


# Read the Google API key from the file
with open("/home/grstathis/ti-paizei-tora.gr/google_api", "r") as file:
    GOOGLE_API_KEY = file.read().strip()
with open("/home/grstathis/ti-paizei-tora.gr/omdb_api", "r") as file:
    OMDB_API_KEY = file.read().strip()


def extract_movie_links():
    url = "https://www.athinorama.gr/cinema/guide/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    # Find all div elements with class "item horizontal card-item"
    movie_cards = soup.find_all("div", class_="item horizontal card-item")
    movie_links = []
    for card in movie_cards:
        # Find the link inside item-title div
        title_div = card.find("h2", class_="item-title")
        if title_div:
            link = title_div.find("a")
            if link and link.get("href"):
                movie_links.append(link["href"])

    return movie_links


def get_movie_times(url):
    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Find all inner-panel divs
    panels = soup.find_all("div", class_="panel-inner")

    results = []
    for panel in panels:
        # Get all elements with class daytimeschedule inside each inner-panel
        schedules = panel.find_all(class_="daytimeschedule")
        times = [s.get_text(strip=True) for s in schedules]
        if times:
            results.append(times)
    # Print extracted schedules
    for i, sched in enumerate(results, 1):
        print(f"Panel {i}: {sched}")


def get_movie_theater(url):
    # fetch the page
    response = requests.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # find all theater blocks
    theaters = []
    for title_tag, details_tag in zip(
        soup.find_all("h2", class_="item-title"),
        soup.find_all("div", class_="details"),
    ):
        name = title_tag.get_text(strip=True)
        address = details_tag.get_text(" ", strip=True)  # keep spacing
        theaters.append({"name": name, "address": address})

    # print results
    for t in theaters:
        print(f"{t['name']} - {t['address']}")


def is_greek(text):
    """Return True if text contains mostly Greek characters."""
    greek_chars = re.findall(r"[Α-Ωα-ωάέήίόύώΆΈΉΊΌΎΏ]", text)
    return len(greek_chars) > len(text) * 0.5  # >50% Greek letters = Greek text


def transliterate_greek_to_latin(text):
    """Convert Greek to Latin using unidecode if needed."""
    if is_greek(text):
        return unidecode(text)
    return text


def get_cinema_website_from_google_places(name: str, address: str = None):
    """Fetch cinema website URL from Google Places API."""
    import time

    # Step 1: Search for the place to get place_id
    search_query = name if not address else f"{name}, {address}"

    # First, try to find the place using Places Search API
    search_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    search_params = {
        "query": search_query,
        "key": GOOGLE_API_KEY,
        "language": "el",
        "type": "movie_theater",  # Specify we're looking for cinemas
    }

    try:
        search_response = requests.get(search_url, params=search_params)
        search_response.raise_for_status()
        search_data = search_response.json()

        if search_data["status"] != "OK" or not search_data.get("results"):
            print(f"⚠️ No place found for '{search_query}'")
            return {"website": None}

        # Get the first (most relevant) result
        place = search_data["results"][0]
        place_id = place.get("place_id")

        if not place_id:
            print(f"⚠️ No place_id found for '{search_query}'")
            return {"website": None}

        # Step 2: Get detailed information including website
        details_url = "https://maps.googleapis.com/maps/api/place/details/json"
        details_params = {
            "place_id": place_id,
            "fields": "website",  # Only request website field
            "key": GOOGLE_API_KEY,
            "language": "el",
        }

        # Add a small delay to respect API rate limits
        time.sleep(0.1)

        details_response = requests.get(details_url, params=details_params)
        details_response.raise_for_status()
        details_data = details_response.json()

        if details_data["status"] != "OK":
            print(
                f"⚠️ Could not get details for '{search_query}' (place_id: {place_id})"
            )
            return {"website": None}

        result = details_data.get("result", {})
        website = result.get("website")

        print(f"✅ Found info for '{name}': {website or 'No website'}")

        return {"website": website}

    except requests.exceptions.RequestException as e:
        print(f"❌ Request error for '{search_query}': {e}")
        return {"website": None}
    except Exception as e:
        print(f"❌ Unexpected error for '{search_query}': {e}")
        return {"website": None}


def get_cinema_info_from_google(name: str, address: str = None):
    """Fetch cinema info (lat, lon, area, formatted address) from Google Maps API."""
    query = name if not address else f"{name}, {address}"
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": query,
        "key": GOOGLE_API_KEY,
        "language": "el",  # or "en" depending on what you want
    }

    response = requests.get(url, params=params)
    data = response.json()

    if data["status"] != "OK" or not data["results"]:
        print(f"⚠️ Google Maps API: No match for '{query}'")
        return {"lat": None, "lon": None, "area": "Unknown", "formatted_address": None}

    result = data["results"][0]
    geometry = result["geometry"]["location"]
    address_components = result.get("address_components", [])

    # Try to extract area (e.g., neighborhood, locality, sublocality)
    area = "Unknown"
    # Extract broader area (default: locality)
    area = next(
        (c["long_name"] for c in address_components if "locality" in c["types"]),
        "Unknown",
    )

    formatted_addr = result.get("formatted_address")

    # 🧹 Step 3: Remove Greek street words and abbreviations
    first_part = re.sub(
        r"\b(Λ\.?|Λεωφόρος|Λεωφ\.?|Οδός|Οδ\.?|Δρόμος|Δρ\.?)\b",
        "",
        formatted_addr,
        flags=re.IGNORECASE,
    ).strip()

    # 🧹 Step 4: Keep only up to the first '&' or 'και' or '-' (e.g., "Συγγρού & Φραντζή" → "Συγγρού")
    first_part = re.split(r"\s*&\s*|\s*και\s*|\s*-\s*", first_part)[0].strip()

    # --- Geocoding ---
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": f"{first_part}", "format": "json", "addressdetails": 1, "limit": 1}

    r = requests.get(url, params=params, headers={"User-Agent": "cinema-app"})
    r.raise_for_status()
    data = r.json()
    if data:
        details = data[0].get("address", {})
        open_info_suburb = details.get("suburb")
        open_info_neighbourhood = details.get("neighbourhood")
    else:
        open_info_suburb = open_info_neighbourhood = ""

    return {
        "lat": geometry["lat"],
        "lon": geometry["lng"],
        "area": area,
        "suburb": open_info_suburb,
        "neighbourhood": open_info_neighbourhood,
        "formatted_address": formatted_addr,
    }


def geocode_area(address):
    # 🧹 Step 1: Remove parentheses and contents inside them
    cleaned = re.sub(r"\([^)]*\)", "", address).strip()

    # 🧹 Step 2: Keep only the first comma-separated part
    # first_part = cleaned.split(',')[0].strip()

    # 🧹 Step 3: Remove Greek street words and abbreviations
    first_part = re.sub(
        r"\b(Λ\.?|Λεωφόρος|Λεωφ\.?|Οδός|Οδ\.?|Δρόμος|Δρ\.?)\b",
        "",
        first_part,
        flags=re.IGNORECASE,
    ).strip()

    # 🧹 Step 4: Keep only up to the first '&' or 'και' or '-' (e.g., "Συγγρού & Φραντζή" → "Συγγρού")
    first_part = re.split(r"\s*&\s*|\s*και\s*|\s*-\s*", first_part)[0].strip()

    #     # 🧹 Step 5: Keep only first word and possible number (e.g. "Παπανδρέου 12")
    #     match = re.match(r'^([\wΆ-ώΑ-Ωά-ώ]+(?:\s*\d{1,3})?)', first_part)
    #     if match:
    #         query_base = match.group(1)
    #     else:
    #         query_base = first_part

    # 🧹 Step 6: Collapse spaces
    query_base = re.sub(r"\s+", " ", query_base).strip()

    # --- Geocoding ---
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": f"{query_base}", "format": "json", "addressdetails": 1, "limit": 1}

    #     print(f"Geocoding query: {params['q']}")

    try:
        r = requests.get(url, params=params, headers={"User-Agent": "cinema-app"})
        r.raise_for_status()
        data = r.json()
        if not data:
            return None

        details = data[0].get("address", {})
        area = (
            details.get("suburb")
            or details.get("neighbourhood")
            or details.get("city_district")
            or details.get("town")
            or details.get("city")
        )

        lat = data[0].get("lat")
        lon = data[0].get("lon")

        return {"area": area, "lat": lat, "lng": lon}

    except Exception as e:
        print(f"Error geocoding {address}: {e}")
        return None


def normalize_name(name: str) -> str:
    """Normalize and clean cinema name for reliable matching."""
    if not name:
        return ""
    # Normalize Unicode (remove accent inconsistencies)
    name = unicodedata.normalize("NFKC", name)
    # Remove invisible spaces, trim, and lowercase
    name = name.strip().replace("\u200b", "").replace("\xa0", " ").lower()
    return name


def load_cinema_database(
    filename="/home/grstathis/ti-paizei-tora.gr/cinema_database.json",
):
    """Load existing cinema database from file."""
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            print(f"⚠️ Warning: {filename} is empty or corrupted. Starting fresh.")
            return {}
    else:
        print(f"ℹ️ No existing {filename} found. Starting fresh.")
        return {}


def save_cinema_database(
    cinema_db, filename="/home/grstathis/ti-paizei-tora.gr/cinema_database.json"
):
    """Save cinema database to file."""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(cinema_db, f, ensure_ascii=False, indent=2)
    print(f"✅ Cinema database saved to {filename}")


def get_or_create_cinema_info(name, address, cinema_db):
    """
    Get cinema info from database or fetch from Google API if not exists.
    Now includes website information from Google Places API.
    Returns cinema info dict and updates the database.
    """
    # Create a unique key for the cinema
    norm_name = normalize_name(name)
    norm_address = normalize_name(address) if address else ""
    cinema_key = f"{norm_name}_{norm_address}"

    # Check if cinema already exists in database
    if cinema_key in cinema_db:
        existing_info = cinema_db[cinema_key]

        # Check if we already have complete info (including website)
        if "website" in existing_info:
            print(f"✅ Found cached info (with website) for: {name}")
            return existing_info
        else:
            print(f"🔄 Found cached location info for: {name}, fetching website...")
            # Get website info and merge with existing
            website_info = get_cinema_website_from_google_places(name, address)
            merged_info = {**existing_info, **website_info}
            cinema_db[cinema_key] = merged_info
            return merged_info

    # Cinema not found, fetch both location and website info
    print(f"🔍 Fetching new info (location + website) for: {name}")

    # Get location info from Google Maps Geocoding API
    location_dict = get_cinema_info_from_google(name, address)

    # Get website info from Google Places API
    website_dict = get_cinema_website_from_google_places(name, address)

    # Merge the information
    if location_dict:
        region_dict = {**location_dict, **website_dict}
    else:
        # Fallback if location info fails
        region_dict = {
            "lat": None,
            "lon": None,
            "area": "Unknown",
            "suburb": None,
            "neighbourhood": None,
            "formatted_address": address,
            **website_dict,
        }

    # Store in database (if value)
    if region_dict:
        cinema_db[cinema_key] = region_dict

    return region_dict


def get_movie_theater_times(url, cinema_db):
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    movies_data = []
    cinemas_data = []

    # --- Movie Titles ---
    title_greek_tag = soup.find("h1")
    title_greek = (
        title_greek_tag.get_text(strip=True) if title_greek_tag else "Unknown Title"
    )

    card = soup.find_all("ul", class_="review-details")
    for c in card:
        original_tag = c.find("span", class_="original-title")
        if original_tag:
            original_title = original_tag.get_text()
        else:
            original_title = ""

    imdb = soup.find("a", class_="imdb")
    imdb = imdb.get("href") if imdb else None

    movies_data.append(
        {
            "greek_title": title_greek,
            "original_title": original_title,
            "athinorama_link": url,
            "imdb_link": imdb,
        }
    )

    # --- Cinema Entries ---
    cinema_blocks = soup.find_all("div", class_="item card-item")
    for block in cinema_blocks:
        name_tag = block.find("h2", class_="item-title")
        details_tag = block.find("div", class_="details")
        name = name_tag.get_text(strip=True) if name_tag else None

        # Rooms
        rooms = []
        for panel in block.find_all("div", class_="grid schedule-grid"):
            room_name_tag = panel.find("span")
            room_name = (
                room_name_tag.get_text(strip=True) if room_name_tag else "Main Room"
            )
            rooms.append({"room": room_name})

        # Timetable
        room_timetable = []
        innerpanels = block.find_all("div", class_="panel-inner")
        for panel in innerpanels:
            schedules = panel.find_all(class_="daytimeschedule")
            times = [s.get_text(strip=True) for s in schedules]
            if times:
                room_timetable.append(times)

        address = details_tag.get_text(" ", strip=True) if details_tag else None
        # --- Get cinema info from cache or API ---
        region_dict = get_or_create_cinema_info(name, address, cinema_db)

        # Get values with safe .get() method, leveraging the dict guarantee
        final_area = region_dict.get("area", "Unknown")
        suburb = region_dict.get("suburb", "Unknown")
        neighbourhood = region_dict.get("neighbourhood", "Unknown")

        # 1. When area is "Αθηνα", list subarea if available, otherwise use "Αθηνα (Κεντρο)"
        if final_area == "Αθήνα":
            print(region_dict)
            # Check if suburb is not empty/None AND not the same as the main area
            if suburb and normalize_name(suburb) != normalize_name(final_area):
                final_area = suburb
            elif not suburb and normalize_name(neighbourhood) != normalize_name(
                final_area
            ):
                final_area = neighbourhood
            else:
                # This will act as the filter for all Athens cinemas
                final_area = "Αθήνα (Κέντρο)"

        # 2. Replace 'ampelokipi' with 'Αμπελοκηποι'
        if final_area == "Ampelokipi":
            final_area = "Αμπελόκηποι"

        cinemas_data.append(
            {
                "cinema": name,
                "address": region_dict["formatted_address"],
                "lat": region_dict["lat"],
                "lon": region_dict["lon"],
                "region": final_area,
                "subregion": region_dict["suburb"],
                "neighbourhood": region_dict["neighbourhood"],
                "website": region_dict["website"],
                "rooms": rooms,
                "timetable": room_timetable,
            }
        )

    return movies_data, cinemas_data


#### main routine here ####
movie_links = []

base_url = "https://www.athinorama.gr"
if __name__ == "__main__":
    links = extract_movie_links()
    for link in links:
        print(link)
        movie_links.append(base_url + link)

# Load cinema database at the start
cinema_database = load_cinema_database()

movies_l = []
cinemas_l = []


for url in movie_links:
    print(url)
    movie, cinema_t = get_movie_theater_times(url, cinema_database)
    movies_l.append(movie)
    cinemas_l.append(cinema_t)

# Save updated cinema database
save_cinema_database(cinema_database)

with open("/home/grstathis/ti-paizei-tora.gr/cinemas.json", "w", encoding="utf-8") as f:
    json.dump(cinemas_l, f, ensure_ascii=False, indent=2)

with open("/home/grstathis/ti-paizei-tora.gr/movies.json", "w", encoding="utf-8") as f:
    json.dump(movies_l, f, ensure_ascii=False, indent=2)

print("saved cinemas.json, movies.json files")

### create movie html folder ###

# --- Minimal HTML Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>{title}</title>
<style>
  body {{ font-family: Arial, sans-serif; background:#f5f5f5; padding:20px; }}
  .card {{ background:#fff; padding:16px; max-width:420px; margin:auto; border-radius:10px; 
           box-shadow:0 2px 6px rgba(0,0,0,0.15); }}
  img {{ width:100%; border-radius:6px; margin-bottom:12px; }}
  .title {{ font-size:22px; font-weight:bold; margin-bottom:6px; }}
  .year {{ color:#777; margin-bottom:12px; }}
  .plot {{ margin-bottom:16px; line-height:1.4; }}
</style>
</head>
<body>

<div class="card">
  <img src="{poster}" alt="Poster">
  <div class="title">{title}</div>
  <div class="year">{year} • {runtime}</div>
  <div class="plot">{plot}</div>
  <div><small>⭐ IMDb {rating}/10</small></div>

  <div style="margin-top:12px;">
    <a href="https://ti-paizei-tora.gr" target="_blank"
       style="color:#0066cc; text-decoration:none; font-size:14px;">
       🔗 ti-paizei-tora.gr
    </a>
  </div>

</div>

</body>
</html>
"""


# --- Load JSON ---
with open("/home/grstathis/ti-paizei-tora.gr/movies.json", "r", encoding="utf-8") as f:
    movies_data = json.load(f)


# --- Helper: slugify movie title ---
def slugify(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")  # remove accents
    text = re.sub(r"[^a-z0-9]+", "-", text)  # replace non-alphanum with -
    text = re.sub(r"-+", "-", text)  # remove duplicates
    return text.strip("-")


# --- Helper: extract IMDb ID ---
def extract_imdb_id(url: str):
    """Extract tt1234567 from an IMDb link."""
    match = re.search(r"(tt\d+)", url)
    return match.group(1) if match else None


# 🗑️ DELETE OLD MOVIE FOLDER BEFORE REBUILDING
movie_base_path = Path(MOVIE_DIR)
if os.path.exists(movie_base_path):
    print(f"🗑️ Deleting existing movie folder: {movie_base_path}")
    shutil.rmtree(movie_base_path)
    print(f"✅ Old movie folder removed")


# --- Main processing loop ---
for entry in movies_data:
    if not entry or not isinstance(entry, list):
        continue

    movie = entry[0]

    try:
        imdb_link = movie.get("imdb_link")
        imdb_id = extract_imdb_id(imdb_link)
    except Exception as e:
        print(f"Error extracting IMDb ID: {e}")
        continue
    if not imdb_id:
        print("Skipped movie (no IMDb ID):", movie)
        continue

    # Fetch from OMDb
    api_url = f"http://www.omdbapi.com/?i={imdb_id}&apikey={OMDB_API_KEY}"
    print("Fetching:", api_url)
    r = requests.get(api_url)
    data = r.json()

    if data.get("Response") != "True":
        print("OMDb error for", imdb_id, data)
        continue

    # Slug from Title
    title = data.get("Title", "unknown-movie")
    movie_slug = slugify(title)

    # 💾 Save slug back to the movie entry
    movie["slug"] = movie_slug

    # Build HTML with fallbacks
    html = HTML_TEMPLATE.format(
        title=data.get("Title", "Unknown"),
        poster=data.get("Poster", ""),
        year=data.get("Year", "—"),
        runtime=data.get("Runtime", "—"),
        plot=data.get("Plot", "No plot available."),
        rating=data.get("imdbRating", "—"),
    )

    # Output folder: movie/<movie-slug>/index.html
    out_dir = os.path.join(MOVIE_DIR, movie_slug)
    os.makedirs(out_dir, exist_ok=True)

    output_file = os.path.join(out_dir, "index.html")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

    print("Created:", output_file)

# 💾 Save updated movies.json with slugs
with open("/home/grstathis/ti-paizei-tora.gr/movies.json", "w", encoding="utf-8") as f:
    json.dump(movies_data, f, ensure_ascii=False, indent=2)

print("\nDone! All movie cards and folders generated.")

#### create html showtime subfolders ####

# Basic Greek -> Latin transliteration suitable for URL slugs
GREEK_TO_LATIN = {
    # lowercase
    "α": "a",
    "ά": "a",
    "β": "v",
    "γ": "g",
    "δ": "d",
    "ε": "e",
    "έ": "e",
    "ζ": "z",
    "η": "i",
    "ή": "i",
    "θ": "th",
    "ι": "i",
    "ί": "i",
    "ϊ": "i",
    "ΐ": "i",
    "κ": "k",
    "λ": "l",
    "μ": "m",
    "ν": "n",
    "ξ": "x",
    "ο": "o",
    "ό": "o",
    "π": "p",
    "ρ": "r",
    "σ": "s",
    "ς": "s",
    "τ": "t",
    "υ": "y",
    "ύ": "y",
    "ϋ": "y",
    "ΰ": "y",
    "φ": "f",
    "χ": "x",
    "ψ": "ps",
    "ω": "o",
    "ώ": "o",
    # uppercase
    "Α": "a",
    "Ά": "a",
    "Β": "v",
    "Γ": "g",
    "Δ": "d",
    "Ε": "e",
    "Έ": "e",
    "Ζ": "z",
    "Η": "i",
    "Ή": "i",
    "Θ": "th",
    "Ι": "i",
    "Ί": "i",
    "Ϊ": "i",
    "Κ": "k",
    "Λ": "l",
    "Μ": "m",
    "Ν": "n",
    "Ξ": "x",
    "Ο": "o",
    "Ό": "o",
    "Π": "p",
    "Ρ": "r",
    "Σ": "s",
    "Τ": "t",
    "Υ": "y",
    "Ύ": "y",
    "Ϋ": "y",
    "Φ": "f",
    "Χ": "x",
    "Ψ": "ps",
    "Ω": "o",
    "Ώ": "o",
}


def transliterate_greek(text: str) -> str:
    return "".join(GREEK_TO_LATIN.get(ch, ch) for ch in text)


def slugify(text: str) -> str:
    text = transliterate_greek(text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text


def parse_showtime(showtime_str: str):
    """Parse showtime string like 'Κυριακή 07 Δεκ. 16:00' to extract date and time"""
    # Extract date and time using regex
    match = re.search(
        r"(\d{1,2})\s+([Α-Ωα-ωάέίόήύώΆΈΉΊΌΎΏ\.]+)\s+(\d{2}):(\d{2})", showtime_str
    )

    if match:
        day = match.group(1).zfill(2)
        month_str = match.group(2).replace(".", "").strip()
        hour = match.group(3)
        minute = match.group(4)

        # Greek month mapping
        greek_months = {
            "Ιαν": "01",
            "Φεβ": "02",
            "Μαρ": "03",
            "Απρ": "04",
            "Μαΐ": "05",
            "Ιουν": "06",
            "Ιουλ": "07",
            "Αυγ": "08",
            "Σεπ": "09",
            "Οκτ": "10",
            "Νοε": "11",
            "Δεκ": "12",
        }

        month = greek_months.get(month_str, "01")
        current_year = datetime.now().year

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

    return None


def is_future_showtime(parsed_showtime):
    """
    Check if a showtime is in the future.
    Matches JS logic: filterPastTimesFromToday()
    """
    if not parsed_showtime:
        return False

    now = datetime.now()
    today_date = now.date()
    now_mins = now.hour * 60 + now.minute

    # Create datetime for the showtime
    showtime_date = datetime(
        parsed_showtime["year"], parsed_showtime["month"], parsed_showtime["day"]
    ).date()

    # If date is before today, filter it out
    if showtime_date < today_date:
        return False

    # If it's today, check if the time has passed
    if showtime_date == today_date:
        showtime_mins = parsed_showtime["hour"] * 60 + parsed_showtime["minute"]
        # Only show future times for today
        if showtime_mins < now_mins:
            return False

    # Keep future dates and future times for today
    return True


def flatten_timetable(timetable):
    """Flatten nested timetable array, similar to JavaScript .flat()"""
    if not timetable:
        return []

    flattened = []
    for item in timetable:
        if isinstance(item, list):
            flattened.extend(item)
        else:
            flattened.append(item)

    return flattened


def create_showtime_html_fallback(movie, cinema, parsed_showtime):
    """
    FALLBACK: Generate complete HTML when movie HTML doesn't exist
    """

    # Prepare movie title display
    movie_title_display = movie.get("greek_title", "")
    if movie.get("original_title") and movie.get("original_title").strip() not in [
        "",
        "/",
    ]:
        movie_title_display += f" ({movie.get('original_title').rstrip('/ ').strip()})"

    # Format showtime
    showtime_formatted = parsed_showtime["time"].replace("-", ":")
    date_formatted = parsed_showtime["full"]

    # Build external links
    external_links = []
    if movie.get("athinorama_link"):
        external_links.append(
            f'<a href="{movie["athinorama_link"]}" target="_blank" class="external-link">Athinorama</a>'
        )
    if movie.get("imdb_link"):
        external_links.append(
            f'<a href="{movie["imdb_link"]}" target="_blank" class="external-link">IMDb</a>'
        )

    # Build cinema location link
    maps_query = f"{cinema.get('cinema', '')} {cinema.get('address', '')}"
    maps_link = f"https://www.google.com/maps/search/?api=1&query={maps_query.replace(' ', '+')}"

    # Get rooms info
    rooms_info = ""
    if cinema.get("rooms"):
        rooms_list = [
            room.get("room", "") for room in cinema["rooms"] if room.get("room")
        ]
        if rooms_list:
            rooms_info = f"<p><strong>Αίθουσα:</strong> {', '.join(rooms_list)}</p>"

    html_content = f"""<!DOCTYPE html>
<html lang="el">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{movie_title_display} - {cinema.get('cinema', '')} - {showtime_formatted}</title>
    <meta name="description" content="Προβολή της ταινίας {movie_title_display} στο {cinema.get('cinema', '')} στις {date_formatted}">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 1.8em;
            margin-bottom: 10px;
        }}
        .showtime-badge {{
            display: inline-block;
            background: rgba(255,255,255,0.2);
            padding: 8px 20px;
            border-radius: 20px;
            font-size: 1.2em;
            font-weight: bold;
            margin-top: 10px;
        }}
        .content {{
            padding: 30px;
        }}
        .section {{
            margin-bottom: 30px;
        }}
        .section h2 {{
            color: #667eea;
            font-size: 1.3em;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #f0f0f0;
        }}
        .info-grid {{
            display: grid;
            gap: 15px;
        }}
        .info-item {{
            padding: 12px;
            background: #f9f9f9;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        .info-item strong {{
            color: #667eea;
            display: block;
            margin-bottom: 5px;
        }}
        .external-links {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 15px;
        }}
        .external-link {{
            display: inline-block;
            padding: 10px 20px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 500;
            transition: background 0.3s;
        }}
        .external-link:hover {{
            background: #5568d3;
        }}
        .location-link {{
            display: inline-block;
            padding: 12px 24px;
            background: #28a745;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 500;
            margin-top: 10px;
            transition: background 0.3s;
        }}
        .location-link:hover {{
            background: #218838;
        }}
        .location-link:before {{
            content: "📍 ";
        }}
        @media (max-width: 600px) {{
            body {{
                padding: 10px;
            }}
            .header {{
                padding: 20px;
            }}
            .header h1 {{
                font-size: 1.4em;
            }}
            .content {{
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎬 {movie_title_display}</h1>
            <div class="showtime-badge">🕒 {showtime_formatted}</div>
        </div>
        
        <div class="content">
            <div class="section">
                <h2>📽️ Πληροφορίες Ταινίας</h2>
                <div class="info-grid">
                    <div class="info-item">
                        <strong>Ελληνικός Τίτλος</strong>
                        {movie.get('greek_title', 'Μη διαθέσιμο')}
                    </div>
                    {f'''<div class="info-item">
                        <strong>Πρωτότυπος Τίτλος</strong>
                        {movie.get('original_title').rstrip('/ ').strip()}
                    </div>''' if movie.get('original_title') and movie.get('original_title').strip() not in ['', '/'] else ''}
                </div>
                {f'<div class="external-links">{" ".join(external_links)}</div>' if external_links else ''}
            </div>
            
            <div class="section">
                <h2>🎭 Κινηματογράφος</h2>
                <div class="info-grid">
                    <div class="info-item">
                        <strong>Όνομα</strong>
                        {cinema.get('cinema', 'Μη διαθέσιμο')}
                        {f' - <a href="{cinema["website"]}" target="_blank">Ιστοσελίδα</a>' if cinema.get('website') else ''}
                    </div>
                    <div class="info-item">
                        <strong>Διεύθυνση</strong>
                        {cinema.get('address', 'Μη διαθέσιμη')}
                    </div>
                    {f'''<div class="info-item">
                        <strong>Περιοχή</strong>
                        {cinema['region']}{f' - {cinema["subregion"]}' if cinema.get('subregion') else ''}{f' ({cinema["neighbourhood"]})' if cinema.get('neighbourhood') else ''}
                    </div>''' if cinema.get('region') else ''}
                </div>
                <a href="{maps_link}" target="_blank" class="location-link">Δες στο Google Maps</a>
            </div>
            
            <div class="section">
                <h2>⏰ Προβολή</h2>
                <div class="info-grid">
                    <div class="info-item">
                        <strong>Ημερομηνία & Ώρα</strong>
                        {date_formatted}
                    </div>
                    {rooms_info}
                </div>
            </div>
        </div>
    </div>
</body>
</html>"""

    return html_content


def inject_cinema_showtime_info(movie_html, cinema, parsed_showtime, movie):
    """
    Inject cinema and showtime information into the existing movie HTML
    """
    if not movie_html:
        return None

    # Format showtime
    showtime_formatted = parsed_showtime["time"].replace("-", ":")
    date_formatted = parsed_showtime["full"]

    # Build cinema location link
    maps_query = f"{cinema.get('cinema', '')} {cinema.get('address', '')}"
    maps_link = f"https://www.google.com/maps/search/?api=1&query={maps_query.replace(' ', '+')}"

    # Get rooms info
    rooms_html = ""
    if cinema.get("rooms"):
        rooms_list = [
            room.get("room", "") for room in cinema["rooms"] if room.get("room")
        ]
        if rooms_list:
            rooms_html = f"<div><small>Αίθουσα: {', '.join(rooms_list)}</small></div>"

    # Movie title for meta update
    movie_title_display = movie.get("greek_title", "")
    if movie.get("original_title") and movie.get("original_title").strip() not in [
        "",
        "/",
    ]:
        movie_title_display += f" ({movie.get('original_title').rstrip('/ ').strip()})"

    # Create cinema and showtime section HTML
    cinema_showtime_section = f"""
  <!-- Cinema & Showtime Information -->
  <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 24px; border-radius: 10px; margin-bottom: 20px;">
    <h3 style="margin: 0 0 16px 0; font-size: 1.4em;">🎭 Προβολή</h3>
    <div style="background: rgba(255,255,255,0.1); padding: 16px; border-radius: 8px; margin-bottom: 12px;">
      <div style="font-size: 1.8em; font-weight: bold; margin-bottom: 8px;">🕒 {showtime_formatted}</div>
      <div style="font-size: 1.1em; opacity: 0.9;">{date_formatted}</div>
      {rooms_html}
    </div>
    
    <div style="background: rgba(255,255,255,0.1); padding: 16px; border-radius: 8px;">
      <h4 style="margin: 0 0 12px 0; font-size: 1.2em;">📍 Κινηματογράφος</h4>
      <div style="font-size: 1.1em; margin-bottom: 8px;">
        <strong>{cinema.get('cinema', 'Μη διαθέσιμο')}</strong>
        {f' - <a href="{cinema["website"]}" target="_blank" style="color: white; text-decoration: underline;">Ιστοσελίδα</a>' if cinema.get('website') else ''}
      </div>
      <div style="margin-bottom: 8px;">{cinema.get('address', 'Μη διαθέσιμη')}</div>
      {f'<div style="font-size: 0.95em; opacity: 0.9;">{cinema["region"]}" - {cinema["subregion"]}"'}
      <a href="{maps_link}" target="_blank" style="display: inline-block; margin-top: 12px; padding: 10px 20px; background: rgba(255,255,255,0.9); color: #667eea; text-decoration: none; border-radius: 6px; font-weight: bold;">📍 Δες στο Google Maps</a>
    </div>
  </div>
"""

    # Update the title tag
    new_title = (
        f"{movie_title_display} - {cinema.get('cinema', '')} - {showtime_formatted}"
    )
    movie_html = re.sub(
        r"<title>.*?</title>", f"<title>{new_title}</title>", movie_html
    )

    # Update meta description
    new_description = f"Προβολή της ταινίας {movie_title_display} στο {cinema.get('cinema', '')} στις {date_formatted}"
    if '<meta name="description"' in movie_html:
        movie_html = re.sub(
            r'<meta name="description"[^>]*>',
            f'<meta name="description" content="{new_description}">',
            movie_html,
        )
    else:
        # Add meta description after charset
        movie_html = movie_html.replace(
            '<meta charset="UTF-8" />',
            f'<meta charset="UTF-8" />\n<meta name="description" content="{new_description}">',
        )

    # Inject cinema/showtime section after the opening <body> tag or after the first div.card
    if '<div class="card">' in movie_html:
        # Insert right after opening of .card div
        movie_html = movie_html.replace(
            '<div class="card">', f'<div class="card">\n{cinema_showtime_section}', 1
        )
    elif "<body>" in movie_html:
        # Fallback: insert after body tag
        movie_html = movie_html.replace(
            "<body>", f"<body>\n{cinema_showtime_section}", 1
        )

    return movie_html


def create_cinema_structure():
    """Create folder structure: .region/{region}/cinema/{cinema}/movie/{movie}/date/showtime.html"""

    # Load JSON files
    with open(
        "/home/grstathis/ti-paizei-tora.gr/movies.json", "r", encoding="utf-8"
    ) as f:
        movies_data = json.load(f)

    with open(
        "/home/grstathis/ti-paizei-tora.gr/cinemas.json", "r", encoding="utf-8"
    ) as f:
        cinemas_data = json.load(f)

    base_path = Path(REGION_DIR)

    # 🗑️ DELETE OLD STRUCTURE BEFORE REBUILDING
    if base_path.exists():
        print(f"🗑️  Deleting existing folder structure: {base_path}")
        shutil.rmtree(base_path)
        print(f"✅ Old structure removed")

    base_path.mkdir(exist_ok=True)

    stats = {
        "total_movies": 0,
        "total_cinemas": 0,
        "total_showtimes": 0,
        "skipped_no_timetable": 0,
        "skipped_empty_timetable": 0,
        "skipped_past_times": 0,
        "used_movie_html": 0,
        "used_fallback_html": 0,
        "movies_processed": [],
    }

    # Loop through movies and their corresponding cinemas
    for movie_idx, (movie_list, cinema_list) in enumerate(
        zip(movies_data, cinemas_data)
    ):
        if not movie_list or not cinema_list:
            continue

        movie = movie_list[0]
        stats["total_movies"] += 1

        # Determine which title to use for folder structure
        movie_title = movie.get("original_title", "").strip()
        if not movie_title or movie_title == "/":
            movie_title = movie.get("greek_title", "").strip()

        # Clean up trailing slashes and extra spaces
        movie_title = movie_title.rstrip("/ ").strip()
        movie_slug = movie.get("slug", "").strip()

        # Fallback: if no slug exists, generate one
        if not movie_slug:
            movie_title = movie.get("original_title", "").strip()
            if not movie_title or movie_title == "/":
                movie_title = movie.get("greek_title", "").strip()
            movie_title = movie_title.rstrip("/ ").strip()
            movie_slug = slugify(movie_title)

        # ✅ Try to load the existing movie HTML (OPTIONAL)
        movie_html_path = Path("movie") / movie_slug / "index.html"
        base_movie_html = None
        use_fallback = False

        if movie_html_path.exists():
            try:
                with open(movie_html_path, "r", encoding="utf-8") as f:
                    base_movie_html = f.read()
            except Exception as e:
                print(f"⚠️  Could not read movie HTML for {movie_title}: {e}")
                use_fallback = True
        else:
            use_fallback = True

        # ✅ SAME AS JS: Filter valid cinemas first
        valid_cinemas = []
        for cinema in cinema_list:
            # Check if cinema has required fields
            if not cinema.get("region") or not cinema.get("cinema"):
                continue

            # ✅ MATCH JS LOGIC: c.timetable && c.timetable.flat().length > 0
            timetable = cinema.get("timetable")

            # Skip if no timetable property
            if not timetable:
                stats["skipped_no_timetable"] += 1
                continue

            # Flatten and check if it has content
            flattened = flatten_timetable(timetable)
            if len(flattened) == 0:
                stats["skipped_empty_timetable"] += 1
                continue

            valid_cinemas.append(cinema)

        # ✅ SAME AS JS: if (regionFiltered.length === 0) return;
        if len(valid_cinemas) == 0:
            continue

        cinemas_for_movie = 0
        showtimes_for_movie = 0

        # Loop through valid cinemas only
        for cinema in valid_cinemas:
            region_slug = slugify(cinema["region"])
            cinema_slug = slugify(cinema["cinema"])

            # Collect all valid parsed showtimes
            valid_showtimes = []
            timetable = cinema.get("timetable", [])

            for showtime_list in timetable:
                if not showtime_list:  # Skip empty lists
                    continue
                for showtime in showtime_list:
                    if not showtime or not showtime.strip():  # Skip empty strings
                        continue

                    parsed = parse_showtime(showtime)

                    # ✅ Skip past dates and times
                    if not is_future_showtime(parsed):
                        stats["skipped_past_times"] += 1
                        continue

                    if parsed:
                        valid_showtimes.append(parsed)

            # Only create folders if we have valid future showtimes
            if not valid_showtimes:
                continue

            cinemas_for_movie += 1

            # Create region/cinema/movie folder structure
            movie_path = (
                base_path / region_slug / "cinema" / cinema_slug / "movie" / movie_slug
            )
            movie_path.mkdir(parents=True, exist_ok=True)

            # Write all the valid showtimes as HTML files
            for parsed in valid_showtimes:
                showtimes_for_movie += 1

                # Create date folder
                date_path = movie_path / parsed["date"]
                date_path.mkdir(parents=True, exist_ok=True)

                # Create showtime HTML file
                showtime_file = date_path / f"{parsed['time']}.html"

                # ✅ Use movie HTML if available, otherwise use fallback
                if base_movie_html and not use_fallback:
                    # Inject cinema and showtime info into existing movie HTML
                    showtime_html = inject_cinema_showtime_info(
                        base_movie_html, cinema, parsed, movie
                    )
                    stats["used_movie_html"] += 1
                else:
                    # Generate complete HTML from scratch
                    showtime_html = create_showtime_html_fallback(movie, cinema, parsed)
                    stats["used_fallback_html"] += 1

                if showtime_html:
                    # Write HTML file
                    with open(showtime_file, "w", encoding="utf-8") as f:
                        f.write(showtime_html)

        stats["total_cinemas"] += cinemas_for_movie
        stats["total_showtimes"] += showtimes_for_movie

        if cinemas_for_movie > 0:  # Only log movies that have actual showtimes
            stats["movies_processed"].append(
                {
                    "title": movie_title,
                    "slug": movie_slug,
                    "cinemas": cinemas_for_movie,
                    "showtimes": showtimes_for_movie,
                }
            )
            print(
                f"✅ {movie_title}: {cinemas_for_movie} cinemas, {showtimes_for_movie} showtimes"
            )

    print(f"\n📊 Summary:")
    print(f"   Movies processed: {stats['total_movies']}")
    print(f"   Total cinema entries: {stats['total_cinemas']}")
    print(f"   Total HTML pages created: {stats['total_showtimes']}")
    print(f"   Used existing movie HTML: {stats['used_movie_html']}")
    print(f"   Used fallback HTML: {stats['used_fallback_html']}")
    print(f"   Skipped (no timetable): {stats['skipped_no_timetable']}")
    print(f"   Skipped (empty timetable): {stats['skipped_empty_timetable']}")
    print(f"   Skipped (past times): {stats['skipped_past_times']}")

    return stats


# Run the function
stats = create_cinema_structure()


def generate_sitemap():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    urls = []

    # --- Homepage ---
    urls.append(
        f"""
  <url>
    <loc>{BASE_URL}/</loc>
    <lastmod>{now}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
"""
    )

    # --- Contact page ---
    urls.append(
        f"""
  <url>
    <loc>{BASE_URL}/contact.html</loc>
    <lastmod>{now}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
"""
    )

    # --- Static JSON resources ---
    for resource in ["movies.json", "cinemas.json", "ti_paizei_tora_logo.svg"]:
        urls.append(
            f"""
  <url>
    <loc>{BASE_URL}/{resource}</loc>
    <lastmod>{now}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.6</priority>
  </url>
"""
        )

    # --- Movie folders ---
    for folder in sorted(os.listdir(MOVIE_DIR)):
        full_path = os.path.join(MOVIE_DIR, folder)
        index_file = os.path.join(full_path, "index.html")

        # Only include folders that contain index.html
        if os.path.isdir(full_path) and os.path.isfile(index_file):
            urls.append(
                f"""
  <url>
    <loc>{BASE_URL}/movie/{folder}/</loc>
    <lastmod>{now}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>
"""
            )

    # --- Region folder structure (showtime pages) ---
    if os.path.exists(REGION_DIR):
        for root, dirs, files in os.walk(REGION_DIR):
            for file in files:
                if file.endswith(".html"):
                    # Get full file path
                    full_file_path = os.path.join(root, file)

                    # Create relative path from REGION_DIR
                    relative_path = os.path.relpath(full_file_path, REGION_DIR)

                    # Convert to URL path (replace backslashes with forward slashes for Windows compatibility)
                    url_path = relative_path.replace("\\", "/")

                    # Build the full URL
                    page_url = f"{BASE_URL}/region/{url_path}"

                    urls.append(
                        f"""
  <url>
    <loc>{page_url}</loc>
    <lastmod>{now}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>
"""
                    )

    # --- Write final XML ---
    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset 
  xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
  xmlns:xhtml="http://www.w3.org/1999/xhtml">
{''.join(urls)}
</urlset>
"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(sitemap)

    print(f"Sitemap generated: {OUTPUT_FILE}")
    print(f"Total URLs: {len(urls)}")


generate_sitemap()
