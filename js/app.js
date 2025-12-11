let moviesData = [];
let cinemasData = [];

let currentTimeFilter = 'all'; // Track current time filter: 'all', 'today', 'next3'


// ✅ Dynamic title/meta updates
function updateMeta(title, description) {
    document.title = title;
    const descTag = document.querySelector('meta[name="description"]');
    if (descTag) descTag.setAttribute('content', description);
}

// ✅ Search filter function for dropdowns
function filterList(listId, query) {
    const list = document.getElementById(listId);
    const q = query.trim().toLowerCase();
    list.querySelectorAll('li').forEach(li => {
        const text = li.textContent.toLowerCase();
        li.style.display = text.includes(q) ? '' : 'none';
    });
}

// ✅ Clear all filters function
function clearAllFilters() {

    // Reset time filter state
    currentTimeFilter = 'all';
    // Uncheck all checkboxes
    document.querySelectorAll('#movieCheckboxes input[type="checkbox"]').forEach(cb => cb.checked = false);
    document.querySelectorAll('#cinemaCheckboxes input[type="checkbox"]').forEach(cb => cb.checked = false);
    document.querySelectorAll('#regionCheckboxes input[type="checkbox"]').forEach(cb => cb.checked = false);

    // Clear all search inputs
    document.querySelectorAll('.search-input').forEach(input => input.value = '');

    // Reset visibility of all filter items
    document.querySelectorAll('.checkbox-list li').forEach(li => li.style.display = '');

    // Hide all results info
    document.querySelectorAll('.results-info').forEach(info => {
        info.style.display = 'none';
    });
    // Show all results
    showAll();

    // Clear location-based summaries
    const summary = document.getElementById('nearbySummary');
    if (summary) summary.textContent = '';
    const addrInput = document.getElementById('addressInput');
    if (addrInput) addrInput.value = '';

    // Optional: Close all filter details
    document.querySelectorAll('#filters-container details').forEach(details => details.open = true);

    // Show feedback to user
    const btn = document.querySelector('.clear-btn');
    if (btn) {
        const originalText = btn.innerHTML;
        btn.innerHTML = '✅ Καθαρίστηκαν!';
        btn.style.background = '#28a745';
        setTimeout(() => {
            btn.innerHTML = originalText;
            btn.style.background = '#dc3545';
        }, 1500);
    }
}

// Add smooth scroll function
function smoothScrollToResults() {
    const results = document.getElementById('results');
    results.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Add function to show results count
function showResultsCount(infoId) {
    const movieElements = document.querySelectorAll('#results .movie');
    const movieCount = movieElements.length;
    const resultsText = document.querySelector('#results').textContent;
    const hasNoResults = resultsText.includes('Δεν υπάρχουν διαθέσιμες προβολές');

    // Hide all results info first
    document.querySelectorAll('.results-info').forEach(info => {
        info.style.display = 'none';
    });

    // Show the specific results info
    const infoDiv = document.getElementById(infoId);
    if (infoDiv) {
        if (hasNoResults || movieCount === 0) {
            infoDiv.innerHTML = `
        <p style="margin: 0.5em 0; color: #dc3545; font-weight: bold;">
          ❌ Δεν βρέθηκαν προβολές
        </p>
      `;
            infoDiv.classList.add('empty');
        } else {
            infoDiv.innerHTML = `
        <p style="margin: 0.5em 0; color: #28a745; font-weight: bold;">
          ✅ Βρέθηκαν ${movieCount} ${movieCount === 1 ? 'ταινία' : 'ταινίες'}
        </p>
        <button class="view-results-btn" onclick="smoothScrollToResults()">
          👇 Δες Αποτελέσματα
        </button>
      `;
            infoDiv.classList.remove('empty');
        }
        infoDiv.style.display = 'block';
    }
}

// ✅ Back to Top functionality
function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: 'smooth'
    });
}

// ✅ Show/hide back to top button based on scroll
function toggleBackToTopButton() {
    const backToTopBtn = document.getElementById('backToTop');
    if (window.pageYOffset > 300) {
        backToTopBtn.classList.add('show');
    } else {
        backToTopBtn.classList.remove('show');
    }
}

// ✅ Add scroll event listener
window.addEventListener('scroll', toggleBackToTopButton);

async function loadData() {
    const [moviesRes, cinemasRes] = await Promise.all([
        fetch('movies.json'),
        fetch('cinemas.json')
    ]);
    moviesData = await moviesRes.json();
    cinemasData = await cinemasRes.json();
    normalizeCoordinates(); // ← normalize lon -> lng and coerce to numbers
    populateCheckboxes();
    populateRegions();
    renderResults();
}

// ✅ Populate unique regions (checkbox list)
function populateRegions() {
    const allRegions = [...new Set(cinemasData.flat().map(c => c.region).filter(Boolean))].sort();
    const regionBox = document.getElementById('regionCheckboxes');
    regionBox.innerHTML = '';

    allRegions.forEach(region => {
        const li = document.createElement('li');
        li.innerHTML = `<label><input type="checkbox" value="${region}" onchange="renderResults()"> ${region}</label>`;
        regionBox.appendChild(li);
    });
}

