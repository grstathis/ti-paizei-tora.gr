let moviesData = [];
let cinemasData = [];

let currentTimeFilter = 'all'; // Track current time filter: 'all', 'today', 'next3'
let timeWindowMinutes = 180; // Track selected time window in minutes (default 3 hours)

// ============ GOOGLE MAPS DISTANCE MATRIX CONFIGURATION ============
const GOOGLE_MAPS_API_KEY = 'AIzaSyCmtiYOOYxmmwczkvXooICM4IwyEnb0jsE'; // TODO: Add your Google Maps API key here
const MAX_DISTANCE_KM = 5; // Pre-filter cinemas within 5km before calling API
let userLocation = null; // Store user's location { lat, lng }
let travelTimesCache = {}; // Cache travel times: { cinemaName: { walking: 15, driving: 8, transit: 12 } }
let canIMakeItActive = false; // Track if "Can I Make It" filter is active
let distanceMatrixService = null; // Google Maps DistanceMatrixService instance

// Load Google Maps API dynamically
function loadGoogleMapsAPI() {
    return new Promise((resolve, reject) => {
        if (window.google && window.google.maps) {
            resolve();
            return;
        }

        if (!GOOGLE_MAPS_API_KEY) {
            reject(new Error('Google Maps API key not configured'));
            return;
        }

        const script = document.createElement('script');
        script.src = `https://maps.googleapis.com/maps/api/js?key=${GOOGLE_MAPS_API_KEY}&libraries=places`;
        script.async = true;
        script.defer = true;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error('Failed to load Google Maps API'));
        document.head.appendChild(script);
    });
}

// Greek to Latin transliteration map (ported from Python)
const GREEK_TO_LATIN = {
    // lowercase
    'α': 'a', 'ά': 'a', 'β': 'v', 'γ': 'g', 'δ': 'd', 'ε': 'e', 'έ': 'e',
    'ζ': 'z', 'η': 'i', 'ή': 'i', 'θ': 'th', 'ι': 'i', 'ί': 'i', 'ϊ': 'i',
    'ΐ': 'i', 'κ': 'k', 'λ': 'l', 'μ': 'm', 'ν': 'n', 'ξ': 'x', 'ο': 'o',
    'ό': 'o', 'π': 'p', 'ρ': 'r', 'σ': 's', 'ς': 's', 'τ': 't', 'υ': 'y',
    'ύ': 'y', 'ϋ': 'y', 'ΰ': 'y', 'φ': 'f', 'χ': 'x', 'ψ': 'ps', 'ω': 'o',
    'ώ': 'o',
    // uppercase
    'Α': 'a', 'Ά': 'a', 'Β': 'v', 'Γ': 'g', 'Δ': 'd', 'Ε': 'e', 'Έ': 'e',
    'Ζ': 'z', 'Η': 'i', 'Ή': 'i', 'Θ': 'th', 'Ι': 'i', 'Ί': 'i', 'Ϊ': 'i',
    'Κ': 'k', 'Λ': 'l', 'Μ': 'm', 'Ν': 'n', 'Ξ': 'x', 'Ο': 'o', 'Ό': 'o',
    'Π': 'p', 'Ρ': 'r', 'Σ': 's', 'Τ': 't', 'Υ': 'y', 'Ύ': 'y', 'Ϋ': 'y',
    'Φ': 'f', 'Χ': 'x', 'Ψ': 'ps', 'Ω': 'o', 'Ώ': 'o'
};

function transliterateGreek(text) {
    return text.split('').map(ch => GREEK_TO_LATIN[ch] || ch).join('');
}

function slugify(text) {
    if (!text) return '';
    text = transliterateGreek(text);
    text = text.toLowerCase();
    text = text.replace(/[^a-z0-9]+/g, '-');
    text = text.replace(/-+/g, '-');
    return text.replace(/^-|-$/g, '');
}

// Parse showtime string to extract date and time for URL generation
function parseShowtimeForUrl(showtimeStr) {
    // Greek month abbreviations
    const greekMonths = {
        'Ιαν': '01', 'Φεβ': '02', 'Μαρ': '03', 'Απρ': '04',
        'Μαΐ': '05', 'Ιουν': '06', 'Ιουλ': '07', 'Αυγ': '08',
        'Σεπ': '09', 'Οκτ': '10', 'Νοε': '11', 'Δεκ': '12'
    };

    // Extract date and time: "Κυριακή 07 Δεκ. 16:00"
    const match = showtimeStr.match(/(\d{1,2})\s+([Α-Ωα-ωάέίόήύώΆΈΉΊΌΎΏ\.]+)\s+(\d{2}):(\d{2})/);

    if (!match) return null;

    const day = match[1].padStart(2, '0');
    const monthStr = match[2].replace('.', '').trim();
    const hour = match[3];
    const minute = match[4];

    // Find month number
    const month = greekMonths[monthStr];
    if (!month) return null;

    // Determine year (handle December -> January transition)
    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonth = now.getMonth() + 1; // 1-indexed

    let year = currentYear;
    // If current month is December (12) and showtime is January (01), use next year
    if (currentMonth === 12 && month === '01') {
        year = currentYear + 1;
    }

    return {
        date: `${year}-${month}-${day}`,
        time: `${hour}-${minute}`,
        fullShowtime: showtimeStr
    };
}

