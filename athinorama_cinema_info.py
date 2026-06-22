import json
import os
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from unidecode import unidecode

BASE_URL = "https://ti-paizei-tora.gr"

BASE_DIR = "/home/grstathis/ti-paizei-tora.gr"
MOVIE_DIR = os.path.join(BASE_DIR, "movie")
REGION_DIR = os.path.join(BASE_DIR, "region")
OUTPUT_FILE = os.path.join(BASE_DIR, "sitemap.xml")


# Read the Google API key from the file
with open(os.path.join(BASE_DIR, "google_api"), "r") as file:
    GOOGLE_API_KEY = file.read().strip()
with open(os.path.join(BASE_DIR, "omdb_api"), "r") as file:
    OMDB_API_KEY = file.read().strip()
with open(os.path.join(BASE_DIR, "tmdb_api"), "r") as file:
    TMDB_API_KEY = file.read().strip()


def extract_movie_links():
    url = "https://www.athinorama.gr/cinema/guide/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
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
                movie_links.append(
                    link["href"].replace("\n", " ").replace("\r", "").replace(" ", "")
                )

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
        return {
            "lat": None,
            "lon": None,
            "area": "Unknown",
            "formatted_address": None,
        }

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

    # 🧹 Step 4: Keep only up to the first '&' or 'και' or '-'
    # (e.g., "Συγγρού & Φραντζή" → "Συγγρού")
    first_part = re.split(r"\s*&\s*|\s*και\s*|\s*-\s*", first_part)[0].strip()

    # --- Geocoding ---
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": f"{first_part}",
        "format": "json",
        "addressdetails": 1,
        "limit": 1,
    }

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
    # Step 1: Remove parentheses and contents inside them
    cleaned = re.sub(r"\([^)]*\)", "", address).strip()

    # Step 2: Keep only the first comma-separated part
    first_part = cleaned.split(",")[0].strip()

    # Step 3: Remove Greek street words and abbreviations
    first_part = re.sub(
        r"\b(Λ\.?|Λεωφόρος|Λεωφ\.?|Οδός|Οδ\.?|Δρόμος|Δρ\.?)\b",
        "",
        first_part,
        flags=re.IGNORECASE,
    ).strip()

    # Step 4: Keep only up to the first '&' or 'και' or '-'
    # (e.g., "Συγγρού & Φραντζή" → "Συγγρού")
    first_part = re.split(r"\s*&\s*|\s*και\s*|\s*-\s*", first_part)[0].strip()

    # Step 5: Keep only first word and possible number
    # (e.g. "Παπανδρέου 12")
    # match = re.match(r'^([\wΆ-ώΑ-Ωά-ώ]+(?:\s*\d{1,3})?)', first_part)
    # if match:
    #     query_base = match.group(1)
    # else:
    #     query_base = first_part
    query_base = first_part

    # Step 6: Collapse spaces
    query_base = re.sub(r"\s+", " ", query_base).strip()

    # --- Geocoding ---
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": f"{query_base}",
        "format": "json",
        "addressdetails": 1,
        "limit": 1,
    }

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
    filename=None,
):
    """Load existing cinema database from file."""
    if filename is None:
        filename = os.path.join(BASE_DIR, "cinema_database.json")
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