// ✅ Movie + Cinema checkbox population
function populateCheckboxes() {
    const movieBox = document.getElementById('movieCheckboxes');
    movieBox.innerHTML = '';
    moviesData.forEach((m, i) => {
        const movie = m[0];
        const displayTitle = movie.original_title && movie.original_title.trim() !== ""
            ? `${movie.greek_title} (${movie.original_title})`
            : movie.greek_title;
        const li = document.createElement('li');
        li.innerHTML = `<label><input type="checkbox" value="${i}" onchange="renderResults()"> ${displayTitle}</label>`;
        movieBox.appendChild(li);
    });

    const allCinemas = [...new Set(cinemasData.flat(2).map(c => c.cinema))].sort();
    const cinemaBox = document.getElementById('cinemaCheckboxes');
    cinemaBox.innerHTML = '';
    allCinemas.forEach(name => {
        const li = document.createElement('li');
        li.innerHTML = `<label><input type="checkbox" value="${name}" onchange="renderResults()"> ${name}</label>`;
        cinemaBox.appendChild(li);
    });
}

// Distance in km using Haversine
function distanceKm(lat1, lon1, lat2, lon2) {
    const toRad = d => d * Math.PI / 180;
    const R = 6371;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return R * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)));
}

// “Near me” main action
// Also update the main filterNearMe function to include this logic
async function filterNearMe() {
    const btn = document.getElementById('nearMeBtn');
    const radiusInput = document.getElementById('radiusSelect');
    const summary = document.getElementById('nearbySummary');
    const radiusKm = parseFloat(radiusInput?.value) || 3;

    // Hide results info during search
    document.getElementById('nearbyResultsInfo').style.display = 'none';

    if (!cinemasData || !cinemasData.length) {
        summary.textContent = '⏳ Τα δεδομένα φορτώνουν, δοκίμασε ξανά σε λίγο.';
        return;
    }

    if (!('geolocation' in navigator)) {
        summary.textContent = '❌ Ο εντοπισμός τοποθεσίας δεν υποστηρίζεται στον περιηγητή.';
        return;
    }

    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '⌛ Εντοπισμός...';
    summary.textContent = '';

    navigator.geolocation.getCurrentPosition(
        (pos) => {
            const { latitude, longitude } = pos.coords;

            // Use the helper function which now clears region filters
            const { nearby, withoutCoords } = findAndSelectNearbyCinemas(latitude, longitude, radiusKm);

            if (nearby.length > 0) {
                const top3 = nearby.slice(0, 3).map(n => `${n.name} (${n.distance.toFixed(1)}km)`).join(' • ');
                summary.textContent = `✅ Βρέθηκαν ${nearby.length} σινεμά σε ακτίνα ${radiusKm}km. ${top3 ? 'Κοντινότερα: ' + top3 : ''}`;
                updateMeta('Σινεμά κοντά μου στην Αθήνα 🎯', `Δες σινεμά γύρω σου σε ακτίνα ${radiusKm}km και τι παίζουν τώρα.`);
                // Show results count after a short delay
                setTimeout(() => showResultsCount('nearbyResultsInfo'), 100);
            } else {
                summary.textContent = `ℹ️ Δεν βρέθηκαν σινεμά σε ακτίνα ${radiusKm}km. ${withoutCoords ? `(Χωρίς συντεταγμένες: ${withoutCoords})` : ''}`;
            }


            btn.textContent = originalText;
            btn.disabled = false;
        },
        (err) => {
            let msg = '❌ Αποτυχία εντοπισμού.';
            if (err.code === err.PERMISSION_DENIED) msg = '❌ Δεν δόθηκε άδεια τοποθεσίας.';
            else if (err.code === err.POSITION_UNAVAILABLE) msg = '❌ Η τοποθεσία δεν είναι διαθέσιμη.';
            else if (err.code === err.TIMEOUT) msg = '❌ Λήξη προθεσμίας εντοπισμού.';
            summary.textContent = `${msg} Μπορείς να επιλέξεις ακτίνα και να δοκιμάσεις ξανά.`;
            btn.textContent = originalText;
            btn.disabled = false;
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }
    );
}


function toNum(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n : undefined;
}

function normalizeCoordinates() {
    if (!Array.isArray(cinemasData) || !cinemasData.length) return;
    cinemasData.flat(2).forEach(c => {
        if (!c) return;
        const lat = toNum(c.lat);
        // accept both lng and lon in the source; normalize to lng
        const lng = toNum(c.lng != null ? c.lng : c.lon);

        if (Number.isFinite(lat)) c.lat = lat; else delete c.lat;
        if (Number.isFinite(lng)) c.lng = lng; else delete c.lng;
    });
}

function uniqueCinemasFromData() {
    const map = new Map();
    if (!Array.isArray(cinemasData) || !cinemasData.length) return map;

    cinemasData.flat(2).forEach(raw => {
        if (!raw || !raw.cinema) return;
        const name = raw.cinema;
        const lat = toNum(raw.lat);
        const lng = toNum(raw.lng);

        if (!map.has(name)) {
            map.set(name, { ...raw, lat, lng });
            return;
        }

        const current = map.get(name);
        const hasCurrent = Number.isFinite(current.lat) && Number.isFinite(current.lng);
        const hasNew = Number.isFinite(lat) && Number.isFinite(lng);
        if (!hasCurrent && hasNew) {
            map.set(name, { ...current, ...raw, lat, lng });
        }
    });

    return map;
}