// Generate URL for a specific showtime
function generateShowtimeUrl(movie, cinema, showtimeStr) {
    // Parse the showtime
    const parsed = parseShowtimeForUrl(showtimeStr);
    if (!parsed) return null;

    // Get movie slug (already exists in movie data)
    const movieSlug = movie.slug;
    if (!movieSlug) return null;

    // Create slugs for region and cinema
    const regionSlug = slugify(cinema.region);
    const cinemaSlug = slugify(cinema.cinema);

    if (!regionSlug || !cinemaSlug) return null;

    // Build URL: region/{region}/cinema/{cinema}/movie/{movie}/date/time.html
    const url = `region/${regionSlug}/cinema/${cinemaSlug}/movie/${movieSlug}/${parsed.date}/${parsed.time}.html`;

    return url;
}


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

    // Initialize FAB tooltip hint for first-time visitors
    initializeFABHint();
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

// ============ "CAN I MAKE IT" TRAVEL TIME FUNCTIONS ============

// Get travel times from Google Maps Distance Matrix API using JavaScript SDK
async function getTravelTimes(userLat, userLng, cinemas) {
    if (!GOOGLE_MAPS_API_KEY) {
        console.error('Google Maps API key not configured');
        return {};
    }

    // Load Google Maps API if not already loaded
    try {
        await loadGoogleMapsAPI();
    } catch (error) {
        console.error('Failed to load Google Maps API:', error);
        return {};
    }

    // Pre-filter cinemas within 10km radius
    const nearbyCinemas = cinemas.filter(cinema => {
        if (typeof cinema.lat !== 'number' || typeof cinema.lon !== 'number') return false;
        const distance = distanceKm(userLat, userLng, cinema.lat, cinema.lon);
        return distance <= MAX_DISTANCE_KM;
    });

    if (nearbyCinemas.length === 0) {
        return {};
    }

    // Initialize DistanceMatrixService
    if (!distanceMatrixService) {
        distanceMatrixService = new google.maps.DistanceMatrixService();
    }

    const origin = new google.maps.LatLng(userLat, userLng);
    const destinations = nearbyCinemas.map(c => new google.maps.LatLng(c.lat, c.lon));

    // Fetch travel times for all 3 modes
    const modes = [
        { key: 'walking', mode: google.maps.TravelMode.WALKING },
        { key: 'driving', mode: google.maps.TravelMode.DRIVING },
        { key: 'transit', mode: google.maps.TravelMode.TRANSIT }
    ];

    const results = {};

    try {
        // Call API for each mode
        for (const { key, mode } of modes) {
            const request = {
                origins: [origin],
                destinations: destinations,
                travelMode: mode,
                unitSystem: google.maps.UnitSystem.METRIC
            };

            // Add departure time for transit to get real-time schedules
            if (mode === google.maps.TravelMode.TRANSIT || mode === google.maps.TravelMode.DRIVING) {
                request.drivingOptions = {
                    departureTime: new Date(),
                    trafficModel: google.maps.TrafficModel.BEST_GUESS
                };
            }

            // Wrap callback in Promise
            const response = await new Promise((resolve, reject) => {
                distanceMatrixService.getDistanceMatrix(request, (response, status) => {
                    if (status === 'OK') {
                        resolve(response);
                    } else {
                        console.warn(`Distance Matrix API error for mode ${key}:`, status);
                        resolve(null);
                    }
                });
            });

            if (response && response.rows && response.rows[0]) {
                const elements = response.rows[0].elements;

                nearbyCinemas.forEach((cinema, idx) => {
                    if (!results[cinema.cinema]) {
                        results[cinema.cinema] = {};
                    }

                    if (elements[idx] && elements[idx].status === 'OK') {
                        const durationMinutes = Math.ceil(elements[idx].duration.value / 60);
                        results[cinema.cinema][key] = durationMinutes;
                    }
                });
            }
        }

        return results;
    } catch (error) {
        console.error('Error fetching travel times:', error);
        return {};
    }
}

