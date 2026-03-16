#!/usr/bin/env python3
"""Add Flix and Lifo ratings/URLs to movies.json"""

import json
import unicodedata


def normalize(text):
    """Normalize text for matching"""
    if not text:
        return ""

    text = text.lower().strip()

    # Remove accents
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
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
    flix_lookup[key] = {
        "rating": item["rating"],
        "url": item["url"]
    }

lifo_lookup = {}
for item in lifo_data:
    key = normalize(item["title"])
    lifo_lookup[key] = {
        "rating": item["rating"],
        "url": item["url"]
    }

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

print("\n" + "="*60)
print(f"Total movies: {total_movies}")
print(f"Flix matches: {flix_matches}")
print(f"Lifo matches: {lifo_matches}")
print("="*60)
print("\n✓ Successfully updated movies.json")
