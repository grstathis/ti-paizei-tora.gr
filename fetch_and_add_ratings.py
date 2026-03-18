#!/usr/bin/env python3
"""
Combined script: Fetch ratings from LIFO and Flix, then add them to movies.json
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from unidecode import unidecode
import os
import unicodedata
from typing import Iterable, Tuple, Any, Dict, Set, List
import shutil
import time


# ----------------------------------------------------------------------------
# LIFO - Scrape sitemap and get movie ratings
# ----------------------------------------------------------------------------

print("=" * 80)
print("PART 1: FETCHING LIFO RATINGS")
print("=" * 80)


def get_sitemap_links(url):
    try:
        # 1. Fetch the sitemap content
        # Adding a User-Agent header helps avoid being blocked by some servers
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        # 2. Parse the XML content
        # We use 'xml' (or 'lxml-xml') to ensure it handles XML tags correctly
        soup = BeautifulSoup(response.content, "xml")
        # 3. Find all <loc> tags (these contain the URLs)
        # Using .text to get the content inside the tags and .strip() to clean it
        links = [loc.text.strip() for loc in soup.find_all("loc")]

        return links

    except Exception as e:
        print(f"An error occurred: {e}")
        return []


# Execute
target_url = "https://www.lifo.gr/sitemap.xml"
all_pages = get_sitemap_links(target_url)

print(f"Total links found: {len(all_pages)}")


def get_cinema_links(all_pages):
    base_sitemap_url = "https://www.lifo.gr/sitemap.xml?page="
    target_pattern = "/guide/cinema/movies/"
    all_movie_links = []

    print(f"Starting crawl...")

    for url in all_pages:

        print(f"Scanning: {url}")

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # Use 'xml' parser for sitemaps
            soup = BeautifulSoup(response.content, "xml")

            # Find all <loc> tags which contain the URLs
            loc_tags = soup.find_all("loc")

            page_links = [loc.text for loc in loc_tags if target_pattern in loc.text]
            all_movie_links.extend(page_links)

            print(f" Found {len(page_links)} movie links on page {url}.")

            # Be polite to the server
            time.sleep(0.1)

        except Exception as e:
            print(f" Error on page: {e}")
            break

    return all_movie_links


# Run the script
movies = get_cinema_links(all_pages)

print("\n--- Extraction Complete ---")
lifo_movie_links = sorted(set(movies))

# Filter out movies not currently showing
clean_lifo_links = []
for url in lifo_movie_links:
    response = requests.get(url, timeout=10)
    response.raise_for_status()

    pattern = re.compile(r"Η ΤΑΙΝΙΑ ΔΕΝ ΠΡΟΒΑΛΛΕΤΑΙ AYTH ΤΗ ΣΤΙΓΜΗ ΣΕ ΚΑΠΟΙΑ ΑΙΘΟΥΣΑ")
    matches = pattern.findall(response.text)
    if matches:
        print("not used", url)
    else:
        print("ok", url)
        clean_lifo_links.append(url)

print(f"\nClean LIFO links: {len(clean_lifo_links)}")

# Extract ratings from LIFO pages
results = []

for url in clean_lifo_links:
    print(url)
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")

    title = ""
    title_tag = soup.find("h1", class_="eventTitle")
    if title_tag:
        title = title_tag.get_text(strip=True)

    parent = soup.find("div", class_="lifoRating fs-9-v-lg fs-7-v")
    rating_number = 0
    if parent:
        # 2. Search ONLY inside that parent for the ratings div
        # 1. Find the div that contains the "rating-" class
        rating_div = parent.find("div", class_="ratings")

        if rating_div:
            # 2. rating_div['class'] returns a list: ['ratings', 'rating-3', 'mb-lg-3', 'mb-2']
            # We look for the item that starts with 'rating-'
            rating_class = next(
                (c for c in rating_div["class"] if c.startswith("rating-")), None
            )
            rating_number = rating_class.split("-")[-1]
    else:
        print("no rating")

    # store result
    results.append({"url": url, "title": title, "rating": rating_number})

# save to json
with open("lifo_ratings.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4, ensure_ascii=False)

print("Saved to lifo_ratings.json")

# ----------------------------------------------------------------------------
# FLIX - Scrape movie review pages and get ratings
# ----------------------------------------------------------------------------

print("\n" + "=" * 80)
print("PART 2: FETCHING FLIX RATINGS")
print("=" * 80)


def get_flix_review_links():
    search_url = "https://flix.gr/search-movies-in-cinemas/"
    domain = "https://flix.gr"

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Referer": domain,
        }
    )

    try:
        session.get(domain)
        response = session.get(search_url)
        response.raise_for_status()

        html_content = response.text
        soup = BeautifulSoup(html_content, "html.parser")

        found_links = set()

        # --- PART 1: Standard href Extraction ---
        for a_tag in soup.find_all("a", href=re.compile(r"-review")):
            href = a_tag["href"].strip()
            # Normalize URL
            if href.startswith("http"):
                full_url = href
            elif href.startswith("/"):
                full_url = f"{domain}{href}"
            else:
                full_url = f"{domain}/cinema/{href}"
            found_links.add(full_url)

        # --- PART 2: Regex search for "url": "..." strings ---
        # This looks for the specific "url": "name-review" pattern in the text
        json_style_pattern = re.compile(r'"url":\s*"([^"]+)"')
        matches = json_style_pattern.findall(html_content)

        for match in matches:
            # We only care if it's a review link
            if "-review" in match:
                # Add .html if it's missing from the string
                clean_match = match if match.endswith(".html") else f"{match}.html"

                # Normalize URL
                if clean_match.startswith("http"):
                    full_url = clean_match
                elif clean_match.startswith("/"):
                    full_url = f"{domain}{clean_match}"
                else:
                    full_url = f"{domain}/cinema/{clean_match}"

                found_links.add(full_url)

        return sorted(list(found_links))

    except Exception as e:
        print(f"An error occurred: {e}")
        return []


# Run
review_list = get_flix_review_links()

print(f"--- Found {len(review_list)} unique review links ---")

flix_movie_links = review_list


def get_flix_rating(url):
    print(url)

    rating = None
    title = None
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # --- Get title ---
        title_tag = soup.find("h1")
        movie_title = title_tag.get_text(strip=True) if title_tag else None

        tag = soup.find("span", itemprop="aggregateRating")

        if tag and tag.has_attr("title"):
            title = tag["title"]  # e.g. "8 στα 10"

            match = re.search(r"(\d+)\s*στα\s*10", title)
            if match:
                rating = int(match.group(1))

        return rating, movie_title

    except Exception as e:
        print(f"Error with {url}: {e}")
        return None, None


results = []

for url in flix_movie_links:
    rating, movie_title = get_flix_rating(url)

    results.append({"url": url, "title": movie_title, "rating": rating})

# save json
with open("flix_ratings.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4, ensure_ascii=False)

print("Saved to flix_ratings.json")

# ============================================================================
# PART 2: Add ratings to movies.json
# ============================================================================

print("\n" + "=" * 80)
print("PART 3: ADDING RATINGS TO MOVIES.JSON")
print("=" * 80)


def normalize(text):
    """Normalize text for matching"""
    if not text:
        return ""

    text = text.lower().strip()

    # Remove accents
    text = "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )

    return text


# Load all data files
print("Loading data files...")
with open("movies.json", encoding="utf-8") as f:
    movies_data = json.load(f)

with open("flix_ratings.json", encoding="utf-8") as f:
    flix_data = json.load(f)

with open("lifo_ratings.json", encoding="utf-8") as f:
    lifo_data = json.load(f)

# Build lookup dictionaries for flix and lifo
print("Building lookup dictionaries...")
flix_lookup = {}
for item in flix_data:
    key = normalize(item["title"])
    flix_lookup[key] = {"rating": item["rating"], "url": item["url"]}

lifo_lookup = {}
for item in lifo_data:
    key = normalize(item["title"])
    lifo_lookup[key] = {"rating": item["rating"], "url": item["url"]}

# Match and update movies
print("Matching movies and adding ratings...")
flix_matches = 0
lifo_matches = 0
total_movies = 0

for group in movies_data:
    for movie in group:
        total_movies += 1

        # Try matching with greek title
        greek_key = normalize(movie["greek_title"])
        original_key = normalize(movie["original_title"])

        # Check flix
        if greek_key in flix_lookup or original_key in flix_lookup:
            match_data = flix_lookup.get(greek_key) or flix_lookup.get(original_key)
            movie["flix_rating"] = match_data["rating"]
            movie["flix_url"] = match_data["url"]
            flix_matches += 1
            print(f"  ✓ Flix match: {movie['greek_title']}")

        # Check lifo
        if greek_key in lifo_lookup or original_key in lifo_lookup:
            match_data = lifo_lookup.get(greek_key) or lifo_lookup.get(original_key)
            movie["lifo_rating"] = match_data["rating"]
            movie["lifo_url"] = match_data["url"]
            lifo_matches += 1
            print(f"  ✓ Lifo match: {movie['greek_title']}")

# Save updated movies.json
print("\nSaving updated movies.json...")
with open("movies.json", "w", encoding="utf-8") as f:
    json.dump(movies_data, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 60)
print(f"Total movies: {total_movies}")
print(f"Flix matches: {flix_matches}")
print(f"Lifo matches: {lifo_matches}")
print("=" * 60)
print("\n✓ Successfully updated movies.json")