// Helper: reuse the logic to find nearby cinemas and apply the checkbox selection
// Update the findAndSelectNearbyCinemas function to clear region filters
function findAndSelectNearbyCinemas(lat, lng, radiusKm) {
    const uniq = uniqueCinemasFromData();
    const nearby = [];
    let withoutCoords = 0;

    uniq.forEach((c, name) => {
        if (typeof c.lat === 'number' && typeof c.lng === 'number') {
            const d = distanceKm(lat, lng, c.lat, c.lng);
            if (isFinite(d) && d <= radiusKm) nearby.push({ name, distance: d });
        } else {
            withoutCoords++;
        }
    });

    nearby.sort((a, b) => a.distance - b.distance);

    // Clear region filters when using location-based filtering
    const regionInputs = document.querySelectorAll('#regionCheckboxes input[type="checkbox"]');
    regionInputs.forEach(cb => cb.checked = false);

    // Clear all cinema checkboxes first
    const cinemaInputs = document.querySelectorAll('#cinemaCheckboxes input[type="checkbox"]');
    cinemaInputs.forEach(cb => cb.checked = false);


    // Only check nearby cinemas if any were found
    if (nearby.length > 0) {
        const nearbyNames = new Set(nearby.map(n => n.name));
        cinemaInputs.forEach(cb => { if (nearbyNames.has(cb.value)) cb.checked = true; });
    }

    renderResults(null, true);

    return { nearby, withoutCoords };
}

async function geocodeAddress(query) {
    const url = 'https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&countrycodes=GR&q=' + encodeURIComponent(query);
    const res = await fetch(url, {
        headers: {
            'Accept': 'application/json',
            'Accept-Language': 'el-GR,el;q=0.9,en;q=0.8'
            // Note: Browsers don't allow setting User-Agent; Referer is set automatically.
        }
    });
    if (!res.ok) throw new Error('Geocoding failed');
    const json = await res.json();
    if (!Array.isArray(json) || json.length === 0) return null;
    const first = json[0];
    const lat = Number(first.lat);
    const lng = Number(first.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    return { lat, lng, label: first.display_name };
}

// Update the filterByAddress function to show the same message
async function filterByAddress() {
    const radiusInput = document.getElementById('radiusSelect');
    const summary = document.getElementById('nearbySummary');
    const addrInput = document.getElementById('addressInput');
    const addrBtn = document.getElementById('addressBtn');
    const radiusKm = parseFloat(radiusInput?.value) || 3;
    // Hide results info during search
    document.getElementById('nearbyResultsInfo').style.display = 'none';


    if (!cinemasData || !cinemasData.length) {
        summary.textContent = '⏳ Τα δεδομένα φορτώνουν, δοκίμασε ξανά σε λίγο.';
        return;
    }

    const q = (addrInput?.value || '').trim();
    if (!q) {
        summary.textContent = 'ℹ️ Πληκτρολόγησε μια διεύθυνση, περιοχή ή ΤΚ (π.χ. Σύνταγμα, 14343).';
        addrInput?.focus();
        return;
    }

    const originalText = addrBtn.textContent;
    addrBtn.disabled = true;
    addrBtn.textContent = '⌛ Αναζήτηση...';
    summary.textContent = '';

    try {
        const result = await geocodeAddress(q);
        if (!result) {
            summary.textContent = '❌ Δεν βρέθηκε η διεύθυνση. Δοκίμασε πιο συγκεκριμένα.';
            return;
        }

        const { lat, lng, label } = result;
        const { nearby, withoutCoords } = findAndSelectNearbyCinemas(lat, lng, radiusKm);

        if (nearby.length > 0) {
            const top3 = nearby.slice(0, 3).map(n => `${n.name} (${n.distance.toFixed(1)}km)`).join(' • ');
            summary.textContent = `✅ Βρέθηκαν ${nearby.length} σινεμά σε ακτίνα ${radiusKm}km από: ${label}. ${top3 ? 'Κοντινότερα: ' + top3 : ''} (Καθαρίστηκαν τα φίλτρα περιοχής)`;
            updateMeta('Σινεμά κοντά στη διεύθυνσή μου στην Αθήνα 🎯', `Βρες σινεμά γύρω από "${q}" σε ακτίνα ${radiusKm}km και δες τι παίζουν τώρα.`);
            // Show results count after a short delay
            setTimeout(() => showResultsCount('nearbyResultsInfo'), 100);
        } else {
            summary.textContent = `ℹ️ Δεν βρέθηκαν σινεμά σε ακτίνα ${radiusKm}km από: ${label}. ${withoutCoords ? `(Χωρίς συντεταγμένες: ${withoutCoords})` : ''}`;
        }
    } catch (e) {
        summary.textContent = '❌ Σφάλμα κατά την αναζήτηση διεύθυνσης. Προσπάθησε ξανά.';
    } finally {
        addrBtn.textContent = originalText;
        addrBtn.disabled = false;
    }
}
// Enter key triggers address search
window.addEventListener('DOMContentLoaded', () => {
    const addrInput = document.getElementById('addressInput');
    if (addrInput) {
        addrInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                filterByAddress();
            }
        });
    }
});