def save_cinema_database(cinema_db, filename=None):
    """Save cinema database to file."""
    if filename is None:
        filename = os.path.join(BASE_DIR, "cinema_database.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(cinema_db, f, ensure_ascii=False, indent=2)
    print(f"✅ Cinema database saved to {filename}")


def get_or_create_cinema_info(name, address, cinema_db, is_summer_cinema=None):
    """
    Get cinema info from database or fetch from Google API if not exists.
    Now includes website information from Google Places API.
    Returns cinema info dict and updates the database.

    Args:
        name: Cinema name
        address: Cinema address
        cinema_db: Cinema database dictionary
        is_summer_cinema: Boolean flag for summer cinema status (updates DB if provided)
    """
    # Create a unique key for the cinema
    norm_name = normalize_name(name)
    norm_address = normalize_name(address) if address else ""
    cinema_key = f"{norm_name}_{norm_address}"

    # Check if cinema already exists in database
    if cinema_key in cinema_db:
        existing_info = cinema_db[cinema_key]

        # Update summer cinema flag if provided
        if is_summer_cinema is not None and existing_info.get("is_summer_cinema") != is_summer_cinema:
            print(f"🌞 Updating summer cinema status for: {name}")
            existing_info["is_summer_cinema"] = is_summer_cinema
            cinema_db[cinema_key] = existing_info

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

    # Add summer cinema flag if provided
    if is_summer_cinema is not None:
        region_dict["is_summer_cinema"] = is_summer_cinema

    # Store in database (if value)
    if region_dict:
        cinema_db[cinema_key] = region_dict

    return region_dict


def get_movie_theater_times(url, cinema_db):
    cinemas_data = []
    movies_data = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html, application/xhtml+xml, application/xml;q=0.9,"
            "image/avif, image/webp, image/apng, */*;q=0.8"
        ),
        "Accept-Language": "el-GR, el;q=0.9, en;q=0.8",
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # --- Movie Titles ---
    title_greek_tag = soup.find("h1")
    title_greek = (
        title_greek_tag.get_text(strip=True) if title_greek_tag else "Unknown Title"
    )

    # --- Extract Review Details ---
    original_title = ""
    year = ""
    color = ""
    duration = ""
    rating_age = ""
    rating_stars = None

    review_details = soup.find("ul", class_="review-details")
    if review_details:
        # Original title
        original_tag = review_details.find("span", class_="original-title")
        if original_tag:
            original_title = original_tag.get_text(strip=True)

        # Year
        year_tag = review_details.find("span", class_="year")
        if year_tag:
            year = year_tag.get_text(strip=True)

        # Color (black & white or color)
        color_tag = review_details.find("span", class_="color")
        if color_tag:
            color = color_tag.get_text(strip=True)

        # Duration
        duration_tag = review_details.find("span", class_="duration")
        if duration_tag:
            duration = duration_tag.get_text(strip=True)

        # Age rating (Κ-12, etc.)
        appropriate_tag = review_details.find("span", class_="appropriate")
        if appropriate_tag:
            rating_age = appropriate_tag.get_text(strip=True)

        # Star rating
        rating_div = review_details.find("div", class_="rating-stars")
        if rating_div:
            rating_value_tag = rating_div.find("span", class_="rating-value")
            if rating_value_tag:
                try:
                    # Replace comma with dot for Greek decimal format
                    rating_text = rating_value_tag.get_text(strip=True).replace(
                        ",", "."
                    )
                    rating_stars = float(rating_text)
                except ValueError:
                    rating_stars = None

    # --- Extract Tags (genres and nationality) ---
    movie_type = ""
    movie_country = ""
    review_tags = soup.find("ul", class_="review-tags")
    if review_tags:
        tag_items = review_tags.find_all("li")
        tags_list = []
        for tag_item in tag_items:
            tag_link = tag_item.find("a")
            if tag_link:
                tags_list.append(tag_link.get_text(strip=True))

        # First tag is movie type (genre), second is country
        if len(tags_list) >= 1:
            movie_type = tags_list[0]
        if len(tags_list) >= 2:
            movie_country = tags_list[1]

    # --- IMDb Link ---
    imdb = soup.find("a", class_="imdb")
    imdb = imdb.get("href") if imdb else None

    movies_data.append(
        {
            "greek_title": title_greek,
            "original_title": original_title,
            "year": year,
            "color": color,
            "duration": duration,
            "rating_age": rating_age,
            "rating_stars": rating_stars,
            "movie_type": movie_type,
            "movie_country": movie_country,
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

        # Check for summer cinema (Θερινός) indicator
        is_summer_cinema = False
        description_div = block.find("div", class_="item-description")
        if description_div:
            # Look for the tags div which contains cinema metadata
            tags_div = description_div.find("div", class_="tags")
            if tags_div:
                # Check if any span contains "Θερινός" text
                for span in tags_div.find_all("span"):
                    if span.get_text(strip=True) == "Θερινός" or "Θερινός" in span.get_text():
                        is_summer_cinema = True
                        break

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
        region_dict = get_or_create_cinema_info(name, address, cinema_db, is_summer_cinema)

        # Get values with safe .get() method, leveraging the dict guarantee
        final_area = region_dict.get("area", "Unknown")
        suburb = region_dict.get("suburb", "Unknown")
        neighbourhood = region_dict.get("neighbourhood", "Unknown")

        # 1. When area is "Αθηνα", list subarea if available,
        # otherwise use "Αθηνα (Κεντρο)"
        if final_area == "Αθήνα":
            print(region_dict)
            # Check if suburb is not empty/None AND not the same as
            # the main area
            if suburb and normalize_name(suburb) != normalize_name(final_area):
                final_area = suburb
            elif neighbourhood and normalize_name(neighbourhood) != normalize_name(
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
                "address": region_dict.get("formatted_address"),
                "lat": region_dict.get("lat"),
                "lon": region_dict.get("lon"),
                "region": final_area,
                "subregion": region_dict.get("suburb"),
                "neighbourhood": region_dict.get("neighbourhood"),
                "website": region_dict.get("website"),
                "rooms": rooms,
                "timetable": room_timetable,
                "is_summer_cinema": region_dict.get("is_summer_cinema", False),
            }
        )

    # Deduplicate cinemas by name - Athinorama sometimes lists the same cinema twice
    seen_cinemas = set()
    unique_cinemas = []
    for cinema in cinemas_data:
        cinema_key = normalize_name(cinema.get("cinema", ""))
        if cinema_key in seen_cinemas:
            continue
        seen_cinemas.add(cinema_key)
        unique_cinemas.append(cinema)
    cinemas_data = unique_cinemas

    return movies_data, cinemas_data


# Main routine here
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

# Calculate total cinema counts for each movie to determine popular movies
print("Calculating popular movies based on cinema count...")
movie_cinema_counts = {}
for movie_idx, cinema_list in enumerate(cinemas_l):
    # Count cinemas that have valid timetables with actual showtime strings
    valid_cinema_count = len(
        [c for c in cinema_list if c.get("timetable") and any(
            s for sublist in c["timetable"] for s in sublist if s and s.strip()
        )]
    )
    movie_cinema_counts[movie_idx] = valid_cinema_count

# Find the maximum cinema count
max_count = max(movie_cinema_counts.values()) if movie_cinema_counts else 0
print(f"Maximum cinema count: {max_count}")

# Add total_cinema_count and is_popular fields to each movie
for movie_idx, movie_list in enumerate(movies_l):
    cinema_count = movie_cinema_counts.get(movie_idx, 0)
    # movie_list is a list containing one dict, so we add fields to movie_list[0]
    if movie_list:  # Check if list is not empty
        movie_list[0]["total_cinema_count"] = cinema_count
        # Mark as popular if it has the max count and the count is greater than 1
        movie_list[0]["is_popular"] = cinema_count == max_count and max_count > 1
        if movie_list[0]["is_popular"]:
            title = movie_list[0]["greek_title"]
            print(f"Popular movie: {title} ({cinema_count} cinemas)")

with open(os.path.join(BASE_DIR, "cinemas.json"), "w", encoding="utf-8") as f:
    json.dump(cinemas_l, f, ensure_ascii=False, indent=2)

with open(os.path.join(BASE_DIR, "movies.json"), "w", encoding="utf-8") as f:
    json.dump(movies_l, f, ensure_ascii=False, indent=2)

print("saved cinemas.json, movies.json files")

# Create movie html folder

# --- Minimal HTML Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>{title}</title>
<style>
  body {{ font-family: Arial, sans-serif; background:#f5f5f5; \
padding:20px; }}
  .card {{ background:#fff; padding:16px; max-width:420px; \
margin:auto; border-radius:10px;
           box-shadow:0 2px 6px rgba(0, 0, 0, 0.15); }}
  img {{ width:100%; border-radius:6px; margin-bottom:12px; }}
  .title {{ font-size:22px; font-weight:bold; margin-bottom:6px; }}
  .year {{ color:#777; margin-bottom:12px; }}
  .plot {{ margin-bottom:16px; line-height:1.4; }}
  .review-links {{ margin-top:12px; display:flex; gap:8px; flex-wrap:wrap; }}
  .review-link {{ display:inline-block; padding:6px 12px; background:#f0f0f0; \
color:#333; text-decoration:none; border-radius:6px; font-size:13px; \
transition:background 0.2s; }}
  .review-link:hover {{ background:#e0e0e0; }}
  .home-link {{ margin-top:16px; text-align:center; }}
  .home-button {{ display:inline-block; padding:12px 24px; background:#667eea; \
color:white; text-decoration:none; border-radius:8px; font-size:16px; \
font-weight:600; transition:all 0.3s; box-shadow:0 2px 8px rgba(102,126,234,0.3); }}
  .home-button:hover {{ background:#5568d3; transform:translateY(-2px); \
box-shadow:0 4px 12px rgba(102,126,234,0.4); }}
</style>
</head>
<body>

<div class="card">
  <img src="{poster}" alt="Poster">
  <div class="title">{title}</div>
  <div class="year">{year} • {runtime}</div>
  <div class="plot">{plot}</div>
  <div><small>⭐ IMDb {rating}/10</small></div>

  {review_links}

  <div class="home-link">
    <a href="https://ti-paizei-tora.gr" class="home-button">
       🎬 Περισσότερες Προβολές
    </a>
  </div>

</div>

</body>
</html>
"""


# --- Load JSON ---
with open(os.path.join(BASE_DIR, "movies.json"), "r", encoding="utf-8") as f:
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
    print("✅ Old movie folder removed")


def fetch_athinorama_poster(athinorama_url):
    """
    Fetch movie poster from Athinorama page as fallback when OMDB doesn't have it.
    Returns the poster URL or None if not found.
    """
    if not athinorama_url:
        return None

    try:
        response = requests.get(athinorama_url, timeout=10)
        response.raise_for_status()

        # Look for the main poster image (250x300 size)
        # Pattern: <img src="https://www.athinorama.gr/Content/ImagesDatabase/p/250x300/...jpg" alt="Movie Title"
        import re
        match = re.search(r'<img[^>]+src="(https://www\.athinorama\.gr/Content/ImagesDatabase/p/250x300/[^"]+\.jpg[^"]*)"', response.text)

        if match:
            poster_url = match.group(1)
            # Clean up the URL (remove HTML entities)
            poster_url = poster_url.replace('&amp;', '&')
            return poster_url

        return None
    except Exception as e:
        print(f"Error fetching Athinorama poster: {e}")
        return None


def fetch_tmdb_by_title(title, year=None):
    """Search TMDB by title+year with fallback strategies."""
    search_url = "https://api.themoviedb.org/3/search/movie"

    # Strategy 1: title + year
    # Strategy 2: title without year (year can be off by 1 or wrong)
    # Strategy 3: title with language hint for Greek films
    search_attempts = []
    if year:
        search_attempts.append({"api_key": TMDB_API_KEY, "query": title, "year": year})
    search_attempts.append({"api_key": TMDB_API_KEY, "query": title})
    search_attempts.append({"api_key": TMDB_API_KEY, "query": title, "language": "el-GR"})

    movie_id = None
    try:
        for params in search_attempts:
            strategy = f"query='{params['query']}'"
            if "year" in params:
                strategy += f", year={params['year']}"
            if "language" in params:
                strategy += f", lang={params['language']}"

            r = requests.get(search_url, params=params)
            results = r.json().get("results", [])
            if results:
                movie_id = results[0]["id"]
                print(f"  TMDB: matched with [{strategy}] → id={movie_id}, '{results[0].get('title')}' ({results[0].get('release_date', '?')[:4]})")
                break
            else:
                print(f"  TMDB: no results for [{strategy}]")

        if not movie_id:
            return None

        details_url = f"https://api.themoviedb.org/3/movie/{movie_id}"
        details = requests.get(details_url, params={"api_key": TMDB_API_KEY}).json()

        credits_url = f"https://api.themoviedb.org/3/movie/{movie_id}/credits"
        credits = requests.get(credits_url, params={"api_key": TMDB_API_KEY}).json()

        directors = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"]
        actors = [c["name"] for c in credits.get("cast", [])[:5]]

        poster_path = details.get("poster_path")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

        return {
            "title": details.get("title", ""),
            "poster": poster_url,
            "year": details.get("release_date", "")[:4],
            "runtime": f"{details.get('runtime', '')} min" if details.get("runtime") else "",
            "plot": details.get("overview", ""),
            "rating": str(details.get("vote_average", "")),
            "director": ", ".join(directors),
            "actors": ", ".join(actors),
            "genre": ", ".join(g["name"] for g in details.get("genres", [])),
            "language": details.get("original_language", ""),
            "imdb_id": details.get("imdb_id", ""),
        }
    except Exception as e:
        print(f"  TMDB error: {e}")
        return None


# --- Main processing loop ---
for entry in movies_data:
    if not entry or not isinstance(entry, list):
        continue

    movie = entry[0]

    try:
        imdb_link = movie.get("imdb_link")
        imdb_id = extract_imdb_id(imdb_link) if imdb_link else None
    except Exception as e:
        print(f"Error extracting IMDb ID: {e}")
        imdb_id = None
    if not imdb_id:
        print("No IMDb ID:", movie.get("greek_title", "Unknown"), "→ trying TMDB search")

        # Try TMDB search by original title + year, then Greek title
        original_title = movie.get("original_title", "").strip().rstrip("/").strip()
        greek_title = movie.get("greek_title", "").strip()
        movie_year = movie.get("year")

        tmdb_data = None
        if original_title and original_title != "/":
            tmdb_data = fetch_tmdb_by_title(original_title, movie_year)
        if not tmdb_data and greek_title:
            tmdb_data = fetch_tmdb_by_title(greek_title, movie_year)

        if tmdb_data:
            movie_slug = slugify(tmdb_data["title"]) if tmdb_data["title"] else slugify(original_title or greek_title)
            movie["slug"] = movie_slug
            movie["omdb_poster"] = tmdb_data["poster"] or ""
            movie["omdb_title"] = tmdb_data["title"]
            movie["omdb_year"] = tmdb_data["year"]
            movie["omdb_runtime"] = tmdb_data["runtime"]
            movie["omdb_plot"] = tmdb_data["plot"]
            movie["omdb_rating"] = tmdb_data["rating"]
            movie["omdb_director"] = tmdb_data["director"]
            movie["omdb_actors"] = tmdb_data["actors"]
            movie["omdb_genre"] = tmdb_data["genre"]
            movie["omdb_language"] = tmdb_data["language"]
            if tmdb_data["imdb_id"]:
                movie["imdb_link"] = f"https://www.imdb.com/title/{tmdb_data['imdb_id']}/"
            print(f"  ✓ TMDB match: {tmdb_data['title']} ({tmdb_data['year']})")
        else:
            # Final fallback: Athinorama poster only
            athinorama_link = movie.get("athinorama_link")
            if athinorama_link:
                athinorama_poster = fetch_athinorama_poster(athinorama_link)
                if athinorama_poster:
                    movie["omdb_poster"] = athinorama_poster
                    movie_title = movie.get("original_title") or movie.get("greek_title", "")
                    if movie_title and movie_title != "/":
                        movie["slug"] = slugify(movie_title.rstrip("/").strip())
            print("  ✗ TMDB no results, fell back to Athinorama poster")

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

    # 💾 Save slug and OMDB data back to the movie entry for later use
    movie["slug"] = movie_slug
    movie["omdb_title"] = data.get("Title", "")
    movie["omdb_poster"] = data.get("Poster", "")
    movie["omdb_year"] = data.get("Year", "")
    movie["omdb_runtime"] = data.get("Runtime", "")
    movie["omdb_plot"] = data.get("Plot", "")
    movie["omdb_rating"] = data.get("imdbRating", "")
    movie["omdb_votes"] = data.get("imdbVotes", "")
    movie["omdb_director"] = data.get("Director", "")
    movie["omdb_actors"] = data.get("Actors", "")
    movie["omdb_genre"] = data.get("Genre", "")
    movie["omdb_language"] = data.get("Language", "")
    movie["omdb_country"] = data.get("Country", "")

    # 🖼️ Fallback: If OMDB poster is missing or "N/A", try Athinorama
    omdb_poster = movie["omdb_poster"]
    if not omdb_poster or omdb_poster == "N/A" or omdb_poster.strip() == "":
        athinorama_link = movie.get("athinorama_link")
        if athinorama_link:
            print(f"  → OMDB poster missing, fetching from Athinorama...")
            athinorama_poster = fetch_athinorama_poster(athinorama_link)
            if athinorama_poster:
                movie["omdb_poster"] = athinorama_poster
                print(f"  ✓ Got poster from Athinorama: {athinorama_poster[:60]}...")

    # Build review links section
    review_links_html = ""
    review_links_list = []

    if movie.get("flix_url") and movie.get("flix_rating", 0) > 0:
        flix_rating = movie["flix_rating"]
        review_links_list.append(
            f'<a href="{movie["flix_url"]}" target="_blank" class="review-link">'
            f'📺 Flix: {flix_rating}/10</a>'
        )

    if movie.get("lifo_url") and movie.get("lifo_rating", "0") not in ["0", ""]:
        lifo_rating = movie["lifo_rating"]
        review_links_list.append(
            f'<a href="{movie["lifo_url"]}" target="_blank" class="review-link">'
            f'📰 Lifo: {lifo_rating}/5</a>'
        )

    if review_links_list:
        review_links_html = '<div class="review-links">' + "".join(review_links_list) + '</div>'

    # Build HTML with fallbacks
    html = HTML_TEMPLATE.format(
        title=data.get("Title", "Unknown"),
        poster=data.get("Poster", ""),
        year=data.get("Year", "—"),
        runtime=data.get("Runtime", "—"),
        plot=data.get("Plot", "No plot available."),
        rating=data.get("imdbRating", "—"),
        review_links=review_links_html,
    )

    # Output folder: movie/<movie-slug>/index.html
    out_dir = os.path.join(MOVIE_DIR, movie_slug)
    os.makedirs(out_dir, exist_ok=True)

    output_file = os.path.join(out_dir, "index.html")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

    print("Created:", output_file)

# 💾 Save updated movies.json with slugs
with open(os.path.join(BASE_DIR, "movies.json"), "w", encoding="utf-8") as f:
    json.dump(movies_data, f, ensure_ascii=False, indent=2)

# 📋 Report movies missing information
missing_info = []
for entry in movies_data:
    if not entry or not isinstance(entry, list):
        continue
    movie = entry[0]
    title = movie.get("greek_title") or movie.get("original_title") or "Unknown"
    gaps = []
    if not movie.get("imdb_link"):
        gaps.append("imdb_id")
    if not movie.get("omdb_poster") or movie.get("omdb_poster") == "N/A":
        gaps.append("poster")
    if not movie.get("omdb_director"):
        gaps.append("director")
    if not movie.get("omdb_actors"):
        gaps.append("actors")
    if not movie.get("omdb_plot"):
        gaps.append("plot")
    if not movie.get("omdb_rating") or movie.get("omdb_rating") == "N/A":
        gaps.append("rating")
    if not movie.get("slug"):
        gaps.append("slug")
    if gaps:
        missing_info.append({"title": title, "missing": gaps})

if missing_info:
    print(f"\n⚠️  Movies missing information: {len(missing_info)}/{len([e for e in movies_data if e and isinstance(e, list)])}")
    for m in missing_info:
        print(f"   • {m['title']} — missing: {', '.join(m['missing'])}")
else:
    print("\n✅ All movies have complete information.")

print("\nDone! All movie cards and folders generated.")

# Create html showtime subfolders

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
    # Include dialytika characters: ϊ (U+03CA), ΐ (U+0390), ϋ (U+03CB), ΰ (U+03B0)
    match = re.search(
        r"(\d{1,2})\s+([Α-Ωα-ωάέίόήύώΆΈΉΊΌΎΏϊΐϋΰ\.]+)\s+(\d{2}):(\d{2})",
        showtime_str,
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
            "Μαΐ": "05",  # May with tonos (ΐ)
            "Μαϊ": "05",  # May without tonos (ϊ) - alternative spelling from Athinorama
            "Ιουν": "06",
            "Ιουλ": "07",
            "Αυγ": "08",
            "Σεπ": "09",
            "Οκτ": "10",
            "Νοε": "11",
            "Δεκ": "12",
        }

        month = greek_months.get(month_str, "01")

        # DEBUG: Check if month parsing is working
        if month == "01":
            print(f"      🐛 DEBUG: month_str='{month_str}' (repr: {repr(month_str)}) not found in dictionary")
            print(f"      🐛 Available keys: {list(greek_months.keys())}")

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

    return None


def is_future_showtime(parsed_showtime):
    """
    Check if a showtime is in the future.
    Matches JS logic: filterPastTimesFromToday()
    Adds 15-minute grace period - if a showtime starts within 15 minutes, keep it.
    """
    if not parsed_showtime:
        return False

    now = datetime.now(ZoneInfo("Europe/Athens"))
    today_date = now.date()
    now_mins = now.hour * 60 + now.minute

    # Create datetime for the showtime
    showtime_date = datetime(
        parsed_showtime["year"],
        parsed_showtime["month"],
        parsed_showtime["day"],
    ).date()

    # If date is before today, filter it out
    if showtime_date < today_date:
        return False

    # If it's today, check if the time has passed
    if showtime_date == today_date:
        showtime_mins = parsed_showtime["hour"] * 60 + parsed_showtime["minute"]
        # Keep showtimes that haven't started yet, or started very recently (15 min grace period)
        # This allows people to still see/share showtimes that are about to start
        grace_period_mins = 15
        threshold = now_mins - grace_period_mins
        if showtime_mins < threshold:
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
        link_html = (
            f'<a href="{movie["athinorama_link"]}" '
            f'target="_blank" class="external-link">Athinorama</a>'
        )
        external_links.append(link_html)
    if movie.get("imdb_link"):
        link_html = (
            f'<a href="{movie["imdb_link"]}" '
            f'target="_blank" class="external-link">IMDb</a>'
        )
        external_links.append(link_html)
    if movie.get("flix_url") and movie.get("flix_rating", 0) > 0:
        link_html = (
            f'<a href="{movie["flix_url"]}" '
            f'target="_blank" class="external-link">Flix ({movie["flix_rating"]}/10)</a>'
        )
        external_links.append(link_html)
    if movie.get("lifo_url") and movie.get("lifo_rating", "0") not in ["0", ""]:
        link_html = (
            f'<a href="{movie["lifo_url"]}" '
            f'target="_blank" class="external-link">Lifo ({movie["lifo_rating"]}/5)</a>'
        )
        external_links.append(link_html)

    # Build cinema location link
    cinema_name = cinema.get("cinema", "")
    cinema_addr = cinema.get("address", "")
    maps_query = f"{cinema_name} {cinema_addr}"
    maps_link = (
        f"https://www.google.com/maps/search/?api=1"
        f"&query={maps_query.replace(' ', '+')}"
    )

    # Get rooms info
    rooms_info = ""
    if cinema.get("rooms"):
        rooms_list = [
            room.get("room", "") for room in cinema["rooms"] if room.get("room")
        ]
        if rooms_list:
            rooms_str = ", ".join(rooms_list)
            rooms_info = f"<p><strong>Αίθουσα:</strong> {rooms_str}</p>"

    # Build COMPLETE ScreeningEvent Schema with Movie workPresented
    screening_event_schema = None
    try:
        # Create ISO 8601 datetime for the event
        start_datetime = f"{parsed_showtime['year']}-{parsed_showtime['month']:02d}-{parsed_showtime['day']:02d}T{parsed_showtime['hour']:02d}:{parsed_showtime['minute']:02d}:00+03:00"

        # Build URL for this specific showtime page
        region_slug = slugify(cinema.get("region", ""))
        cinema_slug = slugify(cinema.get("cinema", ""))
        movie_slug = movie.get("slug", "")
        showtime_url = f"{BASE_URL}/region/{region_slug}/cinema/{cinema_slug}/movie/{movie_slug}/{parsed_showtime['date']}/{parsed_showtime['time']}.html"

        # Build location object with geo coordinates
        location_obj = {
            "@type": "MovieTheater",
            "name": cinema.get("cinema", "")
        }
        if cinema.get("address"):
            location_obj["address"] = {
                "@type": "PostalAddress",
                "streetAddress": cinema["address"],
                "addressLocality": "Αθήνα",
                "addressCountry": "GR"
            }
        if cinema.get("lat") and cinema.get("lon"):
            location_obj["geo"] = {
                "@type": "GeoCoordinates",
                "latitude": str(cinema["lat"]),
                "longitude": str(cinema["lon"])
            }
        if cinema.get("website"):
            location_obj["url"] = cinema["website"]

        # Build Movie object (workPresented) with OMDB data
        movie_name = movie.get("omdb_title") or movie.get("original_title") or movie.get("greek_title", "")
        movie_obj = {
            "@type": "Movie",
            "name": movie_name,
            "image": movie.get("omdb_poster", ""),
            "description": movie.get("omdb_plot", "")
        }

        # Add IMDb URL as @id
        if movie.get("imdb_link"):
            movie_obj["@id"] = movie.get("imdb_link")

        # Add alternate name (Greek title)
        if movie.get("greek_title") and movie.get("greek_title") != movie_name:
            movie_obj["alternateName"] = movie.get("greek_title")

        # Add year
        if movie.get("omdb_year"):
            movie_obj["datePublished"] = movie.get("omdb_year")

        # Convert runtime to ISO 8601 duration (e.g., "119 min" -> "PT119M")
        if movie.get("omdb_runtime"):
            runtime_str = movie.get("omdb_runtime")
            minutes = re.search(r'(\d+)', runtime_str)
            if minutes:
                movie_obj["duration"] = f"PT{minutes.group(1)}M"

        # Add genre as array
        if movie.get("omdb_genre"):
            genres = [g.strip() for g in movie.get("omdb_genre").split(",")]
            movie_obj["genre"] = genres

        # Add director
        if movie.get("omdb_director") and movie.get("omdb_director") != "N/A":
            directors = [d.strip() for d in movie.get("omdb_director").split(",")]
            if len(directors) == 1:
                movie_obj["director"] = {"@type": "Person", "name": directors[0]}
            else:
                movie_obj["director"] = [{"@type": "Person", "name": d} for d in directors]

        # Add actors
        if movie.get("omdb_actors") and movie.get("omdb_actors") != "N/A":
            actors = [a.strip() for a in movie.get("omdb_actors").split(",")]
            movie_obj["actor"] = [{"@type": "Person", "name": a} for a in actors[:5]]  # Limit to 5 actors

        # Add aggregate rating
        if movie.get("omdb_rating") and movie.get("omdb_rating") != "N/A":
            rating_obj = {
                "@type": "AggregateRating",
                "ratingValue": movie.get("omdb_rating"),
                "bestRating": "10"
            }
            if movie.get("omdb_votes"):
                # Remove commas from vote count (e.g., "15,247" -> "15247")
                votes = movie.get("omdb_votes").replace(",", "")
                rating_obj["ratingCount"] = votes
            movie_obj["aggregateRating"] = rating_obj

        # Build complete ScreeningEvent schema
        screening_event_schema = {
            "@context": "https://schema.org",
            "@type": "ScreeningEvent",
            "@id": showtime_url,
            "name": f"{movie.get('greek_title', '')} στο {cinema.get('cinema', '')}",
            "url": showtime_url,
            "image": movie.get("omdb_poster", ""),
            "startDate": start_datetime,
            "location": location_obj,
            "workPresented": movie_obj,
            "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
            "eventStatus": "https://schema.org/EventScheduled"
        }
    except Exception as e:
        print(f"⚠️ Could not generate ScreeningEvent schema: {e}")
        screening_event_schema = None

    # JSON-LD script tag for ScreeningEvent
    screening_schema_tag = ""
    if screening_event_schema:
        screening_schema_tag = f"""
    <script type="application/ld+json">
    {json.dumps(screening_event_schema, ensure_ascii=False, indent=2)}
    </script>"""

    html_content = f"""<!DOCTYPE html>
<html lang="el">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{movie_title_display} - {cinema.get('cinema', '')} - \
{showtime_formatted}</title>
    <meta name="description" content="Προβολή της ταινίας \
{movie_title_display} στο {cinema.get('cinema', '')} στις {date_formatted}">{screening_schema_tag}
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, \
'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
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
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
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
            background: rgba(255, 255, 255, 0.2);
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
                    {(
                        f'''<div class="info-item">
                        <strong>Πρωτότυπος Τίτλος</strong>
                        {movie.get('original_title').rstrip('/ ').strip()}
                    </div>'''
                        if movie.get('original_title')
                        and movie.get('original_title').strip() not in ['', '/']
                        else ''
                    )}
                </div>
                {(
                    f'<div class="external-links">{" ".join(external_links)}'
                    '</div>'
                    if external_links
                    else ''
                )}
            </div>

            <div class="section">
                <h2>🎭 Κινηματογράφος</h2>
                <div class="info-grid">
                    <div class="info-item">
                        <strong>Όνομα</strong>
                        {cinema.get('cinema', 'Μη διαθέσιμο')}
                        {(
                            f' - <a href="{cinema["website"]}" '
                            'target="_blank">Ιστοσελίδα</a>'
                            if cinema.get('website')
                            else ''
                        )}
                    </div>
                    <div class="info-item">
                        <strong>Διεύθυνση</strong>
                        {cinema.get('address', 'Μη διαθέσιμη')}
                    </div>
                    {(
                        f'''<div class="info-item">
                        <strong>Περιοχή</strong>
                        {cinema['region']}'''
                        + (f' - {cinema["subregion"]}' if cinema.get('subregion') else '')
                        + (f' ({cinema["neighbourhood"]})' if cinema.get('neighbourhood') else '')
                        + '''
                    </div>'''
                        if cinema.get('region')
                        else ''
                    )}
                </div>
                <a href="{maps_link}" target="_blank" \
class="location-link">Δες στο Google Maps</a>
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

            <div class="section" style="text-align:center;">
                <a href="https://ti-paizei-tora.gr"
                   style="display:inline-block; color:white; text-decoration:none; \
font-size:16px; font-weight:600; padding:12px 32px; background:#667eea; \
border-radius:8px; transition:all 0.3s; box-shadow:0 2px 8px rgba(102,126,234,0.3);">
                   🎬 Περισσότερες Προβολές
                </a>
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

    # Build COMPLETE ScreeningEvent Schema with Movie workPresented
    screening_event_schema = None
    try:
        # Create ISO 8601 datetime for the event
        start_datetime = f"{parsed_showtime['year']}-{parsed_showtime['month']:02d}-{parsed_showtime['day']:02d}T{parsed_showtime['hour']:02d}:{parsed_showtime['minute']:02d}:00+03:00"

        # Build URL for this specific showtime page
        region_slug = slugify(cinema.get("region", ""))
        cinema_slug = slugify(cinema.get("cinema", ""))
        movie_slug = movie.get("slug", "")
        showtime_url = f"{BASE_URL}/region/{region_slug}/cinema/{cinema_slug}/movie/{movie_slug}/{parsed_showtime['date']}/{parsed_showtime['time']}.html"

        # Build location object with geo coordinates
        location_obj = {
            "@type": "MovieTheater",
            "name": cinema.get("cinema", "")
        }
        if cinema.get("address"):
            location_obj["address"] = {
                "@type": "PostalAddress",
                "streetAddress": cinema["address"],
                "addressLocality": "Αθήνα",
                "addressCountry": "GR"
            }
        if cinema.get("lat") and cinema.get("lon"):
            location_obj["geo"] = {
                "@type": "GeoCoordinates",
                "latitude": str(cinema["lat"]),
                "longitude": str(cinema["lon"])
            }
        if cinema.get("website"):
            location_obj["url"] = cinema["website"]

        # Build Movie object (workPresented) with OMDB data
        movie_name = movie.get("omdb_title") or movie.get("original_title") or movie.get("greek_title", "")
        movie_obj = {
            "@type": "Movie",
            "name": movie_name,
            "image": movie.get("omdb_poster", ""),
            "description": movie.get("omdb_plot", "")
        }

        # Add IMDb URL as @id
        if movie.get("imdb_link"):
            movie_obj["@id"] = movie.get("imdb_link")

        # Add alternate name (Greek title)
        if movie.get("greek_title") and movie.get("greek_title") != movie_name:
            movie_obj["alternateName"] = movie.get("greek_title")

        # Add year
        if movie.get("omdb_year"):
            movie_obj["datePublished"] = movie.get("omdb_year")

        # Convert runtime to ISO 8601 duration (e.g., "119 min" -> "PT119M")
        if movie.get("omdb_runtime"):
            runtime_str = movie.get("omdb_runtime")
            minutes = re.search(r'(\d+)', runtime_str)
            if minutes:
                movie_obj["duration"] = f"PT{minutes.group(1)}M"

        # Add genre as array
        if movie.get("omdb_genre"):
            genres = [g.strip() for g in movie.get("omdb_genre").split(",")]
            movie_obj["genre"] = genres

        # Add director
        if movie.get("omdb_director") and movie.get("omdb_director") != "N/A":
            directors = [d.strip() for d in movie.get("omdb_director").split(",")]
            if len(directors) == 1:
                movie_obj["director"] = {"@type": "Person", "name": directors[0]}
            else:
                movie_obj["director"] = [{"@type": "Person", "name": d} for d in directors]

        # Add actors
        if movie.get("omdb_actors") and movie.get("omdb_actors") != "N/A":
            actors = [a.strip() for a in movie.get("omdb_actors").split(",")]
            movie_obj["actor"] = [{"@type": "Person", "name": a} for a in actors[:5]]  # Limit to 5 actors

        # Add aggregate rating
        if movie.get("omdb_rating") and movie.get("omdb_rating") != "N/A":
            rating_obj = {
                "@type": "AggregateRating",
                "ratingValue": movie.get("omdb_rating"),
                "bestRating": "10"
            }
            if movie.get("omdb_votes"):
                # Remove commas from vote count (e.g., "15,247" -> "15247")
                votes = movie.get("omdb_votes").replace(",", "")
                rating_obj["ratingCount"] = votes
            movie_obj["aggregateRating"] = rating_obj

        # Build complete ScreeningEvent schema
        screening_event_schema = {
            "@context": "https://schema.org",
            "@type": "ScreeningEvent",
            "@id": showtime_url,
            "name": f"{movie.get('greek_title', '')} στο {cinema.get('cinema', '')}",
            "url": showtime_url,
            "image": movie.get("omdb_poster", ""),
            "startDate": start_datetime,
            "location": location_obj,
            "workPresented": movie_obj,
            "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
            "eventStatus": "https://schema.org/EventScheduled"
        }
    except Exception as e:
        print(f"⚠️ Could not generate ScreeningEvent schema: {e}")
        screening_event_schema = None

    # Build cinema location link
    cinema_name = cinema.get("cinema", "")
    cinema_addr = cinema.get("address", "")
    maps_query = f"{cinema_name} {cinema_addr}"
    maps_link = (
        f"https://www.google.com/maps/search/?api=1"
        f"&query={maps_query.replace(' ', '+')}"
    )

    # Get rooms info
    rooms_html = ""
    if cinema.get("rooms"):
        rooms_list = [
            room.get("room", "") for room in cinema["rooms"] if room.get("room")
        ]
        if rooms_list:
            rooms_str = ", ".join(rooms_list)
            rooms_html = f"<div><small>Αίθουσα: {rooms_str}</small></div>"

    # Movie title for meta update
    movie_title_display = movie.get("greek_title", "")
    orig_title = movie.get("original_title", "")
    if orig_title and orig_title.strip() not in ["", "/"]:
        movie_title_display += f" ({movie.get('original_title').rstrip('/ ').strip()})"

    # Create cinema and showtime section HTML
    cinema_showtime_section = f"""
  <!-- Cinema & Showtime Information -->
  <div style="background: linear-gradient(135deg, #667eea 0%, \
#764ba2 100%); color: white; padding: 24px; border-radius: 10px; \
margin-bottom: 20px;">
    <h3 style="margin: 0 0 16px 0; font-size: 1.4em;">🎭 Προβολή</h3>
    <div style="background: rgba(255, 255, 255, 0.1); padding: 16px; \
border-radius: 8px; margin-bottom: 12px;">
      <div style="font-size: 1.8em; font-weight: bold; \
margin-bottom: 8px;">🕒 {showtime_formatted}</div>
      <div style="font-size: 1.1em; opacity: 0.9;">{date_formatted}</div>
      {rooms_html}
    </div>

    <div style="background: rgba(255, 255, 255, 0.1); padding: 16px; \
border-radius: 8px;">
      <h4 style="margin: 0 0 12px 0; font-size: 1.2em;">\
📍 Κινηματογράφος</h4>
      <div style="font-size: 1.1em; margin-bottom: 8px;">
        <strong>{cinema.get('cinema', 'Μη διαθέσιμο')}</strong>
        {(
            f' - <a href="{cinema["website"]}" target="_blank" '
            'style="color: white; text-decoration: underline;">Ιστοσελίδα</a>'
            if cinema.get('website')
            else ''
        )}
      </div>
      <div style="margin-bottom: 8px;">{cinema.get('address', 'Μη διαθέσιμη')}</div>
      {f'<div style="font-size: 0.95em; opacity: 0.9;">{cinema["region"]}" - {cinema["subregion"]}"'}
      <a href="{maps_link}" target="_blank" style="display: inline-block; margin-top: 12px; padding: 10px 20px; background: rgba(255, 255, 255, 0.9); color: #667eea; text-decoration: none; border-radius: 6px; font-weight: bold;">📍 Δες στο Google Maps</a>
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
    cinema_name = cinema.get("cinema", "")
    new_description = (
        f"Προβολή της ταινίας {movie_title_display} "
        f"στο {cinema_name} στις {date_formatted}"
    )
    if '<meta name="description"' in movie_html:
        movie_html = re.sub(
            r'<meta name="description"[^>]*>',
            f'<meta name="description" content="{new_description}">',
            movie_html,
        )
    else:
        # Add meta description after charset
        meta_desc = (
            f'<meta charset="UTF-8" />\n'
            f'<meta name="description" content="{new_description}">'
        )
        movie_html = movie_html.replace('<meta charset="UTF-8" />', meta_desc)

    # Inject ScreeningEvent Schema in <head>
    if screening_event_schema:
        schema_tag = f"""
    <script type="application/ld+json">
    {json.dumps(screening_event_schema, ensure_ascii=False, indent=2)}
    </script>"""
        # Insert before closing </head>
        if "</head>" in movie_html:
            movie_html = movie_html.replace("</head>", f"{schema_tag}\n</head>", 1)

    # Inject cinema/showtime section after opening <body> or .card div
    if '<div class="card">' in movie_html:
        # Insert right after opening of .card div
        replacement = f'<div class="card">\n{cinema_showtime_section}'
        movie_html = movie_html.replace('<div class="card">', replacement, 1)
    elif "<body>" in movie_html:
        # Fallback: insert after body tag
        movie_html = movie_html.replace(
            "<body>", f"<body>\n{cinema_showtime_section}", 1
        )

    return movie_html


def generate_consolidated_movie_page(movie, cinema_screenings):
    """
    Generate a consolidated movie page with ALL showtimes grouped by cinema.

    Args:
        movie: Movie data dict with OMDB fields
        cinema_screenings: List of dicts with keys:
            - "cinema": cinema data dict
            - "showtimes": list of parsed showtime dicts

    Returns:
        Complete HTML string for the movie page
    """

    # Prepare movie title for display
    movie_title_display = movie.get("greek_title", "")
    movie_title_english = movie.get("omdb_title") or movie.get("original_title", "")
    if movie.get("original_title") and movie.get("original_title").strip() not in ["", "/"]:
        movie_title_display += f" ({movie.get('original_title').rstrip('/ ').strip()})"

    # Get movie metadata
    poster = movie.get("omdb_poster", "")
    plot = movie.get("omdb_plot", "No plot available.")
    year = movie.get("omdb_year", movie.get("year", ""))
    runtime = movie.get("omdb_runtime", "")
    rating = movie.get("omdb_rating", "")

    # Build review links
    review_links_html = ""
    review_links_list = []

    if movie.get("athinorama_link"):
        review_links_list.append(
            f'<a href="{movie["athinorama_link"]}" target="_blank" class="review-link">Athinorama</a>'
        )
    if movie.get("imdb_link"):
        review_links_list.append(
            f'<a href="{movie["imdb_link"]}" target="_blank" class="review-link">IMDb</a>'
        )
    if movie.get("flix_url") and movie.get("flix_rating", 0) > 0:
        review_links_list.append(
            f'<a href="{movie["flix_url"]}" target="_blank" class="review-link">📺 Flix: {movie["flix_rating"]}/10</a>'
        )
    if movie.get("lifo_url") and movie.get("lifo_rating", "0") not in ["0", ""]:
        review_links_list.append(
            f'<a href="{movie["lifo_url"]}" target="_blank" class="review-link">📰 Lifo: {movie["lifo_rating"]}/5</a>'
        )

    if review_links_list:
        review_links_html = '<div class="review-links">' + " ".join(review_links_list) + '</div>'

    # Build Movie schema with all ScreeningEvents as subEvents
    screening_events = []

    for cinema_group in cinema_screenings:
        cinema = cinema_group["cinema"]
        cinema_slug = slugify(cinema.get("cinema", ""))

        for showtime in cinema_group["showtimes"]:
            # Create unique ID for this screening
            showtime_id = f"{cinema_slug}-{showtime['date']}-{showtime['time'].replace('-', '')}"

            # Build ScreeningEvent
            event = {
                "@type": "ScreeningEvent",
                "@id": showtime_id,
                "name": f"{movie.get('greek_title', '')} στο {cinema.get('cinema', '')}",
                "startDate": f"{showtime['year']}-{showtime['month']:02d}-{showtime['day']:02d}T{showtime['hour']:02d}:{showtime['minute']:02d}:00+03:00",
                "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
                "eventStatus": "https://schema.org/EventScheduled"
            }

            # Add location
            location_obj = {
                "@type": "MovieTheater",
                "name": cinema.get("cinema", "")
            }
            if cinema.get("address"):
                location_obj["address"] = {
                    "@type": "PostalAddress",
                    "streetAddress": cinema["address"],
                    "addressLocality": "Αθήνα",
                    "addressCountry": "GR"
                }
            if cinema.get("lat") and cinema.get("lon"):
                location_obj["geo"] = {
                    "@type": "GeoCoordinates",
                    "latitude": str(cinema["lat"]),
                    "longitude": str(cinema["lon"])
                }
            if cinema.get("website"):
                location_obj["url"] = cinema["website"]

            event["location"] = location_obj
            screening_events.append(event)

    # Build Movie schema
    movie_schema = {
        "@context": "https://schema.org",
        "@type": "Movie",
        "name": movie_title_english,
        "image": poster,
        "description": plot
    }

    if movie.get("imdb_link"):
        movie_schema["@id"] = movie.get("imdb_link")

    if movie.get("greek_title") and movie.get("greek_title") != movie_title_english:
        movie_schema["alternateName"] = movie.get("greek_title")

    if year:
        movie_schema["datePublished"] = year

    if runtime:
        minutes = re.search(r'(\d+)', runtime)
        if minutes:
            movie_schema["duration"] = f"PT{minutes.group(1)}M"

    if movie.get("omdb_genre"):
        genres = [g.strip() for g in movie.get("omdb_genre").split(",")]
        movie_schema["genre"] = genres

    if movie.get("omdb_director") and movie.get("omdb_director") != "N/A":
        directors = [d.strip() for d in movie.get("omdb_director").split(",")]
        if len(directors) == 1:
            movie_schema["director"] = {"@type": "Person", "name": directors[0]}
        else:
            movie_schema["director"] = [{"@type": "Person", "name": d} for d in directors]

    if movie.get("omdb_actors") and movie.get("omdb_actors") != "N/A":
        actors = [a.strip() for a in movie.get("omdb_actors").split(",")]
        movie_schema["actor"] = [{"@type": "Person", "name": a} for a in actors[:5]]

    if movie.get("omdb_rating") and movie.get("omdb_rating") != "N/A":
        rating_obj = {
            "@type": "AggregateRating",
            "ratingValue": movie.get("omdb_rating"),
            "bestRating": "10"
        }
        if movie.get("omdb_votes"):
            votes = movie.get("omdb_votes").replace(",", "")
            rating_obj["ratingCount"] = votes
        movie_schema["aggregateRating"] = rating_obj

    # Add all ScreeningEvents as subEvents
    if screening_events:
        movie_schema["subEvent"] = screening_events

    # Build cinema sections HTML
    cinema_sections_html = ""

    for cinema_group in cinema_screenings:
        cinema = cinema_group["cinema"]
        cinema_slug = slugify(cinema.get("cinema", ""))
        showtimes = cinema_group["showtimes"]

        cinema_name = cinema.get("cinema", "Μη διαθέσιμο")
        cinema_region = cinema.get("region", "")
        cinema_addr = cinema.get("address", "")
        cinema_website = cinema.get("website", "")

        # Build cinema header
        website_link = ""
        if cinema_website:
            website_link = f' - <a href="{cinema_website}" target="_blank" style="color: #667eea; text-decoration: underline;">Ιστοσελίδα</a>'

        cinema_sections_html += f'''
  <div class="cinema-section" data-cinema="{cinema_slug}">
    <h2 style="color: #667eea; margin: 24px 0 16px 0; padding-bottom: 12px; border-bottom: 2px solid #f0f0f0;">
      {cinema_name} - {cinema_region}{website_link}
    </h2>
'''

        # Build showtime cards
        for showtime in showtimes:
            showtime_id = f"{cinema_slug}-{showtime['date']}-{showtime['time'].replace('-', '')}"
            time_formatted = showtime["time"].replace("-", ":")
            date_formatted = showtime["full"]

            # Get rooms info
            rooms_html = ""
            if cinema.get("rooms"):
                rooms_list = [room.get("room", "") for room in cinema["rooms"] if room.get("room")]
                if rooms_list:
                    rooms_str = ", ".join(rooms_list)
                    rooms_html = f'<div style="color: #666; font-size: 14px;">Αίθουσα: {rooms_str}</div>'

            cinema_sections_html += f'''
    <div class="showtime-card"
         id="{showtime_id}"
         data-cinema="{cinema_name}"
         data-date="{showtime['date']}"
         data-time="{time_formatted}">
      <div class="time" style="font-size: 18px; font-weight: bold; color: #333; margin-bottom: 4px;">
        🕒 {date_formatted}
      </div>
      <div style="color: #666; font-size: 14px; margin-bottom: 8px;">
        {cinema_addr}
      </div>
      {rooms_html}
      <div style="margin-top: 12px;">
        <button class="share-btn" data-showtime-id="{showtime_id}"
                style="padding: 8px 16px; background: #667eea; color: white; border: none;
                       border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500;">
          🔗 Κοινοποίηση
        </button>
      </div>
    </div>
'''

        cinema_sections_html += "  </div>\n"

    # Complete HTML document
    html_content = f'''<!DOCTYPE html>
<html lang="el">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{movie_title_display} - Προβολές στην Αθήνα</title>
  <meta name="description" content="Όλες οι προβολές της ταινίας {movie_title_display} στα σινεμά της Αθήνας. Βρες ωράρια, κινηματογράφους και κλείσε εισιτήρια.">

  <script type="application/ld+json">
  {json.dumps(movie_schema, ensure_ascii=False, indent=2)}
  </script>

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
      max-width: 900px;
      margin: 0 auto;
      background: white;
      border-radius: 12px;
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
      overflow: hidden;
    }}
    .movie-header {{
      padding: 30px;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      text-align: center;
    }}
    .movie-header h1 {{
      font-size: 2em;
      margin-bottom: 10px;
    }}
    .movie-header .subtitle {{
      font-size: 1.1em;
      opacity: 0.9;
    }}
    .movie-details {{
      padding: 30px;
      display: flex;
      gap: 20px;
    }}
    .movie-poster {{
      flex-shrink: 0;
    }}
    .movie-poster img {{
      width: 200px;
      border-radius: 8px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }}
    .movie-info {{
      flex: 1;
    }}
    .movie-info .meta {{
      color: #777;
      margin-bottom: 12px;
    }}
    .movie-info .plot {{
      margin-bottom: 16px;
      line-height: 1.6;
    }}
    .movie-info .rating {{
      color: #f39c12;
      font-weight: bold;
    }}
    .review-links {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 12px;
    }}
    .review-link {{
      display: inline-block;
      padding: 6px 12px;
      background: #f0f0f0;
      color: #333;
      text-decoration: none;
      border-radius: 6px;
      font-size: 13px;
      transition: background 0.2s;
    }}
    .review-link:hover {{
      background: #e0e0e0;
    }}
    .showtimes-container {{
      padding: 30px;
    }}
    .cinema-section {{
      margin-bottom: 32px;
    }}
    .showtime-card {{
      border: 2px solid transparent;
      transition: all 0.3s ease;
      padding: 16px;
      margin: 12px 0;
      border-radius: 8px;
      background: #f9f9f9;
    }}
    .showtime-card.featured {{
      border-color: #667eea;
      background: linear-gradient(to right, #f0f4ff, #ffffff);
      box-shadow: 0 4px 20px rgba(102, 126, 234, 0.25);
      transform: scale(1.02);
    }}
    .share-btn:hover {{
      background: #5568d3;
    }}
    .show-all-btn {{
      width: 100%;
      padding: 16px;
      background: #f0f4ff;
      border: 2px dashed #667eea;
      border-radius: 8px;
      color: #667eea;
      font-size: 16px;
      font-weight: 600;
      cursor: pointer;
      margin-top: 20px;
      transition: all 0.3s;
    }}
    .show-all-btn:hover {{
      background: #667eea;
      color: white;
      border-style: solid;
    }}
    .toast {{
      position: fixed;
      bottom: 20px;
      left: 50%;
      transform: translateX(-50%) translateY(100px);
      background: #28a745;
      color: white;
      padding: 12px 24px;
      border-radius: 8px;
      opacity: 0;
      transition: all 0.3s ease;
      z-index: 1000;
    }}
    .toast.show {{
      transform: translateX(-50%) translateY(0);
      opacity: 1;
    }}
    .home-link {{
      text-align: center;
      padding: 20px 30px 30px 30px;
    }}
    .home-button {{
      display: inline-block;
      padding: 12px 32px;
      background: #667eea;
      color: white;
      text-decoration: none;
      border-radius: 8px;
      font-size: 16px;
      font-weight: 600;
      transition: all 0.3s;
      box-shadow: 0 2px 8px rgba(102,126,234,0.3);
    }}
    .home-button:hover {{
      background: #5568d3;
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(102,126,234,0.4);
    }}
    .top-nav {{
      text-align: center;
      padding: 15px 20px;
      background: #f8f9fa;
      border-bottom: 1px solid #e0e0e0;
      margin-bottom: 0;
    }}
    .top-nav a {{
      color: #667eea;
      text-decoration: none;
      font-size: 14px;
      font-weight: 600;
      transition: color 0.2s;
    }}
    .top-nav a:hover {{
      color: #5568d3;
      text-decoration: underline;
    }}
    @media (max-width: 768px) {{
      .movie-details {{
        flex-direction: column;
      }}
      .movie-poster img {{
        width: 100%;
        max-width: 300px;
      }}
    }}
  </style>
</head>
<body>
  <div class="top-nav">
    <a href="https://ti-paizei-tora.gr">← Επιστροφή στην Αρχική</a>
  </div>
  <div class="container">
    <div class="movie-header">
      <h1>{movie_title_display}</h1>
      <div class="subtitle">Προβολές στην Αθήνα</div>
    </div>

    <div class="movie-details">
      <div class="movie-poster">
        <img src="{poster}" alt="{movie_title_display}">
      </div>
      <div class="movie-info">
        <div class="meta">{year} • {runtime}</div>
        <div class="plot">{plot}</div>
        <div class="rating">⭐ IMDb {rating}/10</div>
        {review_links_html}
      </div>
    </div>

    <div class="showtimes-container">
      <h2 style="color: #333; margin-bottom: 20px; font-size: 1.5em;">Πού παίζει;</h2>
{cinema_sections_html}
    </div>

    <div class="home-link">
      <a href="https://ti-paizei-tora.gr" class="home-button">
        🎬 Περισσότερες Ταινίες
      </a>
    </div>
  </div>

  <script>
    // Deep linking & default collapsed state
    window.addEventListener('DOMContentLoaded', () => {{
      const urlParams = new URLSearchParams(window.location.search);
      const showtimeId = urlParams.get('showtime');

      if (showtimeId) {{
        // CASE 1: Specific showtime requested - show only that one
        const targetCard = document.getElementById(showtimeId);

        if (targetCard) {{
          // Hide all showtime cards except the target
          document.querySelectorAll('.showtime-card').forEach(card => {{
            if (card.id !== showtimeId) {{
              card.style.display = 'none';
            }}
          }});

          // Hide cinema sections that don't contain this showtime
          document.querySelectorAll('.cinema-section').forEach(section => {{
            if (!section.contains(targetCard)) {{
              section.style.display = 'none';
            }}
          }});

          // Highlight the target card
          targetCard.classList.add('featured');

          // Update page title
          const cinema = targetCard.dataset.cinema;
          const time = targetCard.dataset.time;
          document.title = `{movie_title_display} - ${{cinema}} - ${{time}}`;

          // Add "Show all showtimes" button
          const showAllBtn = document.createElement('button');
          showAllBtn.className = 'show-all-btn';
          showAllBtn.textContent = '📅 Δες όλες τις προβολές';
          showAllBtn.onclick = () => {{
            window.location.href = window.location.pathname;
          }};
          targetCard.parentElement.insertBefore(showAllBtn, targetCard.nextSibling);

          // Scroll to top
          window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}
      }} else {{
        // CASE 2: Base movie URL - hide all cinema sections by default
        const showtimesContainer = document.querySelector('.showtimes-container');

        // Hide all cinema sections
        document.querySelectorAll('.cinema-section').forEach(section => {{
          section.style.display = 'none';
        }});

        // Create and add "Show All Showtimes" button
        const expandBtn = document.createElement('button');
        expandBtn.className = 'show-all-btn';
        expandBtn.style.cssText = `
          display: block;
          margin: 20px auto;
          padding: 16px 32px;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          border: none;
          border-radius: 10px;
          font-size: 18px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.3s;
          box-shadow: 0 4px 12px rgba(102,126,234,0.3);
        `;
        expandBtn.textContent = '📍 Δες Όλες τις Προβολές & Κινηματογράφους';

        expandBtn.addEventListener('mouseover', () => {{
          expandBtn.style.transform = 'translateY(-2px)';
          expandBtn.style.boxShadow = '0 6px 16px rgba(102,126,234,0.4)';
        }});
        expandBtn.addEventListener('mouseout', () => {{
          expandBtn.style.transform = 'translateY(0)';
          expandBtn.style.boxShadow = '0 4px 12px rgba(102,126,234,0.3)';
        }});

        expandBtn.onclick = () => {{
          // Show all cinema sections
          document.querySelectorAll('.cinema-section').forEach(section => {{
            section.style.display = 'block';
          }});
          // Hide the button
          expandBtn.style.display = 'none';
        }};

        // Insert button after the "Πού παίζει;" heading
        const heading = showtimesContainer.querySelector('h2');
        heading.after(expandBtn);
      }}
    }});

    // Share button functionality
    document.querySelectorAll('.share-btn').forEach(btn => {{
      btn.addEventListener('click', async (e) => {{
        const showtimeId = e.target.dataset.showtimeId;
        const shareUrl = `${{window.location.origin}}${{window.location.pathname}}?showtime=${{showtimeId}}`;

        const card = document.getElementById(showtimeId);
        const cinema = card.dataset.cinema;
        const time = card.querySelector('.time').textContent;
        const shareTitle = `{movie_title_display} - ${{cinema}}`;
        const shareText = `Θες να πάμε; ${{time}}`;

        try {{
          if (navigator.share) {{
            await navigator.share({{
              title: shareTitle,
              text: shareText,
              url: shareUrl
            }});
          }} else {{
            await navigator.clipboard.writeText(shareUrl);
            showToast('✅ Ο σύνδεσμος αντιγράφηκε!');
          }}
        }} catch (err) {{
          // User cancelled or error
        }}
      }});
    }});

    function showToast(message) {{
      const toast = document.createElement('div');
      toast.className = 'toast';
      toast.textContent = message;
      document.body.appendChild(toast);

      setTimeout(() => toast.classList.add('show'), 100);
      setTimeout(() => {{
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
      }}, 2000);
    }}
  </script>
</body>
</html>'''

    return html_content


def create_cinema_structure():
    """
    Generate consolidated movie pages with ALL showtimes grouped by cinema.
    Creates ONE HTML file per movie at: /movie/{slug}/index.html
    """

    now_debug = datetime.now(ZoneInfo("Europe/Athens"))
    print(f"Starting consolidated page generation — {now_debug.date()} {now_debug.hour:02d}:{now_debug.minute:02d} (Athens)")

    # Load JSON files
    with open(os.path.join(BASE_DIR, "movies.json"), "r", encoding="utf-8") as f:
        movies_data = json.load(f)

    with open(os.path.join(BASE_DIR, "cinemas.json"), "r", encoding="utf-8") as f:
        cinemas_data = json.load(f)

    movie_dir_path = Path(MOVIE_DIR)

    # 🗑️ DELETE OLD MOVIE FOLDER BEFORE REBUILDING
    if movie_dir_path.exists():
        print(f"🗑️  Deleting existing movie folder: {movie_dir_path}")
        shutil.rmtree(movie_dir_path)
        print("✅ Old movie folder removed")

    movie_dir_path.mkdir(exist_ok=True)

    stats = {
        "total_movies": 0,
        "total_cinemas": 0,
        "total_showtimes": 0,
        "skipped_no_timetable": 0,
        "skipped_empty_timetable": 0,
        "skipped_past_times": 0,
        "movies_with_showtimes": 0,
        "movies_processed": [],
    }

    # Loop through movies and their corresponding cinemas
    for _, (movie_list, cinema_list) in enumerate(zip(movies_data, cinemas_data)):
        if not movie_list or not cinema_list:
            continue

        movie = movie_list[0]
        stats["total_movies"] += 1

        # Get movie slug
        movie_slug = movie.get("slug", "").strip()
        if not movie_slug:
            movie_title = movie.get("original_title", "").strip()
            if not movie_title or movie_title == "/":
                movie_title = movie.get("greek_title", "").strip()
            movie_title = movie_title.rstrip("/ ").strip()
            movie_slug = slugify(movie_title)

        # ✅ Filter valid cinemas
        valid_cinemas = []
        for cinema in cinema_list:
            if not cinema.get("region") or not cinema.get("cinema"):
                continue

            timetable = cinema.get("timetable")
            if not timetable:
                stats["skipped_no_timetable"] += 1
                continue

            flattened = flatten_timetable(timetable)
            if len(flattened) == 0:
                stats["skipped_empty_timetable"] += 1
                continue

            valid_cinemas.append(cinema)

        if len(valid_cinemas) == 0:
            continue

        # ✅ Aggregate showtimes by cinema
        cinema_screenings = []  # List of {cinema: cinema_data, showtimes: [parsed_showtimes]}

        print(f"\n🎬 Processing movie: {movie.get('greek_title', 'Unknown')}")

        for cinema in valid_cinemas:
            valid_showtimes = []
            timetable = cinema.get("timetable", [])

            for showtime_list in timetable:
                if not showtime_list:
                    continue

                for showtime in showtime_list:
                    if not showtime or not showtime.strip():
                        continue

                    parsed = parse_showtime(showtime)
                    if not parsed:
                        continue

                    # Skip past dates and times
                    if not is_future_showtime(parsed):
                        stats["skipped_past_times"] += 1
                        continue

                    valid_showtimes.append(parsed)

            if valid_showtimes:
                # Sort showtimes by date and time
                valid_showtimes.sort(key=lambda x: (x["date"], x["time"]))

                cinema_screenings.append({
                    "cinema": cinema,
                    "showtimes": valid_showtimes
                })

                stats["total_cinemas"] += 1
                stats["total_showtimes"] += len(valid_showtimes)

        # ✅ Generate consolidated movie page if we have showtimes
        if cinema_screenings:
            # Generate HTML
            movie_html = generate_consolidated_movie_page(movie, cinema_screenings)

            # Write to /movie/{slug}/index.html
            movie_page_dir = movie_dir_path / movie_slug
            movie_page_dir.mkdir(parents=True, exist_ok=True)
            movie_page_file = movie_page_dir / "index.html"

            with open(movie_page_file, "w", encoding="utf-8") as f:
                f.write(movie_html)

            stats["movies_with_showtimes"] += 1
            stats["movies_processed"].append({
                "title": movie.get("greek_title", "Unknown"),
                "slug": movie_slug,
                "cinemas": len(cinema_screenings),
                "showtimes": sum(len(cs["showtimes"]) for cs in cinema_screenings),
            })

            print(f"   ✅ {len(cinema_screenings)} cinemas, {sum(len(cs['showtimes']) for cs in cinema_screenings)} showtimes")

    print("\n📊 Summary:")
    print(f"   Total movies: {stats['total_movies']}")
    print(f"   Movies with showtimes: {stats['movies_with_showtimes']}")
    print(f"   Total cinema entries: {stats['total_cinemas']}")
    print(f"   Total showtimes: {stats['total_showtimes']}")
    print(f"   Skipped (no timetable): {stats['skipped_no_timetable']}")
    print(f"   Skipped (empty timetable): {stats['skipped_empty_timetable']}")
    print(f"   Skipped (past times): {stats['skipped_past_times']}")

    return stats


# Run the function
stats = create_cinema_structure()


def generate_sitemap():
    now = datetime.now(ZoneInfo("Europe/Athens"))
    now_str = now.strftime("%Y-%m-%d")

    # Separate URL lists
    static_urls = []
    movie_urls = []

    # --- Static Pages (Homepage, Contact) ---
    static_urls.append(
        f"""
  <url>
    <loc>{BASE_URL}/</loc>
    <lastmod>{now_str}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
"""
    )

    static_urls.append(
        f"""
  <url>
    <loc>{BASE_URL}/contact.html</loc>
    <lastmod>{now_str}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.5</priority>
  </url>
"""
    )

    # --- Movie Pages ---
    for folder in sorted(os.listdir(MOVIE_DIR)):
        full_path = os.path.join(MOVIE_DIR, folder)
        index_file = os.path.join(full_path, "index.html")

        if os.path.isdir(full_path) and os.path.isfile(index_file):
            movie_urls.append(
                f"""
  <url>
    <loc>{BASE_URL}/movie/{folder}/</loc>
    <lastmod>{now_str}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>
"""
            )

    # Helper function to write sitemap file
    def write_sitemap(filename, urls):
        sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset
  xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
  xmlns:xhtml="http://www.w3.org/1999/xhtml">
{''.join(urls)}
</urlset>
"""
        filepath = os.path.join(BASE_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(sitemap_content)
        print(f"  ✓ {filename}: {len(urls)} URLs")
        return len(urls)

    # Write individual sitemaps
    print("\nGenerating sitemaps...")
    total = 0
    total += write_sitemap("sitemap-static.xml", static_urls)
    total += write_sitemap("sitemap-movies.xml", movie_urls)

    # --- Generate Sitemap Index ---
    sitemap_index = f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>{BASE_URL}/sitemap-static.xml</loc>
    <lastmod>{now_str}</lastmod>
  </sitemap>
  <sitemap>
    <loc>{BASE_URL}/sitemap-movies.xml</loc>
    <lastmod>{now_str}</lastmod>
  </sitemap>
</sitemapindex>
"""

    with open(os.path.join(BASE_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap_index)

    print(f"  ✓ sitemap.xml (index)\n")
    print(f"✅ Total URLs: {total}")
    print(f"   - Movies: {len(movie_urls)} (priority 0.8)")
    print(f"   - Static pages: {len(static_urls)}")


generate_sitemap()
