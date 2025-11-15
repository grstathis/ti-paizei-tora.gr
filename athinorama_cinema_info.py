import requests
from bs4 import BeautifulSoup
import json
import unicodedata
import re
from unidecode import unidecode
import os
import unicodedata

# Read the Google API key from the file
with open('/home/grstathis/ti-paizei-tora.gr/google_api', 'r') as file:
    GOOGLE_API_KEY = file.read().strip()



def extract_movie_links():
    url = "https://www.athinorama.gr/cinema/guide/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find all div elements with class "item horizontal card-item"
    movie_cards = soup.find_all('div', class_='item horizontal card-item')
    movie_links = []
    for card in movie_cards:
        # Find the link inside item-title div
        title_div = card.find('h2', class_='item-title')
        if title_div:
            link = title_div.find('a')
            if link and link.get('href'):
                movie_links.append(link['href'])
    
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
        soup.find_all("div", class_="details")):
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


def get_cinema_info_from_google(name: str, address: str = None):
    """Fetch cinema info (lat, lon, area, formatted address) from Google Maps API."""
    query = name if not address else f"{name}, {address}"
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": query,
        "key": GOOGLE_API_KEY,
        "language": "el"  # or "en" depending on what you want
    }

    response = requests.get(url, params=params)
    data = response.json()

    if data["status"] != "OK" or not data["results"]:
        print(f"⚠️ Google Maps API: No match for '{query}'")
        return {
            "lat": None,
            "lon": None,
            "area": "Unknown",
            "formatted_address": None
        }

    result = data["results"][0]
    geometry = result["geometry"]["location"]
    address_components = result.get("address_components", [])

    # Try to extract area (e.g., neighborhood, locality, sublocality)
    area = "Unknown"
    # Extract broader area (default: locality)
    area = next(
        (c["long_name"] for c in address_components if "locality" in c["types"]),
        "Unknown"
    )

    formatted_addr = result.get("formatted_address")
    
    # 🧹 Step 3: Remove Greek street words and abbreviations
    first_part = re.sub(
        r'\b(Λ\.?|Λεωφόρος|Λεωφ\.?|Οδός|Οδ\.?|Δρόμος|Δρ\.?)\b',
        '',
        formatted_addr,
        flags=re.IGNORECASE
    ).strip()

    # 🧹 Step 4: Keep only up to the first '&' or 'και' or '-' (e.g., "Συγγρού & Φραντζή" → "Συγγρού")
    first_part = re.split(r'\s*&\s*|\s*και\s*|\s*-\s*', first_part)[0].strip()
    
    # --- Geocoding ---
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": f"{first_part}",
        "format": "json",
        "addressdetails": 1,
        "limit": 1
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
        "formatted_address": formatted_addr
        }


def geocode_area(address):
    # 🧹 Step 1: Remove parentheses and contents inside them
    cleaned = re.sub(r'\([^)]*\)', '', address).strip()

    # 🧹 Step 2: Keep only the first comma-separated part
    # first_part = cleaned.split(',')[0].strip()

    # 🧹 Step 3: Remove Greek street words and abbreviations
    first_part = re.sub(
        r'\b(Λ\.?|Λεωφόρος|Λεωφ\.?|Οδός|Οδ\.?|Δρόμος|Δρ\.?)\b',
        '',
        first_part,
        flags=re.IGNORECASE
    ).strip()

    # 🧹 Step 4: Keep only up to the first '&' or 'και' or '-' (e.g., "Συγγρού & Φραντζή" → "Συγγρού")
    first_part = re.split(r'\s*&\s*|\s*και\s*|\s*-\s*', first_part)[0].strip()

#     # 🧹 Step 5: Keep only first word and possible number (e.g. "Παπανδρέου 12")
#     match = re.match(r'^([\wΆ-ώΑ-Ωά-ώ]+(?:\s*\d{1,3})?)', first_part)
#     if match:
#         query_base = match.group(1)
#     else:
#         query_base = first_part

    # 🧹 Step 6: Collapse spaces
    query_base = re.sub(r'\s+', ' ', query_base).strip()

    # --- Geocoding ---
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": f"{query_base}",
        "format": "json",
        "addressdetails": 1,
        "limit": 1
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

def load_cinema_database(filename="/home/grstathis/ti-paizei-tora.gr/cinema_database.json"):
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

def save_cinema_database(cinema_db, filename="cinema_database.json"):
    """Save cinema database to file."""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(cinema_db, f, ensure_ascii=False, indent=2)
    print(f"✅ Cinema database saved to {filename}")

def get_or_create_cinema_info(name, address, cinema_db):
    """
    Get cinema info from database or fetch from Google API if not exists.
    Returns cinema info dict and updates the database.
    """
    # Create a unique key for the cinema
    norm_name = normalize_name(name)
    norm_address = normalize_name(address) if address else ""
    cinema_key = f"{norm_name}_{norm_address}"
    
    # Check if cinema already exists in database
    if cinema_key in cinema_db:
        print(f"✅ Found cached info for: {name}")
        return cinema_db[cinema_key]
    
    # Cinema not found, fetch from Google API
    print(f"🔍 Fetching new info for: {name}")
    region_dict = get_cinema_info_from_google(name, address)
    
    # Store in database
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
    title_greek = title_greek_tag.get_text(strip=True) if title_greek_tag else "Unknown Title"

            
    card = soup.find_all("ul", class_="review-details")
    for c in card:
        original_tag = c.find("span", class_="original-title")
        if original_tag:
            original_title = original_tag.get_text()
        else:
            original_title = ""
            
    imdb = soup.find('a',class_="imdb")
    imdb = imdb.get('href') if imdb else None
        

    movies_data.append({
        "greek_title": title_greek,
        "original_title": original_title,
        "athinorama_link": url,
        "imdb_link": imdb
    })

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
            room_name = room_name_tag.get_text(strip=True) if room_name_tag else "Main Room"
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

        if not region_dict:
            region_dict['area'] = 'Unknown'
            region_dict['subarea'] = 'Unknown'
            region_dict['neighbourhood'] = 'Unknown'
            region_dict['formatted_address'] = address
            region_dict['lat'] = 0
            region_dict['lon'] = 0

        cinemas_data.append({
                "cinema": name,
                "address": region_dict['formatted_address'],
                "lat" :region_dict['lat'],
                "lon" :region_dict['lon'],
                "region": region_dict['area'],
                "subregion": region_dict['suburb'],
                "neighbourhood": region_dict['neighbourhood'],
                "rooms": rooms,
                "timetable": room_timetable
            })

    return movies_data, cinemas_data

movie_links =[]

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
    
print('saved cinemas.json, movies.json files')