// ✅ Update the chips displayed above results
function updateFilterChips() {
    const container = document.getElementById("activeFilters");
    container.innerHTML = "";

    // Time filters
    if (currentTimeFilter === "today") addChip("Σήμερα", () => showAll());
    if (currentTimeFilter === "next3") addChip("Επόμενες 3 ώρες", () => showAll());

    // Movies
    document.querySelectorAll('#movieCheckboxes input:checked').forEach(cb => {
        const label = cb.parentElement.textContent.trim();
        addChip(label, () => { cb.checked = false; renderResults(); updateFilterChips(); });
    });

    // Cinemas
    document.querySelectorAll('#cinemaCheckboxes input:checked').forEach(cb => {
        const label = cb.parentElement.textContent.trim();
        addChip(label, () => { cb.checked = false; renderResults(); updateFilterChips(); });
    });

    // Regions
    document.querySelectorAll('#regionCheckboxes input:checked').forEach(cb => {
        const label = cb.parentElement.textContent.trim();
        addChip(label, () => { cb.checked = false; renderResults(); updateFilterChips(); });
    });
}

function addChip(label, removeFn) {
    const chip = document.createElement("div");
    chip.className = "filter-chip";
    chip.innerHTML = `${label} `;

    const btn = document.createElement("button");
    btn.textContent = "✕";
    btn.onclick = removeFn;

    chip.appendChild(btn);
    document.getElementById("activeFilters").appendChild(chip);
}


// ✅ Main rendering logic
// Replace the existing renderResults function with this version that respects time filters
function renderResults(filteredList, forceEmpty = false) {
    const results = document.getElementById('results');
    results.innerHTML = '';

    const selectedMovies = Array.from(document.querySelectorAll('#movieCheckboxes input:checked')).map(el => el.value);
    const selectedCinemas = Array.from(document.querySelectorAll('#cinemaCheckboxes input:checked')).map(el => el.value);
    const selectedRegions = Array.from(document.querySelectorAll('#regionCheckboxes input:checked')).map(el => el.value);

    // If forceEmpty is true and no cinemas are selected, show no results
    if (forceEmpty && selectedCinemas.length === 0) {
        results.innerHTML = '<p style="text-align:center;color:#666;">Δεν υπάρχουν διαθέσιμες προβολές.</p>';
        return;
    }

    // Apply time filtering if one is active
    let list = filteredList || cinemasData;
    if (currentTimeFilter === 'today') {
        list = applyTodayFilter(list);
    } else if (currentTimeFilter === 'next3') {
        list = applyNext3Filter(list);
    } else if (currentTimeFilter === 'all') {
        // Apply past time filter even when showing "all"
        list = filterPastTimesFromToday(list);
    }

    list.forEach((movieCinemas, idx) => {
        if (selectedMovies.length && !selectedMovies.includes(String(idx))) return;

        const movie = moviesData[idx]?.[0];
        if (!movie) return;

        const validCinemas = movieCinemas.filter(c => c.timetable && c.timetable.flat().length > 0);
        const cinemasToShow = selectedCinemas.length
            ? validCinemas.filter(c => selectedCinemas.includes(c.cinema))
            : validCinemas;

        const regionFiltered = selectedRegions.length
            ? cinemasToShow.filter(c => selectedRegions.includes(c.region))
            : cinemasToShow;

        if (regionFiltered.length === 0) return;

        // Create movie summary data
        const movieSummary = createMovieSummary(regionFiltered);
        const uniqueMovieId = `movie-${Math.random().toString(36).substr(2, 9)}`;

        const displayTitle = movie.athinorama_link
            ? `<a href="${movie.athinorama_link}" target="_blank" style="text-decoration: none;">
       ${movie.greek_title}${movie.original_title && movie.original_title.trim() !== ""
                ? ` <span style="font-size:0.9em;color:#777;">(${movie.original_title})</span>`
                : ''}
     </a>`
            : `${movie.greek_title}${movie.original_title && movie.original_title.trim() !== ""
                ? ` <span style="font-size:0.9em;color:#777;">(${movie.original_title})</span>`
                : ''}`;

        let externalLinks = '';
        if (movie.imdb_link && movie.imdb_link.trim() !== '') {
            externalLinks += `<a href="${movie.imdb_link}" target="_blank" class="imdb-link" title="Δες στο IMDB">
      <span style="font-weight:bold;">IMDb</span> ⭐
    </a>`;
        }
        // Add share button
        externalLinks += `<button class="share-btn" onclick="event.stopPropagation(); shareMovie(${idx})" title="Μοιράσου την ταινία">
      📤 Μοιράσου
    </button>`;

        const movieDiv = document.createElement('div');
        movieDiv.className = 'movie';

        // Create collapsible movie structure
        movieDiv.innerHTML = `
    <div class="movie-summary" onclick="toggleMovie('${uniqueMovieId}')">
      <div class="movie-summary-header">
        <h2 class="movie-summary-title">${displayTitle}</h2>
        <div class="external-links">
          ${externalLinks}
        </div>
      </div>
      <div class="movie-summary-info">
        <div class="movie-stats">
          <span class="cinema-count">${regionFiltered.length} κινηματογράφ${regionFiltered.length === 1 ? 'ος' : 'οι'}</span>
          ${movieSummary.nextShowtime ? `<span class="next-showing">Επόμενη: ${movieSummary.nextShowtime} - ${movieSummary.cinemaNames}</span>` : ''}
        </div>
        <span class="movie-toggle">▼</span>
      </div>
    </div>
    <div id="${uniqueMovieId}" class="movie-content">
      <!-- Cinemas will be added here -->
    </div>
  `;

        // Add cinemas to the movie content area
        const movieContent = movieDiv.querySelector('.movie-content');

        regionFiltered.forEach(cinema => {
            const timesList = cinema.timetable.flat().filter(t => t.trim() !== '');
            const sortedTimes = timesList.sort((a, b) => {
                const parsedA = parseShowtimeForSorting(a);
                const parsedB = parseShowtimeForSorting(b);
                return parsedA.sortValue - parsedB.sortValue;
            });

            const formattedTimes = sortedTimes.map(t => {
                const match = t.match(/([Α-Ωα-ωάέίόήύώΆΈΉΊΌΎΏ]+)\s*(\d{1,2}\s*[Α-Ωα-ωάέίόήύώΆΈΉΊΌΎΏ]*)?\s*(\d{2}:\d{2})/);
                if (match) {
                    const day = match[1]?.trim() || '';
                    const datePart = match[2]?.trim() || '';
                    const time = match[3];
                    const fullDate = [day, datePart].filter(Boolean).join(' ');
                    return `<span style="display:inline-block;margin:3px 6px;padding:4px 8px;background:#f5f5f5;border-radius:8px;">🕒 <strong>${time}</strong> — ${fullDate}</span>`;
                }
                return `<span style="display:inline-block;margin:3px 6px;padding:4px 8px;background:#f5f5f5;border-radius:8px;">${t}</span>`;
            }).join(' ');

            const c = document.createElement('div');
            c.className = 'cinema';

            // Create base cinema info
            let cinemaHTML = `
  <h3>${cinema.website && cinema.website !== null
                    ? `<a href="${cinema.website}" target="_blank" rel="noopener noreferrer" class="cinema-link" title="Επίσκεψη στον ιστότοπο">${cinema.cinema}</a>`
                    : cinema.cinema}</h3>
  <p>
    <a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(cinema.cinema + ' ' + cinema.address)}"
       target="_blank"
       rel="noopener noreferrer"
       title="Δες στο Google Maps">
      📍 ${cinema.address}
    </a>
  </p>
  ${cinema.region ? `<div style="font-size:0.9em;color:#777;">📍 ${cinema.region}</div>` : ''}
`;


            if (!formattedTimes) {
                // No showtimes available
                cinemaHTML += `<div class="showtimes-single"><em>Δεν υπάρχουν προβολές</em></div>`;
            } else if (sortedTimes.length === 1) {
                // Single showtime - display directly
                cinemaHTML += `<div class="showtimes-single">${formattedTimes}</div>`;
            } else {
                // Multiple showtimes - make collapsible
                const uniqueId = `showtimes-${Math.random().toString(36).substr(2, 9)}`;
                const nextShowtime = getNextShowtime(sortedTimes[0]);

                cinemaHTML += `
        <div class="cinema-showtimes">
          <div class="showtimes-summary" onclick="toggleShowtimes('${uniqueId}')">
            <div class="showtimes-summary-info">
              <span class="showtimes-count">${sortedTimes.length} προβολές</span>
              ${nextShowtime ? `<span class="next-showtime">Επόμενη: ${nextShowtime}</span>` : ''}
            </div>
            <span class="toggle-icon">▼</span>
          </div>
          <div id="${uniqueId}" class="showtimes-details">
            ${formattedTimes}
          </div>
        </div>
      `;
            }

            c.innerHTML = cinemaHTML;
            movieContent.appendChild(c);
        });

        results.appendChild(movieDiv);
    });



    if (!results.hasChildNodes()) {
        results.innerHTML = '<p style="text-align:center;color:#666;">Δεν υπάρχουν διαθέσιμες προβολές.</p>';
    }
    updateFilterChips();
}