// Activate "Can I Make It" filter
async function activateCanIMakeIt() {
    const btn = document.getElementById('canIMakeItFAB'); // Updated to FAB button
    const modal = document.getElementById('locationModal');

    // Check if API key is configured
    if (!GOOGLE_MAPS_API_KEY) {
        alert('⚠️ Η λειτουργία "Τι προλαβαίνω;" δεν είναι διαθέσιμη. Απαιτείται Google Maps API key.');
        return;
    }

    // Check if geolocation is supported
    if (!navigator.geolocation) {
        alert('⚠️ Ο browser σου δεν υποστηρίζει geolocation.');
        return;
    }

    // Show loading state
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '⌛';

    // Request location
    navigator.geolocation.getCurrentPosition(
        async (pos) => {
            const { latitude, longitude } = pos.coords;
            userLocation = { lat: latitude, lng: longitude };

            // Use existing nearby filter to select cinemas within 10km
            const { nearby, withoutCoords } = findAndSelectNearbyCinemas(latitude, longitude, MAX_DISTANCE_KM);

            // Get all unique cinemas for travel time calculation
            const uniqueCinemas = [];
            const cinemaNames = new Set();

            cinemasData.forEach(movieCinemas => {
                movieCinemas.forEach(cinema => {
                    if (!cinemaNames.has(cinema.cinema)) {
                        cinemaNames.add(cinema.cinema);
                        uniqueCinemas.push(cinema);
                    }
                });
            });

            // Show fetching state
            btn.textContent = '🔍';

            // Fetch travel times
            travelTimesCache = await getTravelTimes(latitude, longitude, uniqueCinemas);

            console.log('✅ Travel times fetched:', Object.keys(travelTimesCache).length, 'cinemas');
            console.log('Sample:', Object.entries(travelTimesCache).slice(0, 3));

            // Activate the filter
            canIMakeItActive = true;
            btn.textContent = '✅';
            btn.classList.add('active');
            btn.disabled = false;

            // Automatically apply "next 30 minutes" filter
            const timeSelect = document.getElementById('timeWindowSelect');
            if (timeSelect) {
                timeSelect.value = '30'; // Set to 30 minutes
            }
            timeWindowMinutes = 30;
            currentTimeFilter = 'next3'; // Reuse next3 filter logic

            // Re-render results with travel times and time filter
            renderResults();
            updateFilterChips();

            // Show success message in nearby summary area
            const summary = document.getElementById('nearbySummary');
            if (summary && nearby.length > 0) {
                const top3 = nearby.slice(0, 3).map(n => `${n.name} (${n.distance.toFixed(1)}km)`).join(' • ');
                summary.textContent = `✅ Βρέθηκαν ${nearby.length} σινεμά σε ακτίνα ${MAX_DISTANCE_KM}km. ${top3 ? 'Κοντινότερα: ' + top3 : ''}`;
                setTimeout(() => showResultsCount('nearbyResultsInfo'), 100);
            }
        },
        (error) => {
            // Location permission denied or error
            btn.disabled = false;
            btn.textContent = originalText;

            // Show modal explaining why we need location
            if (modal) {
                modal.style.display = 'flex';
            } else {
                let message = '📍 Χρειαζόμαστε την τοποθεσία σου για να υπολογίσουμε τους χρόνους μετακίνησης.\n\n';
                if (error.code === error.PERMISSION_DENIED) {
                    message += 'Άρνηση πρόσβασης στην τοποθεσία. Παρακαλώ ενεργοποίησέ την στις ρυθμίσεις του browser σου.';
                } else if (error.code === error.POSITION_UNAVAILABLE) {
                    message += 'Δεν μπόρεσε να προσδιοριστεί η τοποθεσία σου.';
                } else {
                    message += 'Timeout στον εντοπισμό τοποθεσίας.';
                }
                alert(message);
            }
        },
        {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0
        }
    );
}

// Deactivate "Can I Make It" filter
function deactivateCanIMakeIt() {
    canIMakeItActive = false;
    travelTimesCache = {};
    userLocation = null;

    const btn = document.getElementById('canIMakeItFAB'); // Updated to FAB button
    if (btn) {
        btn.textContent = '🚶';
        btn.classList.remove('active');
    }

    // Clear nearby summary
    const summary = document.getElementById('nearbySummary');
    if (summary) {
        summary.textContent = '';
    }

    // Clear cinema checkbox selections (revert to showing all cinemas)
    const cinemaInputs = document.querySelectorAll('#cinemaCheckboxes input[type="checkbox"]');
    cinemaInputs.forEach(cb => cb.checked = false);

    // Reset time filter to 'all'
    currentTimeFilter = 'all';
    timeWindowMinutes = 180; // Reset to default 3 hours
    const timeSelect = document.getElementById('timeWindowSelect');
    if (timeSelect) {
        timeSelect.value = '180';
    }

    // Re-render without travel times and time filter
    renderResults();
    updateFilterChips();
}

// Toggle "Can I Make It" filter
function toggleCanIMakeIt() {
    if (canIMakeItActive) {
        deactivateCanIMakeIt();
    } else {
        activateCanIMakeIt();
    }
}