// Filter out past times from today and past dates
function filterPastTimesFromToday(list) {
    const now = new Date();
    const todayDate = now.getDate();
    const todayMonth = now.getMonth();
    const todayYear = now.getFullYear();
    const nowMins = now.getHours() * 60 + now.getMinutes();

    return list.map(movie =>
        movie.map(cinema => {
            const newTimes = cinema.timetable.map(tt =>
                tt.filter(t => {
                    // Parse the showtime to get actual date
                    const parsed = parseShowtimeForSorting(t);
                    const showtimeDate = new Date(parsed.sortValue);

                    // If date is before today, filter it out
                    const showtimeDateOnly = new Date(showtimeDate.getFullYear(), showtimeDate.getMonth(), showtimeDate.getDate());
                    const todayOnly = new Date(todayYear, todayMonth, todayDate);

                    if (showtimeDateOnly < todayOnly) {
                        return false;
                    }

                    // If it's today, check the time
                    if (showtimeDate.getDate() === todayDate &&
                        showtimeDate.getMonth() === todayMonth &&
                        showtimeDate.getFullYear() === todayYear) {
                        const timeMatch = t.match(/(\d{2}):(\d{2})/);
                        if (timeMatch) {
                            const mins = parseInt(timeMatch[1]) * 60 + parseInt(timeMatch[2]);
                            return mins >= nowMins; // Only show future times for today
                        }
                    }

                    // Keep future dates
                    return true;
                })
            );
            return { ...cinema, timetable: newTimes };
        })
    );
}



// Add these helper functions for time filtering
// Apply today filter - only show today's showtimes
function applyTodayFilter(list) {
    const now = new Date();
    const todayName = now.toLocaleDateString('el-GR', { weekday: 'long' });
    const todayDate = now.getDate();
    const todayMonth = now.getMonth();
    const todayYear = now.getFullYear();
    const nowMins = now.getHours() * 60 + now.getMinutes();

    return list.map(movie =>
        movie.map(cinema => {
            const newTimes = cinema.timetable.map(tt =>
                tt.filter(t => {
                    // Parse the showtime to get actual date
                    const parsed = parseShowtimeForSorting(t);
                    const showtimeDate = new Date(parsed.sortValue);

                    // Check if it's today
                    const isToday = showtimeDate.getDate() === todayDate &&
                        showtimeDate.getMonth() === todayMonth &&
                        showtimeDate.getFullYear() === todayYear;

                    if (!isToday) return false;

                    // If it's today, check if the time hasn't passed
                    const timeMatch = t.match(/(\d{2}):(\d{2})/);
                    if (!timeMatch) return false;

                    const mins = parseInt(timeMatch[1]) * 60 + parseInt(timeMatch[2]);
                    return mins >= nowMins;
                })
            );
            return { ...cinema, timetable: newTimes };
        })
    );
}


// Apply next 3 hours filter - only show today's showtimes within next 3 hours
function applyNext3Filter(list) {
    const now = new Date();
    const todayDate = now.getDate();
    const todayMonth = now.getMonth();
    const todayYear = now.getFullYear();
    const nowMins = now.getHours() * 60 + now.getMinutes();
    const next3Mins = nowMins + 180;

    return list.map(movie =>
        movie.map(cinema => {
            const newTimes = cinema.timetable.map(tt =>
                tt.filter(t => {
                    // Parse the showtime to get actual date
                    const parsed = parseShowtimeForSorting(t);
                    const showtimeDate = new Date(parsed.sortValue);

                    // Check if it's today
                    const isToday = showtimeDate.getDate() === todayDate &&
                        showtimeDate.getMonth() === todayMonth &&
                        showtimeDate.getFullYear() === todayYear;

                    if (!isToday) return false;

                    // If it's today, check if it's within the next 3 hours
                    const timeMatch = t.match(/(\d{2}):(\d{2})/);
                    if (!timeMatch) return false;

                    const mins = parseInt(timeMatch[1]) * 60 + parseInt(timeMatch[2]);
                    return mins >= nowMins && mins <= next3Mins;
                })
            );
            return { ...cinema, timetable: newTimes };
        })
    );
}


// Update the time filter functions to track state
function filterToday() {
    currentTimeFilter = 'today';
    renderResults();
    updateFilterChips();
    highlightButton('todayBtn');
    setTimeout(() => showResultsCount('todayResultsInfo'), 100);
    updateMeta('Τι Παίζει Σήμερα στα Σινεμά της Αθήνας 🎬', 'Δες ποιες ταινίες παίζονται σήμερα στα σινεμά της Αθήνας με ώρες προβολών και αίθουσες.');
}

function filterNext3() {
    currentTimeFilter = 'next3';
    renderResults();
    updateFilterChips();
    highlightButton('next3Btn');
    setTimeout(() => showResultsCount('next3ResultsInfo'), 100);
    updateMeta('Ταινίες στις Επόμενες 3 Ώρες στα Σινεμά της Αθήνας ⏰', 'Ανακάλυψε ποιες ταινίες παίζονται μέσα στις επόμενες 3 ώρες στα σινεμά της Αθήνας.');
}

function showAll() {
    currentTimeFilter = 'all';
    renderResults();
    updateFilterChips();
    highlightButton('allBtn');
    // Hide all results info when showing all
    document.querySelectorAll('.results-info').forEach(info => {
        info.style.display = 'none';
    });
    updateMeta('Σινεμά Αθήνας – Όλες οι Ταινίες & Προβολές', 'Ο πλήρης οδηγός σινεμά της Αθήνας. Δες όλες τις ταινίες, ώρες προβολών και κινηματογράφους.');
}

function highlightButton(id) {
    document.querySelectorAll('.filter-buttons button').forEach(btn => btn.style.outline = 'none');
    const btn = document.getElementById(id);
    if (btn) btn.style.outline = '3px solid #222';
}

// Share movie function with Web Share API support
async function shareMovie(movieIndex) {
    const movie = moviesData[movieIndex]?.[0];
    if (!movie) return;

    // Construct share URL
    let shareUrl;
    if (movie.slug && movie.slug.trim() !== '') {
        shareUrl = `${window.location.origin}/movie/${movie.slug}/index.html`;
    } else if (movie.athinorama_link && movie.athinorama_link.trim() !== '') {
        shareUrl = movie.athinorama_link;
    } else {
        shareUrl = window.location.href;
    }

    const shareTitle = movie.greek_title + (movie.original_title ? ` (${movie.original_title})` : '');
    const shareText = `Δες πού παίζεται η ταινία "${shareTitle}" στα σινεμά της Αθήνας`;

    // Try native Web Share API first (mobile-friendly)
    if (navigator.share) {
        try {
            await navigator.share({
                title: shareTitle,
                text: shareText,
                url: shareUrl
            });
        } catch (err) {
            // User cancelled or error occurred
            if (err.name !== 'AbortError') {
                console.error('Share failed:', err);
                fallbackCopyToClipboard(shareUrl);
            }
        }
    } else {
        // Fallback: copy to clipboard
        fallbackCopyToClipboard(shareUrl);
    }
}