// Close location permission modal
function closeLocationModal() {
    const modal = document.getElementById('locationModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// Format travel time for display
function formatTravelTime(minutes) {
    if (minutes < 60) {
        return `${minutes}'`;
    }
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return mins > 0 ? `${hours}ω ${mins}'` : `${hours}ω`;
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
    if (currentTimeFilter === "next3") {
        const timeLabel = timeWindowMinutes === 30 ? "Επόμενα 30'" :
                          timeWindowMinutes === 60 ? "Επόμενη 1ω" : "Επόμενες 3ω";
        addChip(timeLabel, () => showAll());
    }

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


// ✅ Special rendering for "Can I Make It" mode
function renderCanIMakeItResults() {
    const results = document.getElementById('results');
    results.innerHTML = '';

    // Show banner
    const banner = document.createElement('div');
    banner.style.cssText = 'background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1em; border-radius: 10px; margin-bottom: 1.5em; text-align: center; font-weight: 600;';
    banner.innerHTML = `
        🚶 Τι προλαβαίνω; - Προβολές σε ακτίνα ${MAX_DISTANCE_KM}km τα επόμενα ${timeWindowMinutes} λεπτά
        <button onclick="deactivateCanIMakeIt()" style="margin-left: 1em; padding: 0.5em 1em; background: rgba(255,255,255,0.2); border: 1px solid white; color: white; border-radius: 5px; cursor: pointer;">
            ✕ Απενεργοποίηση
        </button>
    `;
    results.appendChild(banner);

    // Get all showtime options with travel times
    const showtimeOptions = [];
    const now = new Date();
    const nowMins = now.getHours() * 60 + now.getMinutes();

    // Apply time filter first
    let list = cinemasData;
    if (currentTimeFilter === 'next3') {
        list = applyNext3Filter(list);
    }

    // Build showtime options
    list.forEach((movieCinemas, movieIdx) => {
        const movieArray = moviesData[movieIdx];
        if (!movieArray || !movieArray[0]) return;
        const movie = movieArray[0]; // Extract the movie object from the array

        movieCinemas.forEach(cinema => {
            // Only include cinemas with travel times (within 5km)
            if (!travelTimesCache[cinema.cinema]) return;

            const travelTimes = travelTimesCache[cinema.cinema];

            // Get all showtimes for this cinema
            cinema.timetable.flat().forEach(showtime => {
                if (!showtime || showtime.trim() === '') return;

                // Parse showtime
                const timeMatch = showtime.match(/(\d{2}):(\d{2})/);
                if (!timeMatch) return;

                const showtimeMins = parseInt(timeMatch[1]) * 60 + parseInt(timeMatch[2]);

                // Calculate how much time user has to get there
                const minutesUntilShowtime = showtimeMins - nowMins;
                if (minutesUntilShowtime < 0) return; // Skip past showtimes

                // IMPORTANT: Add buffer time for practical considerations
                // - Parking (if driving): 5-10 min
                // - Getting tickets: 2-5 min
                // - Finding the screen: 2-3 min
                // - Getting settled: 1-2 min
                const ARRIVAL_BUFFER_NEEDED = 10; // Minimum 10 minutes needed after arrival

                // Determine feasibility based on travel times + buffer
                let feasibility = 'impossible';
                let travelMethod = null;
                let travelMinutes = null;
                let arrivalBuffer = 0; // How many minutes early they'll arrive after buffer

                // Check walking
                if (travelTimes.walking) {
                    const totalTimeNeeded = travelTimes.walking + ARRIVAL_BUFFER_NEEDED;
                    if (totalTimeNeeded <= minutesUntilShowtime) {
                        feasibility = 'possible';
                        travelMethod = 'walking';
                        travelMinutes = travelTimes.walking;
                        arrivalBuffer = minutesUntilShowtime - totalTimeNeeded;
                    }
                }

                // Check driving (faster than walking, but needs extra parking time)
                if (travelTimes.driving) {
                    const parkingBuffer = 5; // Extra time for parking
                    const totalTimeNeeded = travelTimes.driving + parkingBuffer + ARRIVAL_BUFFER_NEEDED;
                    if (totalTimeNeeded <= minutesUntilShowtime) {
                        if (!travelMethod || (travelTimes.driving + parkingBuffer) < travelMinutes) {
                            feasibility = 'comfortable';
                            travelMethod = 'driving';
                            travelMinutes = travelTimes.driving;
                            arrivalBuffer = minutesUntilShowtime - totalTimeNeeded;
                        }
                    }
                }

                // Check transit
                if (travelTimes.transit) {
                    const totalTimeNeeded = travelTimes.transit + ARRIVAL_BUFFER_NEEDED;
                    if (totalTimeNeeded <= minutesUntilShowtime) {
                        if (!travelMethod || travelTimes.transit < travelMinutes) {
                            feasibility = 'comfortable';
                            travelMethod = 'transit';
                            travelMinutes = travelTimes.transit;
                            arrivalBuffer = minutesUntilShowtime - totalTimeNeeded;
                        }
                    }
                }

                // Upgrade to "very comfortable" if they have 10+ minutes extra buffer (beyond the required 10)
                if (arrivalBuffer >= 10 && feasibility !== 'impossible') {
                    feasibility = 'very-comfortable';
                }

                // Skip impossible options
                if (feasibility === 'impossible') return;

                showtimeOptions.push({
                    movie: movie,
                    movieIdx: movieIdx,
                    cinema: cinema.cinema,
                    showtime: showtime,
                    showtimeMins: showtimeMins,
                    minutesUntilShowtime: minutesUntilShowtime,
                    travelMethod: travelMethod,
                    travelMinutes: travelMinutes,
                    arrivalBuffer: arrivalBuffer,
                    feasibility: feasibility,
                    travelTimes: travelTimes
                });
            });
        });
    });

    // Sort by: feasibility (best first), then by arrival buffer (most buffer first), then by travel time (fastest first)
    const feasibilityOrder = { 'very-comfortable': 0, 'comfortable': 1, 'possible': 2, 'impossible': 3 };
    showtimeOptions.sort((a, b) => {
        // First by feasibility
        if (feasibilityOrder[a.feasibility] !== feasibilityOrder[b.feasibility]) {
            return feasibilityOrder[a.feasibility] - feasibilityOrder[b.feasibility];
        }
        // Then by arrival buffer (more is better)
        if (a.arrivalBuffer !== b.arrivalBuffer) {
            return b.arrivalBuffer - a.arrivalBuffer;
        }
        // Then by travel time (less is better)
        return (a.travelMinutes || 999) - (b.travelMinutes || 999);
    });

    // Show message if no options
    if (showtimeOptions.length === 0) {
        const noResultsDiv = document.createElement('div');
        noResultsDiv.style.cssText = 'background: #fff3cd; border: 2px solid #ffc107; color: #856404; padding: 2em; border-radius: 10px; text-align: center; font-size: 1.1em; margin: 2em 0;';
        noResultsDiv.innerHTML = `<strong>😔 Δεν υπάρχουν προβολές μέσα στα επόμενα ${timeWindowMinutes} λεπτά σε ακτίνα ${MAX_DISTANCE_KM}km.</strong><br><br>Δοκίμασε να αυξήσεις το χρονικό παράθυρο ή απενεργοποίησε το φίλτρο.`;
        results.appendChild(noResultsDiv);
        return;
    }

    // Render options
    showtimeOptions.forEach(option => {
        const optionDiv = document.createElement('div');
        optionDiv.className = `showtime-option feasibility-${option.feasibility}`;

        // Feasibility badge
        let feasibilityBadge = '';
        let feasibilityIcon = '';
        let feasibilityText = '';

        if (option.feasibility === 'very-comfortable') {
            feasibilityIcon = '✅';
            feasibilityText = 'Άνετα!';
        } else if (option.feasibility === 'comfortable') {
            feasibilityIcon = '👍';
            feasibilityText = 'Προλαβαίνεις';
        } else if (option.feasibility === 'possible') {
            feasibilityIcon = '⚡';
            feasibilityText = 'Τρέξιμο!';
        } else {
            feasibilityIcon = '❌';
            feasibilityText = 'Αδύνατο';
        }

        feasibilityBadge = `<span class="feasibility-badge feasibility-${option.feasibility}">${feasibilityIcon} ${feasibilityText}</span>`;

        // Travel method icon
        const travelIcon = option.travelMethod === 'walking' ? '🚶' :
                          option.travelMethod === 'driving' ? '🚗' :
                          option.travelMethod === 'transit' ? '🚇' : '';

        // Build travel info
        const travelInfo = option.travelMinutes
            ? `${travelIcon} ${formatTravelTime(option.travelMinutes)}`
            : '-';

        // Arrival buffer text
        const bufferText = option.arrivalBuffer > 0
            ? `<span class="arrival-buffer">Φτάνεις ${option.arrivalBuffer}' νωρίτερα</span>`
            : '';

        // Add share button
        const shareBtn = `<button class="share-btn share-btn-small" onclick="event.stopPropagation(); shareMovie(${option.movieIdx})" title="Μοιράσου την ταινία">
            📤
        </button>`;

        // Add Google Maps link for cinema
        const mapsLink = `<a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(option.cinema + ', Αθήνα')}"
            target="_blank"
            rel="noopener noreferrer"
            class="cinema-maps-link"
            onclick="event.stopPropagation()"
            title="Δες στο Google Maps">
            📍
        </a>`;

        optionDiv.innerHTML = `
            <div class="showtime-option-header">
                ${feasibilityBadge}
                <span class="showtime-time">${option.showtime}</span>
                ${shareBtn}
            </div>
            <div class="showtime-option-body">
                <h3 class="showtime-movie-title">${option.movie.greek_title || option.movie.original_title}</h3>
                <div class="showtime-cinema">
                    ${mapsLink} ${option.cinema}
                </div>
                <div class="showtime-travel-info">
                    <span class="travel-method">${travelInfo}</span>
                    ${bufferText}
                </div>
            </div>
        `;

        results.appendChild(optionDiv);
    });
}


// ✅ Main rendering logic
// Replace the existing renderResults function with this version that respects time filters
function renderResults(filteredList, forceEmpty = false) {
    const results = document.getElementById('results');
    results.innerHTML = '';

    // If "Can I Make It" mode is active, use special rendering
    if (canIMakeItActive && Object.keys(travelTimesCache).length > 0) {
        renderCanIMakeItResults();
        return;
    }

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

    // Create array of movies with their cinema counts for sorting
    const moviesWithCounts = list.map((movieCinemas, idx) => {
        if (selectedMovies.length && !selectedMovies.includes(String(idx))) return null;

        const movie = moviesData[idx]?.[0];
        if (!movie) return null;

        const validCinemas = movieCinemas.filter(c => c.timetable && c.timetable.flat().length > 0);
        const cinemasToShow = selectedCinemas.length
            ? validCinemas.filter(c => selectedCinemas.includes(c.cinema))
            : validCinemas;

        const regionFiltered = selectedRegions.length
            ? cinemasToShow.filter(c => selectedRegions.includes(c.region))
            : cinemasToShow;

        if (regionFiltered.length === 0) return null;

        return {
            idx,
            movie,
            movieCinemas,
            regionFiltered: regionFiltered,
            cinemaCount: regionFiltered.length
        };
    }).filter(item => item !== null);

    // Sort by cinema count in filtered results (descending - most cinemas first)
    // Note: Popular badge uses pre-calculated total cinema count from backend, not filtered count
    moviesWithCounts.sort((a, b) => b.cinemaCount - a.cinemaCount);

    // Show "Can I Make It" active banner if filter is on
    if (canIMakeItActive && Object.keys(travelTimesCache).length > 0) {
        const banner = document.createElement('div');
        banner.style.cssText = 'background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1em; border-radius: 10px; margin-bottom: 1.5em; text-align: center; font-weight: 600;';
        banner.innerHTML = `
            🚶 Φίλτρο "Τι προλαβαίνω;" Ενεργό - Εμφανίζονται κινηματογράφοι σε ακτίνα ${MAX_DISTANCE_KM}km με χρόνους μετακίνησης
        `;
        results.appendChild(banner);
    }

    // Check if no results and show appropriate message
    if (moviesWithCounts.length === 0 && canIMakeItActive && currentTimeFilter === 'next3') {
        // Check if there are any cinemas nearby at all (without time filter)
        const nearbyCinemasCount = Object.keys(travelTimesCache).length;

        let message = '';
        if (nearbyCinemasCount === 0) {
            message = '😔 Δεν βρέθηκαν κινηματογράφοι σε ακτίνα 10km.';
        } else {
            // Check if there are any showtimes at all for nearby cinemas (checking original data)
            const selectedCinemaNames = new Set();
            document.querySelectorAll('#cinemaCheckboxes input[type="checkbox"]:checked').forEach(cb => {
                selectedCinemaNames.add(cb.value);
            });

            let hasAnyShowtimes = false;
            cinemasData.forEach(movieCinemas => {
                movieCinemas.forEach(cinema => {
                    if (selectedCinemaNames.has(cinema.cinema) && cinema.timetable && cinema.timetable.some(tt => tt.length > 0)) {
                        hasAnyShowtimes = true;
                    }
                });
            });

            const timeLabel = timeWindowMinutes === 30 ? '30 λεπτά' :
                              timeWindowMinutes === 60 ? '1 ώρα' : '3 ώρες';

            if (hasAnyShowtimes) {
                message = `😔 Δεν υπάρχουν προβολές μέσα στην επόμενη ${timeLabel}. Δοκίμασε να αυξήσεις το χρονικό παράθυρο.`;
            } else {
                message = `😔 Δεν υπάρχουν διαθέσιμες προβολές στους κινηματογράφους της περιοχής.`;
            }
        }

        const noResultsDiv = document.createElement('div');
        noResultsDiv.style.cssText = 'background: #fff3cd; border: 2px solid #ffc107; color: #856404; padding: 2em; border-radius: 10px; text-align: center; font-size: 1.1em; margin: 2em 0;';
        noResultsDiv.innerHTML = `<strong>${message}</strong>`;
        results.appendChild(noResultsDiv);
        return;
    }

    // Now render the sorted movies
    moviesWithCounts.forEach(({ idx, movie, movieCinemas, regionFiltered }, arrayIndex) => {
        // Use pre-calculated is_popular field from backend (static, not filtered)
        const isTopResult = movie.is_popular === true;

        // Check for rating disparity (controversial ratings)
        const ratings = [];
        if (movie.rating_stars) {
            const athRating = parseFloat(movie.rating_stars) * 2;
            if (athRating > 0) ratings.push(athRating);
        }
        if (movie.flix_rating) {
            const flixRating = parseFloat(movie.flix_rating);
            if (flixRating > 0) ratings.push(flixRating);
        }
        if (movie.lifo_rating) {
            const lifoRating = parseFloat(movie.lifo_rating);
            if (lifoRating > 0) ratings.push(lifoRating);
        }

        // Determine if there's a rating disparity (difference of 2.5+ points between highest and lowest)
        let hasDisparity = false;
        if (ratings.length >= 2) {
            const maxRating = Math.max(...ratings);
            const minRating = Math.min(...ratings);
            hasDisparity = (maxRating - minRating) >= 2.5;
        }

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
        let movieClasses = 'movie';
        if (isTopResult) movieClasses += ' popular-movie';
        if (hasDisparity) movieClasses += ' controversial-movie';
        movieDiv.className = movieClasses;

        // Build movie metadata string (minimal display)
        const metadataParts = [];
        if (movie.year) metadataParts.push(movie.year);
        if (movie.movie_country) metadataParts.push(movie.movie_country);
        if (movie.movie_type) metadataParts.push(movie.movie_type);
        if (movie.duration) metadataParts.push(movie.duration);

        const metadataLine = metadataParts.length > 0
            ? `<div class="movie-metadata">${metadataParts.join(' • ')}</div>`
            : '';

        // Build ratings display
        const ratingsHTML = [];

        // Athinorama rating (scale to 10)
        if (movie.rating_stars) {
            const athRating = parseFloat(movie.rating_stars) * 2;
            if (athRating > 0) {
                const isHigh = athRating >= 7.5;
                const displayRating = Number.isInteger(athRating) ? athRating : athRating.toFixed(1);
                ratingsHTML.push(`<a href="${movie.athinorama_link || '#'}" target="_blank" class="rating-badge athinorama-rating" title="Βαθμολογία Athinorama: ${displayRating}/10" data-rating-high="${isHigh}">
                    <span class="rating-source">📰 Athinorama</span>
                    <span class="rating-value">${displayRating}/10</span>
                </a>`);
            }
        }

        // Flix rating
        if (movie.flix_rating) {
            const flixRating = parseFloat(movie.flix_rating);
            if (flixRating > 0) {
                const isHigh = flixRating >= 7.5;
                const displayRating = Number.isInteger(flixRating) ? flixRating : flixRating.toFixed(1);
                ratingsHTML.push(`<a href="${movie.flix_url || '#'}" target="_blank" class="rating-badge flix-rating" title="Βαθμολογία Flix: ${displayRating}/10" data-rating-high="${isHigh}">
                    <span class="rating-source">🎬 Flix</span>
                    <span class="rating-value">${displayRating}/10</span>
                </a>`);
            }
        }

        // Lifo rating
        if (movie.lifo_rating) {
            const lifoRating = parseFloat(movie.lifo_rating);
            if (lifoRating > 0) {
                const isHigh = lifoRating >= 7.5;
                const displayRating = Number.isInteger(lifoRating) ? lifoRating : lifoRating.toFixed(1);
                ratingsHTML.push(`<a href="${movie.lifo_url || '#'}" target="_blank" class="rating-badge lifo-rating" title="Βαθμολογία Lifo: ${displayRating}/10" data-rating-high="${isHigh}">
                    <span class="rating-source">📝 Lifo</span>
                    <span class="rating-value">${displayRating}/10</span>
                </a>`);
            }
        }

        const ratingsLine = ratingsHTML.length > 0
            ? `<div class="movie-ratings">${ratingsHTML.join('')}</div>`
            : '';

        // Build travel time info for the next showtime cinema(s)
        let travelTimeHTML = '';
        if (canIMakeItActive && movieSummary.nextShowtime && movieSummary.cinemaNames) {
            // Get the first cinema with the next showtime
            const firstCinema = movieSummary.cinemaNames.split(',')[0].trim();
            const travelTimes = travelTimesCache[firstCinema];

            if (travelTimes) {
                const badges = [];
                if (travelTimes.walking) {
                    badges.push(`🚶 ${formatTravelTime(travelTimes.walking)}`);
                }
                if (travelTimes.driving) {
                    badges.push(`🚗 ${formatTravelTime(travelTimes.driving)}`);
                }
                if (travelTimes.transit) {
                    badges.push(`🚇 ${formatTravelTime(travelTimes.transit)}`);
                }
                if (badges.length > 0) {
                    travelTimeHTML = `<span class="travel-time-inline">${badges.join(' ')}</span>`;
                }
            }
        }

        // Build cinema count with expand indicator
        const cinemaCountHTML = regionFiltered.length === 1
            ? `<span class="cinema-count-single">${regionFiltered.length} κινηματογράφος</span>`
            : `<span class="cinema-count-multiple">
                 ${regionFiltered.length} κινηματογράφοι
                 <span class="expand-hint">➕ Δες όλους</span>
               </span>`;

        // Create collapsible movie structure
        movieDiv.innerHTML = `
    <div class="movie-summary" onclick="toggleMovie('${uniqueMovieId}')">
      ${isTopResult ? '<div class="popular-badge">🔥 Δημοφιλής</div>' : ''}
      ${hasDisparity ? '<div class="controversial-badge">⚡ Οι Απόψεις Διίστανται</div>' : ''}
      <div class="movie-summary-header">
        <div class="movie-title-section">
          <h2 class="movie-summary-title">${displayTitle}</h2>
          ${metadataLine}
          ${ratingsLine}
        </div>
        <div class="external-links">
          ${externalLinks}
        </div>
      </div>
      <div class="movie-summary-info">
        <div class="movie-stats">
          ${cinemaCountHTML}
          ${movieSummary.nextShowtime ? `
            <span class="next-showing-prominent">
              <strong>Επόμενη:</strong> ${movieSummary.nextShowtime} - ${movieSummary.cinemaNames}
              ${travelTimeHTML}
            </span>
          ` : ''}
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
                // Generate URL for this showtime
                const showtimeUrl = generateShowtimeUrl(movie, cinema, t);

                // Escape quotes for onclick attributes
                const escapedTitle = movie.greek_title.replace(/'/g, "\\'");
                const escapedShowtime = t.replace(/'/g, "\\'");

                // If we have a valid URL, make it a clickable link with share popup
                if (showtimeUrl) {
                    return `<a href="${showtimeUrl}" 
                        onclick="showShowtimeSharePopup(event, '${showtimeUrl}', '${escapedShowtime}', '${escapedTitle}'); return false;"
                        style="display:inline-block;margin:3px 6px;padding:4px 8px;background:#f5f5f5;border-radius:8px;text-decoration:none;color:inherit;transition:background 0.2s;cursor:pointer;" 
                        onmouseover="this.style.background='#e0e0e0'" 
                        onmouseout="this.style.background='#f5f5f5'" 
                        title="Κλικ για επιλογές">${t}</a>`;
                } else {
                    // Fallback to non-link version
                    return `<span style="display:inline-block;margin:3px 6px;padding:4px 8px;background:#f5f5f5;border-radius:8px;">${t}</span>`;
                }
            }).join(' ');


            const c = document.createElement('div');
            c.className = 'cinema';

            // Check if we have travel times for this cinema
            let travelTimesHTML = '';
            if (canIMakeItActive && travelTimesCache[cinema.cinema]) {
                const times = travelTimesCache[cinema.cinema];
                const badges = [];

                if (times.walking) {
                    badges.push(`<span class="travel-badge walking" title="Με τα πόδια">🚶 ${formatTravelTime(times.walking)}</span>`);
                }
                if (times.driving) {
                    badges.push(`<span class="travel-badge driving" title="Με αυτοκίνητο">🚗 ${formatTravelTime(times.driving)}</span>`);
                }
                if (times.transit) {
                    badges.push(`<span class="travel-badge transit" title="Με ΜΜΜ">🚇 ${formatTravelTime(times.transit)}</span>`);
                }

                if (badges.length > 0) {
                    travelTimesHTML = `<div class="travel-times">${badges.join('')}</div>`;
                }
            }

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
  ${travelTimesHTML}
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
    const targetMins = nowMins + timeWindowMinutes; // Use dynamic time window

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

                    // If it's today, check if it's within the selected time window
                    const timeMatch = t.match(/(\d{2}):(\d{2})/);
                    if (!timeMatch) return false;

                    const mins = parseInt(timeMatch[1]) * 60 + parseInt(timeMatch[2]);
                    return mins >= nowMins && mins <= targetMins;
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
    // Get selected time window from dropdown
    const select = document.getElementById('timeWindowSelect');
    timeWindowMinutes = parseInt(select?.value) || 180;

    currentTimeFilter = 'next3';
    renderResults();
    updateFilterChips();
    highlightButton('next3Btn');
    setTimeout(() => showResultsCount('next3ResultsInfo'), 100);

    // Update meta based on time window
    const timeLabel = timeWindowMinutes === 30 ? '30 Λεπτά' :
                      timeWindowMinutes === 60 ? '1 Ώρα' : '3 Ώρες';
    updateMeta(`Ταινίες στα Επόμενα ${timeLabel} στα Σινεμά της Αθήνας ⏰`,
               `Ανακάλυψε ποιες ταινίες παίζονται μέσα στα επόμενα ${timeLabel} στα σινεμά της Αθήνας.`);
}

// New function name for clarity
function filterNextHours() {
    filterNext3();
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

// Add this function after the shareMovie function

// Show share popup for specific showtime
function showShowtimeSharePopup(event, url, showtimeText, movieTitle) {
    event.preventDefault();
    event.stopPropagation();

    // Remove any existing popup
    const existingPopup = document.querySelector('.showtime-share-popup');
    if (existingPopup) existingPopup.remove();

    // Create popup
    const popup = document.createElement('div');
    popup.className = 'showtime-share-popup';
    popup.innerHTML = `
        <div class="showtime-share-content">
            <button class="close-popup" onclick="this.closest('.showtime-share-popup').remove()">✕</button>
            <h4>📅 ${showtimeText}</h4>
            <p style="font-size: 0.9em; color: #666; margin: 8px 0;">${movieTitle}</p>
            <div class="share-actions">
                <button onclick="shareShowtime('${url}', '${movieTitle}', '${showtimeText}')" class="share-action-btn">
                    📤 Μοιράσου
                </button>
                <button onclick="window.open('${url}', '_blank'); this.closest('.showtime-share-popup').remove();" class="share-action-btn primary">
                    🎬 Δες Λεπτομέρειες
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(popup);

    // Close on outside click
    setTimeout(() => {
        popup.addEventListener('click', (e) => {
            if (e.target === popup) popup.remove();
        });
    }, 100);
}

// Share specific showtime
async function shareShowtime(url, movieTitle, showtimeText) {
    const fullUrl = url.startsWith('http') ? url : `${window.location.origin}/${url}`;
    const shareTitle = `${movieTitle} - ${showtimeText}`;
    const shareText = `Δες την ταινία "${movieTitle}" στις ${showtimeText}`;

    if (navigator.share) {
        try {
            await navigator.share({
                title: shareTitle,
                text: shareText,
                url: fullUrl
            });
            document.querySelector('.showtime-share-popup')?.remove();
        } catch (err) {
            if (err.name !== 'AbortError') {
                fallbackCopyToClipboard(fullUrl);
            }
        }
    } else {
        fallbackCopyToClipboard(fullUrl);
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

// ========== NEW UI FUNCTIONS ==========

// Handle time filter tabs
function filterByTime(filter) {
    // Update active tab
    document.querySelectorAll('.time-tab').forEach(tab => {
        tab.classList.remove('active');
        if (tab.dataset.filter === filter) {
            tab.classList.add('active');
        }
    });

    // Apply filter
    if (filter === 'all') {
        showAll();
    } else if (filter === 'today') {
        filterToday();
    } else {
        // Time window filters (30, 60, 180)
        timeWindowMinutes = parseInt(filter);
        currentTimeFilter = 'next3';
        renderResults();
        updateFilterChips();
        updateMeta(`Ταινίες στα Επόμενα ${filter === '30' ? '30 Λεπτά' : filter === '60' ? '1 Ώρα' : '3 Ώρες'} ⏰`,
                   `Ανακάλυψε ποιες ταινίες παίζονται σύντομα στα σινεμά της Αθήνας.`);
    }
}

// Handle location option selection
function selectLocation(option) {
    // Update active button
    document.querySelectorAll('.location-option').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.location === option) {
            btn.classList.add('active');
        }
    });

    // Show/hide controls
    const nearbyControls = document.getElementById('nearbyControls');
    const addressControls = document.getElementById('addressControls');

    if (option === 'nearby') {
        nearbyControls.style.display = 'block';
        addressControls.style.display = 'none';
    } else if (option === 'address') {
        nearbyControls.style.display = 'none';
        addressControls.style.display = 'block';
    }
}

// Clear location filter and return to showing all Athens
function clearLocationFilter() {
    // Remove active state from all location buttons
    document.querySelectorAll('.location-option').forEach(btn => {
        btn.classList.remove('active');
    });

    // Hide both control panels
    const nearbyControls = document.getElementById('nearbyControls');
    const addressControls = document.getElementById('addressControls');
    nearbyControls.style.display = 'none';
    addressControls.style.display = 'none';

    // Clear cinema selections (location-based filters)
    const cinemaInputs = document.querySelectorAll('#cinemaCheckboxes input[type="checkbox"]');
    cinemaInputs.forEach(cb => cb.checked = false);

    // Clear summary and address input
    document.getElementById('nearbySummary').textContent = '';
    document.getElementById('addressInput').value = '';

    // Re-render to show all Athens
    renderResults();
    updateFilterChips();
}


// ============ FAB BUTTON HINT (First Visit Discovery) ============
function initializeFABHint() {
    const fabButton = document.getElementById('canIMakeItFAB');
    if (!fabButton) return;

    // Check if user has seen the FAB before
    const hasSeenFAB = localStorage.getItem('hasSeenFABHint');

    if (!hasSeenFAB) {
        // Add first-visit class for tooltip animation
        fabButton.classList.add('first-visit');

        // Remove class after animation completes (about 10 seconds)
        setTimeout(() => {
            fabButton.classList.remove('first-visit');
            localStorage.setItem('hasSeenFABHint', 'true');
        }, 10000);
    }
}


loadData();