// Fallback function to copy URL to clipboard
function fallbackCopyToClipboard(url) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(() => {
            showShareFeedback('✅ Ο σύνδεσμος αντιγράφηκε!');
        }).catch(() => {
            showShareFeedback('❌ Αποτυχία αντιγραφής');
        });
    } else {
        // Older fallback method
        const textarea = document.createElement('textarea');
        textarea.value = url;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand('copy');
            showShareFeedback('✅ Ο σύνδεσμος αντιγράφηκε!');
        } catch (err) {
            showShareFeedback('❌ Αποτυχία αντιγραφής');
        }
        document.body.removeChild(textarea);
    }
}

// Show temporary feedback message
function showShareFeedback(message) {
    const feedback = document.createElement('div');
    feedback.textContent = message;
    feedback.style.cssText = `
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: #333;
        color: white;
        padding: 12px 24px;
        border-radius: 8px;
        z-index: 10000;
        font-size: 14px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    `;
    document.body.appendChild(feedback);
    setTimeout(() => {
        feedback.remove();
    }, 2500);
}


// Function to toggle showtimes visibility
function toggleShowtimes(elementId) {
    const detailsElement = document.getElementById(elementId);
    const summaryElement = detailsElement.previousElementSibling;

    if (detailsElement.classList.contains('expanded')) {
        detailsElement.classList.remove('expanded');
        summaryElement.classList.remove('expanded');
    } else {
        detailsElement.classList.add('expanded');
        summaryElement.classList.add('expanded');
    }
}

// Helper function to create movie summary with next showtime info
function createMovieSummary(cinemas) {
    const now = new Date();
    const todayName = now.toLocaleDateString('el-GR', { weekday: 'long' });
    const todayDate = now.getDate();
    const todayMonth = now.getMonth();
    const todayYear = now.getFullYear();
    const nowMins = now.getHours() * 60 + now.getMinutes();

    // Greek month names for parsing
    const greekMonths = ['Ιαν', 'Φεβ', 'Μαρ', 'Απρ', 'Μαΐ', 'Ιουν', 'Ιουλ', 'Αυγ', 'Σεπ', 'Οκτ', 'Νοε', 'Δεκ'];

    let earliestTime = null;
    let earliestTimestamp = Infinity;
    const cinemasWithEarliestTime = [];

    cinemas.forEach(cinema => {
        let timesList = cinema.timetable.flat().filter(t => t.trim() !== '');

        // Filter out past times from today
        timesList = timesList.filter(t => {
            // Try to extract date components
            const dateMatch = t.match(/(\d{1,2})\s*([Α-Ωα-ωάέίόήύώΆΈΉΊΌΎΏ]+)/);
            if (dateMatch) {
                const dayNum = parseInt(dateMatch[1]);
                const monthStr = dateMatch[2];

                // Try to find month index
                const monthIndex = greekMonths.findIndex(m => monthStr.includes(m));

                if (monthIndex !== -1) {
                    // We have a full date - check if it's in the past
                    const showtimeDate = new Date(todayYear, monthIndex, dayNum);

                    // Handle year boundary
                    if (todayMonth === 11 && monthIndex === 0) {
                        showtimeDate.setFullYear(todayYear + 1);
                    }

                    // If date is before today, filter it out
                    if (showtimeDate < new Date(todayYear, todayMonth, todayDate)) {
                        return false;
                    }

                    // If it's today, check the time
                    if (showtimeDate.getDate() === todayDate &&
                        showtimeDate.getMonth() === todayMonth &&
                        showtimeDate.getFullYear() === todayYear) {
                        const timeMatch = t.match(/(\d{2}):(\d{2})/);
                        if (timeMatch) {
                            const mins = parseInt(timeMatch[1]) * 60 + parseInt(timeMatch[2]);
                            return mins >= nowMins; // Only show future times for today
                        }
                    }
                } else if (t.includes(todayName) && dayNum === todayDate) {
                    // This is today (matched by weekday name) - check time
                    const timeMatch = t.match(/(\d{2}):(\d{2})/);
                    if (timeMatch) {
                        const mins = parseInt(timeMatch[1]) * 60 + parseInt(timeMatch[2]);
                        return mins >= nowMins; // Only show future times for today
                    }
                }
            }

            // Keep the showtime if we couldn't parse it properly or it's in the future
            return true;
        });

        if (timesList.length === 0) return;

        // Sort the filtered times using our enhanced sorting
        const sortedTimes = timesList.sort((a, b) => {
            const parsedA = parseShowtimeForSorting(a);
            const parsedB = parseShowtimeForSorting(b);
            return parsedA.sortValue - parsedB.sortValue;
        });

        // Get the earliest future showtime for this cinema
        const firstShowtimeString = sortedTimes[0];
        const firstShowtimeParsed = parseShowtimeForSorting(firstShowtimeString);

        if (firstShowtimeParsed.sortValue < earliestTimestamp) {
            earliestTime = formatNextShowtime(firstShowtimeString);
            earliestTimestamp = firstShowtimeParsed.sortValue;
            cinemasWithEarliestTime.length = 0; // Clear array
            cinemasWithEarliestTime.push(cinema.cinema);
        } else if (firstShowtimeParsed.sortValue === earliestTimestamp) {
            cinemasWithEarliestTime.push(cinema.cinema);
        }
    });

    return {
        nextShowtime: earliestTime,
        cinemaNames: cinemasWithEarliestTime.length > 0
            ? cinemasWithEarliestTime.join(', ')
            : null
    };
}


// Function to toggle movie visibility
function toggleMovie(elementId) {
    const contentElement = document.getElementById(elementId);
    const summaryElement = contentElement.previousElementSibling;

    // Prevent event bubbling when clicking on external links
    if (event.target.closest('.external-links a')) {
        return;
    }

    if (contentElement.classList.contains('expanded')) {
        // Collapse
        contentElement.classList.remove('expanded');
        summaryElement.classList.remove('expanded');
    } else {
        // Expand
        contentElement.classList.add('expanded');
        summaryElement.classList.add('expanded');
    }
}


// Helper function to extract and format next showtime with day info
function getNextShowtime(timeString) {
    return formatNextShowtime(timeString);
}

// Function to toggle showtimes visibility (keep existing one)
function toggleShowtimes(elementId) {
    const detailsElement = document.getElementById(elementId);
    const summaryElement = detailsElement.previousElementSibling;

    if (detailsElement.classList.contains('expanded')) {
        detailsElement.classList.remove('expanded');
        summaryElement.classList.remove('expanded');
    } else {
        detailsElement.classList.add('expanded');
        summaryElement.classList.add('expanded');
    }
}

// Enhanced sorting function that considers both date and time
function parseShowtimeForSorting(timeString) {
    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonth = now.getMonth(); // 0-indexed (December = 11, January = 0)

    // Greek month abbreviations
    const greekMonths = ['Ιαν', 'Φεβ', 'Μαρ', 'Απρ', 'Μαΐ', 'Ιουν', 'Ιουλ', 'Αυγ', 'Σεπ', 'Οκτ', 'Νοε', 'Δεκ'];

    // Extract time
    const timeMatch = timeString.match(/(\d{2}):(\d{2})/);
    if (!timeMatch) return { sortValue: Infinity, timeString };

    const hours = parseInt(timeMatch[1]);
    const minutes = parseInt(timeMatch[2]);

    // Try to extract date components
    const dateMatch = timeString.match(/([Α-Ωα-ωάέίόήύώΆΈΉΊΌΎΏ]+)\s*(\d{1,2})\s*([Α-Ωα-ωάέίόήύώΆΈΉΊΌΎΏ\.]+)?/);

    if (dateMatch) {
        const dayName = dateMatch[1];
        const dayNum = parseInt(dateMatch[2]);
        const monthStr = dateMatch[3];

        if (monthStr) {
            // Clean month string and find index
            const cleanMonthStr = monthStr.replace('.', '');
            const monthIndex = greekMonths.findIndex(m => m === cleanMonthStr);

            if (monthIndex !== -1) {
                // Default: use current year
                let targetYear = currentYear;

                // Only use next year if we're in December (11) and the showtime is in January (0)
                if (currentMonth === 11 && monthIndex === 0) {
                    targetYear = currentYear + 1;
                }

                const targetDate = new Date(targetYear, monthIndex, dayNum, hours, minutes);

                return {
                    sortValue: targetDate.getTime(),
                    timeString
                };
            }
        }

        // Fallback: assume current month and current year
        const targetDate = new Date(currentYear, currentMonth, dayNum, hours, minutes);

        return {
            sortValue: targetDate.getTime(),
            timeString
        };
    }

    // Final fallback: use today's date with the time
    const fallbackDate = new Date(currentYear, currentMonth, now.getDate(), hours, minutes);

    return {
        sortValue: fallbackDate.getTime(),
        timeString
    };
}


// Enhanced function to format showtime with smart date display
function formatNextShowtime(timeString) {
    const timeMatch = timeString.match(/(\d{2}):(\d{2})/);
    if (!timeMatch) return null;

    const time = timeMatch[0]; // e.g., "19:30"

    // Use our parsing function to get the actual date
    const parsed = parseShowtimeForSorting(timeString);
    const showtimeDate = new Date(parsed.sortValue);

    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    const showtimeDateOnly = new Date(showtimeDate.getFullYear(), showtimeDate.getMonth(), showtimeDate.getDate());

    // Compare dates and format accordingly
    if (showtimeDateOnly.getTime() === today.getTime()) {
        // Today - just show time
        return time;
    } else if (showtimeDateOnly.getTime() === tomorrow.getTime()) {
        // Tomorrow
        return `Αύριο ${time}`;
    } else {
        // After tomorrow - show full date info
        // Try to extract original date info first
        const dateMatch = timeString.match(/([Α-Ωα-ωάέίόήύώΆΈΉΊΌΎΏ]+)\s*(\d{1,2})\s*([Α-Ωα-ωάέίόήύώΆΈΉΊΌΎΏ\.]+)?/);

        if (dateMatch) {
            const dayName = dateMatch[1];
            const dayNum = dateMatch[2];
            const monthStr = dateMatch[3];

            if (monthStr) {
                // Full date with month
                return `${dayName} ${dayNum} ${monthStr.replace('.', '')} ${time}`;
            } else {
                // Day name with date but no month - add current month
                const currentMonthName = showtimeDate.toLocaleDateString('el-GR', { month: 'short' });
                return `${dayName} ${dayNum} ${currentMonthName} ${time}`;
            }
        }

        // Fallback to formatted date
        const formatted = showtimeDate.toLocaleDateString('el-GR', {
            weekday: 'long',
            day: 'numeric',
            month: 'short'
        });

        return `${formatted} ${time}`;
    }
}


loadData();