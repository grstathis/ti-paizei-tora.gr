/**
 * MAP VIEW - Mobile-First Cinema Discovery
 * Shows all cinemas with today's showtimes on a map
 *
 * User Flow:
 * 1. User taps "Map View" button
 * 2. Map loads centered on Athens (no location required)
 * 3. All cinemas with showtimes today shown as pins
 * 4. Tap pin to see cinema details & next showtime
 * 5. Bottom sheet shows full cinema info
 */

// ============ MAP STATE ============
let map = null;
let markers = [];
let userMarker = null;
let selectedCinema = null;
let currentInfoWindow = null; // Track currently open info window
let mapView = {
  active: false,
  userLocation: null
};

// Athens center coordinates
const ATHENS_CENTER = { lat: 37.9838, lng: 23.7275 };

// ============ MAP VIEW TOGGLE ============

/**
 * Initialize and show map view
 * NO location permission required - shows all cinemas
 */
async function showMapView() {
  // Check if already active
  if (mapView.active) {
    hideMapView();
    return;
  }

  // Show loading overlay
  showMapLoading();

  try {
    console.log('🗺️ Step 1: Loading Google Maps API...');
    await loadGoogleMapsAPI();
    console.log('✅ Google Maps API loaded');

    console.log('🗺️ Step 2: Initializing map...');
    await initializeMap();
    console.log('✅ Map initialized');

    console.log('🗺️ Step 3: Finding cinemas with today\'s showtimes...');
    const cinemasWithShowtimes = await findCinemasWithTodayShowtimes();
    console.log(`✅ Found ${cinemasWithShowtimes.length} cinemas with showtimes`);

    console.log('🗺️ Step 4: Adding markers to map...');
    if (cinemasWithShowtimes.length > 0) {
      addCinemaMarkers(cinemasWithShowtimes);
      console.log('✅ Markers added');
    }

    console.log('🗺️ Step 5: Activating map view...');
    activateMapView(cinemasWithShowtimes);
    console.log('✅ Map view activated');

    // Show appropriate message
    try {
      if (cinemasWithShowtimes.length === 0) {
        showNoShowtimesMessage();
      } else if (cinemasWithShowtimes.length > 0 && cinemasWithShowtimes[0].timeframe === 'tomorrow') {
        showTomorrowShowtimesMessage(cinemasWithShowtimes.length);
      } else {
        showWelcomeMessage();
      }
    } catch (e) {
      console.warn('Message failed:', e);
    }

    // Track activation (non-critical)
    try {
      trackMapViewActivation(cinemasWithShowtimes.length);
    } catch (e) {
      console.warn('Tracking failed:', e);
    }

  } catch (error) {
    console.error('❌ Map view initialization error:', error);
    console.error('Error details:', error.message);
    console.error('Error stack:', error.stack);
    showMapError('❌ Σφάλμα κατά τη φόρτωση του χάρτη. Δοκίμασε ξανά.');
  }
}

/**
 * Request location permission with user-friendly prompt
 * DEPRECATED - kept for future "Can I Make It" feature
 */
async function requestLocationPermission() {
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      () => resolve(true),
      (error) => {
        if (error.code === error.PERMISSION_DENIED) {
          resolve(false);
        } else {
          resolve(false);
        }
      },
      { timeout: 5000 }
    );
  });
}

/**
 * Get user location with high accuracy
 * DEPRECATED - kept for future "Can I Make It" feature
 */
function getUserLocation() {
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      resolve,
      reject,
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0
      }
    );
  });
}

// ============ MAP INITIALIZATION ============

/**
 * Initialize Google Maps with mobile-optimized settings
 * Centers on Athens, no user location required
 */
async function initializeMap() {
  const mapContainer = document.getElementById('mapContainer');
  const mapElement = document.getElementById('map');

  if (!mapElement) {
    throw new Error('Map element not found');
  }

  // Optimized map configuration for mobile
  const mapOptions = {
    center: ATHENS_CENTER, // Always center on Athens
    zoom: 12, // Zoom out to show all Athens

    // Mobile optimizations
    gestureHandling: 'greedy', // Better touch handling
    disableDefaultUI: true, // Remove clutter
    zoomControl: true,
    mapTypeControl: false,
    streetViewControl: false,
    fullscreenControl: false,

    // Performance
    renderingType: google.maps.RenderingType.VECTOR, // WebGL for speed

    // Styling
    styles: getMinimalMapStyle(),

    // Bounds - Athens area
    restriction: {
      latLngBounds: {
        north: 38.1,
        south: 37.8,
        east: 23.9,
        west: 23.5
      },
      strictBounds: false
    }
  };

  map = new google.maps.Map(mapElement, mapOptions);
}

/**
 * Minimal map style for better performance and clarity
 */
function getMinimalMapStyle() {
  return [
    {
      "featureType": "poi",
      "elementType": "labels",
      "stylers": [{ "visibility": "off" }] // Hide POI clutter
    },
    {
      "featureType": "transit",
      "elementType": "labels",
      "stylers": [{ "visibility": "simplified" }]
    }
  ];
}

// ============ MARKER MANAGEMENT ============

/**
 * Add user location marker
 */
function addUserMarker(location) {
  if (userMarker) {
    userMarker.setMap(null);
  }

  userMarker = new google.maps.Marker({
    position: location,
    map: map,
    icon: {
      path: google.maps.SymbolPath.CIRCLE,
      scale: 10,
      fillColor: '#4285F4',
      fillOpacity: 1,
      strokeColor: '#ffffff',
      strokeWeight: 3
    },
    title: 'Η θέση σου',
    zIndex: 1000
  });

  // Add accuracy circle
  new google.maps.Circle({
    strokeColor: '#4285F4',
    strokeOpacity: 0.3,
    strokeWeight: 1,
    fillColor: '#4285F4',
    fillOpacity: 0.1,
    map: map,
    center: location,
    radius: 100 // meters
  });
}

/**
 * Add cinema markers with showtime data
 * @param {boolean} skipFitBounds - If true, don't auto-fit bounds (used in location mode)
 */
function addCinemaMarkers(cinemas, skipFitBounds = false) {
  // Clear existing markers
  markers.forEach(marker => marker.setMap(null));
  markers = [];

  cinemas.forEach(cinema => {
    const marker = createCinemaMarker(cinema);
    markers.push(marker);
  });

  // Fit bounds to show all markers (unless in location mode)
  if (cinemas.length > 0 && !skipFitBounds) {
    const bounds = new google.maps.LatLngBounds();
    cinemas.forEach(c => bounds.extend({ lat: c.lat, lng: c.lng }));
    map.fitBounds(bounds, { padding: 60 });
  }
}

/**
 * Create marker for cinema with custom icon showing next showtime
 */
function createCinemaMarker(cinema) {
  const now = new Date();
  const nextShowtime = cinema.nextShowtime;
  const timeframe = cinema.timeframe || 'today';

  // Marker color based on next showtime urgency
  let markerColor = '#4285F4'; // Default blue

  if (nextShowtime) {
    if (timeframe === 'tomorrow') {
      markerColor = '#808080'; // Grey = tomorrow's showtimes
    } else {
      const minutesUntil = (nextShowtime - now) / 1000 / 60;

      if (minutesUntil <= 30) {
        markerColor = '#dc3545'; // Red = starting very soon
      } else if (minutesUntil <= 60) {
        markerColor = '#ff9800'; // Orange = starting soon
      } else {
        markerColor = '#28a745'; // Green = plenty of time
      }
    }
  }

  const marker = new google.maps.Marker({
    position: { lat: cinema.lat, lng: cinema.lng },
    map: map,
    title: cinema.cinema,
    icon: {
      path: google.maps.SymbolPath.CIRCLE,
      scale: 10,
      fillColor: markerColor,
      fillOpacity: 1,
      strokeColor: '#ffffff',
      strokeWeight: 2
    },
    animation: google.maps.Animation.DROP,
    cinema: cinema // Store cinema data
  });

  // Click handler
  marker.addListener('click', () => {
    onMarkerClick(marker, cinema);
  });

  return marker;
}

/**
 * Handle marker click - show info window popup
 */
function onMarkerClick(marker, cinema) {
  // Close previous info window
  if (currentInfoWindow) {
    currentInfoWindow.close();
  }

  // Highlight selected marker
  markers.forEach(m => {
    const isSelected = m === marker;
    m.setIcon({
      path: google.maps.SymbolPath.CIRCLE,
      scale: isSelected ? 14 : 10,
      fillColor: m.icon.fillColor,
      fillOpacity: 1,
      strokeColor: isSelected ? '#FFD700' : '#ffffff',
      strokeWeight: isSelected ? 3 : 2
    });
  });

  selectedCinema = cinema;

  // Build info window content
  const infoContent = buildInfoWindowContent(cinema);

  // Create and show info window
  currentInfoWindow = new google.maps.InfoWindow({
    content: infoContent,
    maxWidth: 320
  });

  currentInfoWindow.open(map, marker);

  // Pan to marker with offset for info window
  map.panTo(marker.getPosition());
}

// ============ CINEMA DATA FUNCTIONS ============

/**
 * Build info window content for cinema marker
 */
function buildInfoWindowContent(cinema) {
  const now = new Date();
  const nextShowtime = cinema.nextShowtime;
  const nextMovieName = cinema.nextMovieName || '';
  const timeframe = cinema.timeframe || 'today';

  let nextShowtimeText = 'Δεν υπάρχουν προβολές';
  let urgencyClass = 'info';

  if (nextShowtime && nextMovieName) {
    const timeStr = nextShowtime.toLocaleTimeString('el-GR', { hour: '2-digit', minute: '2-digit' });

    if (timeframe === 'tomorrow') {
      // Tomorrow's showtime
      nextShowtimeText = `🌅 Αύριο ${timeStr}`;
      urgencyClass = 'info';
    } else {
      // Today's showtime
      const minutesUntil = Math.floor((nextShowtime - now) / 1000 / 60);

      if (minutesUntil <= 30) {
        nextShowtimeText = `${timeStr} (σε ${minutesUntil}')`;
        urgencyClass = 'danger';
      } else if (minutesUntil <= 60) {
        nextShowtimeText = `${timeStr} (σε ${minutesUntil}')`;
        urgencyClass = 'warning';
      } else {
        const hours = Math.floor(minutesUntil / 60);
        const mins = minutesUntil % 60;
        nextShowtimeText = mins > 0 ? `${timeStr} (σε ${hours}ω ${mins}')` : `${timeStr} (σε ${hours}ω)`;
        urgencyClass = 'success';
      }
    }
  }

  // Build info window HTML
  const urgencyColors = {
    'success': '#d4edda',
    'warning': '#fff3cd',
    'danger': '#f8d7da',
    'info': '#d1ecf1'
  };

  const urgencyBorderColors = {
    'success': '#28a745',
    'warning': '#ff9800',
    'danger': '#dc3545',
    'info': '#17a2b8'
  };

  return `
    <div style="padding: 10px; max-width: 280px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
      <h3 style="margin: 0 0 6px 0; font-size: 1em; font-weight: 700; color: #212529;">
        ${cinema.cinema}
      </h3>
      ${cinema.region ? `<p style="margin: 0 0 8px 0; font-size: 0.75em; color: #6c757d;">📍 ${cinema.region}</p>` : ''}

      <div style="padding: 8px; background: ${urgencyColors[urgencyClass]}; border-radius: 6px; margin-bottom: 8px; border-left: 3px solid ${urgencyBorderColors[urgencyClass]};">
        <div style="font-size: 0.7em; font-weight: 600; color: #495057; margin-bottom: 3px;">Επόμενη προβολή:</div>
        <div style="font-size: 0.95em; font-weight: 700; color: #212529; margin-bottom: 2px;">${nextShowtimeText}</div>
        ${nextMovieName ? `<div style="font-size: 0.75em; color: #495057;">🎬 ${nextMovieName}</div>` : ''}
      </div>

      <div style="display: grid; gap: 8px; margin-top: 8px;">
        <button
          onclick="viewCinemaInList('${cinema.cinema.replace(/'/g, "\\'")}')"
          style="width: 100%; background: white; color: #667eea; border: 2px solid #667eea; padding: 10px; border-radius: 6px; font-size: 0.85em; font-weight: 700; cursor: pointer; min-height: 44px;">
          📋 Όλες οι ταινίες & πληροφορίες
        </button>
        <button
          onclick="openDirections('${cinema.cinema.replace(/'/g, "\\'")}', ${cinema.lat}, ${cinema.lng})"
          style="width: 100%; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 10px; border-radius: 6px; font-size: 0.85em; font-weight: 700; cursor: pointer; box-shadow: 0 2px 6px rgba(102, 126, 234, 0.3); min-height: 44px;">
          🧭 Οδηγίες
        </button>
      </div>
    </div>
  `;
}

/**
 * Find all cinemas that have showtimes today OR tomorrow (hybrid approach)
 * - If any cinema has upcoming shows today → show only those
 * - If no upcoming shows today → show cinemas with tomorrow's first show
 */
async function findCinemasWithTodayShowtimes() {
  const now = new Date();

  // Try to find cinemas with upcoming shows TODAY
  const todayResults = findCinemasWithUpcomingShowtimes(now, 'today');

  // If we have shows today, return them (avoid clutter)
  if (todayResults.length > 0) {
    return todayResults;
  }

  // No shows today - fallback to TOMORROW
  console.log('🌙 No upcoming shows today - showing tomorrow\'s showtimes');
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  tomorrow.setHours(0, 0, 0, 0); // Start of tomorrow

  return findCinemasWithUpcomingShowtimes(tomorrow, 'tomorrow');
}

/**
 * Find cinemas with upcoming showtimes for a specific day
 * @param {Date} referenceDate - The date to check showtimes for
 * @param {string} timeframe - 'today' or 'tomorrow'
 */
function findCinemasWithUpcomingShowtimes(referenceDate, timeframe) {
  const now = new Date();
  const results = [];

  // Get unique cinemas from data
  const cinemaMap = uniqueCinemasFromData();

  cinemaMap.forEach((cinema) => {
    // Check if has valid coordinates
    if (!Number.isFinite(cinema.lat) || !Number.isFinite(cinema.lng)) {
      return;
    }

    let firstShowtime = null;
    let firstMovieName = null;

    // Find first upcoming showtime at this cinema
    moviesData.forEach((movieData, movieIndex) => {
      const movie = movieData[0];
      const cinemas = cinemasData[movieIndex];

      cinemas.forEach(c => {
        if (c.cinema === cinema.cinema) {
          if (!c.timetable || !Array.isArray(c.timetable)) {
            return;
          }

          const allShowtimes = c.timetable.flat();

          // Find showtimes for the reference date
          allShowtimes.forEach(showtime => {
            const showtimeDate = parseShowtimeDate(showtime);
            if (!showtimeDate) return;

            // For today: check if showtime is upcoming
            // For tomorrow: check if showtime is on tomorrow's date
            const isValid = timeframe === 'today'
              ? showtimeDate > now && showtimeDate.toDateString() === referenceDate.toDateString()
              : showtimeDate.toDateString() === referenceDate.toDateString();

            if (isValid) {
              // Keep only the first showtime
              if (!firstShowtime || showtimeDate < firstShowtime) {
                firstShowtime = showtimeDate;
                firstMovieName = movie.greek_title || movie.original_title;
              }
            }
          });
        }
      });
    });

    // Add cinema if it has at least one showtime
    if (firstShowtime) {
      results.push({
        ...cinema,
        nextShowtime: firstShowtime,
        nextMovieName: firstMovieName,
        timeframe: timeframe // 'today' or 'tomorrow'
      });
    }
  });

  // Sort by next showtime (soonest first)
  results.sort((a, b) => {
    if (!a.nextShowtime) return 1;
    if (!b.nextShowtime) return -1;
    return a.nextShowtime - b.nextShowtime;
  });

  return results;
}

/**
 * Parse Greek showtime string to Date object
 */
function parseShowtimeDate(showtimeStr) {
  const greekMonths = {
    'Ιαν': 0, 'Φεβ': 1, 'Μαρ': 2, 'Απρ': 3,
    'Μαΐ': 4, 'Ιουν': 5, 'Ιουλ': 6, 'Αυγ': 7,
    'Σεπ': 8, 'Οκτ': 9, 'Νοε': 10, 'Δεκ': 11
  };

  const match = showtimeStr.match(/(\d{1,2})\s+([Α-Ωα-ωάέίόήύώΆΈΉΊΌΎΏ\.]+)\s+(\d{2}):(\d{2})/);
  if (!match) return null;

  const day = parseInt(match[1]);
  const monthStr = match[2].replace('.', '').trim();
  const hour = parseInt(match[3]);
  const minute = parseInt(match[4]);

  const month = greekMonths[monthStr];
  if (month === undefined) return null;

  const year = new Date().getFullYear();
  return new Date(year, month, day, hour, minute);
}

// ============ UI COMPONENTS ============

/**
 * Show map loading overlay
 */
function showMapLoading() {
  const overlay = document.getElementById('mapLoadingOverlay');
  if (overlay) {
    overlay.style.display = 'flex';
  }
}

/**
 * Hide map loading overlay
 */
function hideMapLoading() {
  const overlay = document.getElementById('mapLoadingOverlay');
  if (overlay) {
    overlay.style.display = 'none';
  }
}

/**
 * Show location explanation modal
 */
function showLocationExplanationModal() {
  const modal = document.getElementById('mapLocationModal');
  if (modal) {
    modal.style.display = 'flex';
  }
}

/**
 * Hide location modal
 */
function hideLocationModal() {
  const modal = document.getElementById('mapLocationModal');
  if (modal) {
    modal.style.display = 'none';
  }
}

/**
 * Show welcome message when map loads
 */
function showWelcomeMessage() {
  const welcomeMsg = document.createElement('div');
  welcomeMsg.className = 'map-welcome-toast';
  welcomeMsg.innerHTML = `
    <div class="welcome-icon">💡</div>
    <div class="welcome-text">
      <strong>Χάρτης Κινηματογράφων</strong><br>
      Για περισσότερες πληροφορίες και φιλτράρισμα, πάτα <strong>"📍 Η θέση μου"</strong>
    </div>
    <button class="welcome-close" onclick="this.parentElement.remove()">✕</button>
  `;

  document.getElementById('mapContainer').appendChild(welcomeMsg);

  // Auto-hide after 5 seconds
  setTimeout(() => {
    welcomeMsg.classList.add('fade-out');
    setTimeout(() => welcomeMsg.remove(), 300);
  }, 5000);
}

/**
 * Show tomorrow's showtimes message
 */
function showTomorrowShowtimesMessage(cinemaCount) {
  const tomorrowMsg = document.createElement('div');
  tomorrowMsg.className = 'map-welcome-toast';
  tomorrowMsg.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
  tomorrowMsg.innerHTML = `
    <div class="welcome-icon">🌅</div>
    <div class="welcome-text">
      <strong>Όλες οι προβολές τελείωσαν για σήμερα</strong><br>
      Βλέπεις ${cinemaCount} κινηματογράφ${cinemaCount === 1 ? 'ο' : 'ους'} με αυριανές προβολές
    </div>
    <button class="welcome-close" onclick="this.parentElement.remove()">✕</button>
  `;

  document.getElementById('mapContainer').appendChild(tomorrowMsg);

  // Auto-hide after 7 seconds
  setTimeout(() => {
    tomorrowMsg.classList.add('fade-out');
    setTimeout(() => tomorrowMsg.remove(), 300);
  }, 7000);
}

/**
 * Show no showtimes message when map loads but no cinemas have showtimes today
 */
function showNoShowtimesMessage() {
  const noShowtimesMsg = document.createElement('div');
  noShowtimesMsg.className = 'map-welcome-toast';
  noShowtimesMsg.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
  noShowtimesMsg.innerHTML = `
    <div class="welcome-icon">📍</div>
    <div class="welcome-text">
      <strong>Δεν υπάρχουν προβολές σήμερα</strong><br>
      Μπορείς να δεις όλους τους κινηματογράφους της Αθήνας στον χάρτη
    </div>
    <button class="welcome-close" onclick="this.parentElement.remove()">✕</button>
  `;

  document.getElementById('mapContainer').appendChild(noShowtimesMsg);

  // Auto-hide after 7 seconds (longer since it's important info)
  setTimeout(() => {
    noShowtimesMsg.classList.add('fade-out');
    setTimeout(() => noShowtimesMsg.remove(), 300);
  }, 7000);
}

/**
 * Show map error message
 */
function showMapError(message) {
  hideMapLoading();
  alert(message);
}

/**
 * Activate map view - show UI
 */
function activateMapView(cinemas) {
  mapView.active = true;
  hideMapLoading();

  // Show map container
  const mapContainer = document.getElementById('mapContainer');
  const regularView = document.getElementById('regularView');
  const viewToggleBtn = document.getElementById('viewToggle');
  const viewToggleText = document.getElementById('viewToggleText');

  if (mapContainer) mapContainer.style.display = 'block';
  if (regularView) regularView.style.display = 'none';
  if (viewToggleText) {
    viewToggleText.textContent = '📋 Λίστα';
  }
  if (viewToggleBtn) {
    viewToggleBtn.classList.add('active');
  }

  // Show summary
  showMapSummary(cinemas);
}

/**
 * Hide map view - return to list
 */
function hideMapView() {
  mapView.active = false;

  const mapContainer = document.getElementById('mapContainer');
  const regularView = document.getElementById('regularView');
  const viewToggleBtn = document.getElementById('viewToggle');
  const viewToggleText = document.getElementById('viewToggleText');

  if (mapContainer) mapContainer.style.display = 'none';
  if (regularView) regularView.style.display = 'block';
  if (viewToggleText) {
    viewToggleText.textContent = '🗺️ Χάρτης';
  }
  if (viewToggleBtn) {
    viewToggleBtn.classList.remove('active');
  }

  // Close bottom sheet
  closeBottomSheet();
}

/**
 * Toggle between map and list view (for new centered button)
 */
function toggleView() {
  if (mapView.active) {
    hideMapView();
  } else {
    showMapView();
  }
}

/**
 * Show map summary bar
 */
function showMapSummary(cinemas) {
  const summary = document.getElementById('mapSummary');
  if (!summary) return;

  // Handle case when there are no cinemas with showtimes
  if (cinemas.length === 0) {
    summary.innerHTML = `
      <div class="map-summary-content">
        <div class="map-stat">
          <span class="map-stat-value">0</span>
          <span class="map-stat-label">προβολές σήμερα</span>
        </div>
      </div>
      <div class="map-controls">
        <button id="useLocationBtn" class="use-location-btn" onclick="enableLocationMode()" title="Φίλτραρε με βάση την τοποθεσία σου">
          📍 Η θέση μου
        </button>
      </div>
    `;
    return;
  }

  const totalMovies = cinemas.reduce((sum, c) => sum + c.moviesCount, 0);
  const totalShowtimes = cinemas.reduce((sum, c) => sum + c.showtimesCount, 0);

  // Count cinemas with next showtime in next hour
  const now = new Date();
  const nextHourCount = cinemas.filter(c => {
    if (!c.nextShowtime) return false;
    const minutesUntil = (c.nextShowtime - now) / 1000 / 60;
    return minutesUntil > 0 && minutesUntil <= 60;
  }).length;

  summary.innerHTML = `
    <div class="map-summary-content">
      <div class="map-stat">
        <span class="map-stat-value">${cinemas.length}</span>
        <span class="map-stat-label">κινηματογράφοι</span>
      </div>
      <div class="map-stat success">
        <span class="map-stat-value">${nextHourCount}</span>
        <span class="map-stat-label">επόμενη ώρα ⚡</span>
      </div>
    </div>
    <div class="map-controls">
      <button id="useLocationBtn" class="use-location-btn" onclick="enableLocationMode()" title="Φίλτραρε με βάση την τοποθεσία σου">
        📍 Η θέση μου
      </button>
    </div>
  `;
}

// ============ LOCATION-BASED FILTERING ============

/**
 * Enable location mode - filters cinemas by proximity and upcoming showtimes
 */
async function enableLocationMode() {
  const btn = document.getElementById('useLocationBtn');
  if (!btn) return;

  // Check geolocation support
  if (!navigator.geolocation) {
    alert('⚠️ Ο browser σου δεν υποστηρίζει εντοπισμό τοποθεσίας.');
    return;
  }

  try {
    btn.textContent = '🔄 Εντοπισμός...';
    btn.disabled = true;

    // Get user location
    console.log('📍 Getting user location...');
    const position = await getUserLocation();

    console.log('📍 Raw position:', position);
    console.log('📍 Coords:', position.coords);
    console.log('📍 Latitude:', position.coords.latitude);
    console.log('📍 Longitude:', position.coords.longitude);

    mapView.userLocation = {
      lat: position.coords.latitude,
      lng: position.coords.longitude
    };
    console.log('✅ Location obtained:', mapView.userLocation);

    // Center map on user location with appropriate zoom for 5km radius
    // Zoom level 13 shows approximately 5-7km radius
    console.log('🗺️ Centering map on:', mapView.userLocation);
    map.setCenter(mapView.userLocation);
    console.log('🗺️ Setting zoom to 13');
    map.setZoom(13);

    // Add user marker to map
    addUserMarker(mapView.userLocation);

    // Show location mode controls
    showLocationModeControls();

    // Apply default filter: 5km radius, all showtimes today
    await applyLocationFilter(5);

  } catch (error) {
    console.error('❌ Location error:', error);
    btn.textContent = '📍 Η θέση μου';
    btn.disabled = false;

    if (error.code === error.PERMISSION_DENIED) {
      alert('📍 Χρειαζόμαστε άδεια για την τοποθεσία σου.\n\nΓια να φιλτράρεις με βάση την τοποθεσία σου, επέτρεψε την πρόσβαση στην τοποθεσία.');
    } else {
      alert('❌ Σφάλμα εντοπισμού τοποθεσίας. Δοκίμασε ξανά.');
    }
  }
}

/**
 * Apply location-based filter (radius only, shows all today's showtimes)
 */
async function applyLocationFilter(radiusKm) {
  if (!mapView.userLocation) return;

  showMapLoading();

  try {
    console.log(`🔍 Filtering: ${radiusKm}km radius, all showtimes today`);

    // Find nearby cinemas with today's showtimes
    const nearbyCinemas = await findNearbyCinemasWithShowtimes(
      mapView.userLocation.lat,
      mapView.userLocation.lng,
      radiusKm
    );

    console.log(`✅ Found ${nearbyCinemas.length} nearby cinemas`);

    if (nearbyCinemas.length === 0) {
      hideMapLoading();
      alert(`📍 Δεν βρέθηκαν κινηματογράφοι με προβολές σήμερα σε ακτίνα ${radiusKm}km.\n\nΔοκίμασε να αυξήσεις την ακτίνα.`);
      return;
    }

    // Update markers (skip fitBounds to keep user-centered view)
    addCinemaMarkers(nearbyCinemas, true);

    // Update summary
    showLocationModeSummary(nearbyCinemas, radiusKm);

    // Focus on nearest cinema and show its details
    if (nearbyCinemas.length > 0) {
      const nearestCinema = nearbyCinemas[0]; // Already sorted by distance

      // Pan map to nearest cinema (smooth animation)
      map.panTo({ lat: nearestCinema.lat, lng: nearestCinema.lng });

      // Zoom to a closer level to focus on the nearest cinema
      map.setZoom(14);
    }

    hideMapLoading();

  } catch (error) {
    console.error('❌ Filter error:', error);
    hideMapLoading();
    alert('❌ Σφάλμα φιλτραρίσματος. Δοκίμασε ξανά.');
  }
}

/**
 * Find nearby cinemas with today's showtimes (location mode)
 */
async function findNearbyCinemasWithShowtimes(userLat, userLng, radiusKm) {
  const now = new Date();
  const results = [];

  // Get unique cinemas from data
  const cinemaMap = uniqueCinemasFromData();

  cinemaMap.forEach((cinema) => {
    // Check if has valid coordinates
    if (!Number.isFinite(cinema.lat) || !Number.isFinite(cinema.lng)) {
      return;
    }

    // Calculate distance
    const distance = distanceKm(userLat, userLng, cinema.lat, cinema.lng);
    if (distance > radiusKm) {
      return; // Too far
    }

    // Find first upcoming showtime at this cinema (simplified)
    let firstShowtime = null;
    let firstMovieName = null;

    moviesData.forEach((movieData, movieIndex) => {
      const movie = movieData[0];
      const cinemas = cinemasData[movieIndex];

      cinemas.forEach(c => {
        if (c.cinema === cinema.cinema) {
          if (!c.timetable || !Array.isArray(c.timetable)) return;

          const allShowtimes = c.timetable.flat();

          // Find upcoming showtimes today
          allShowtimes.forEach(showtime => {
            const showtimeDate = parseShowtimeDate(showtime);
            if (!showtimeDate) return;

            // Check if today and upcoming
            if (showtimeDate.toDateString() === now.toDateString() && showtimeDate > now) {
              // Keep only the first showtime
              if (!firstShowtime || showtimeDate < firstShowtime) {
                firstShowtime = showtimeDate;
                firstMovieName = movie.greek_title || movie.original_title;
              }
            }
          });
        }
      });
    });

    // Add cinema if it has at least one upcoming showtime
    if (firstShowtime) {
      results.push({
        ...cinema,
        distance: distance.toFixed(1),
        distanceKm: distance,
        nextShowtime: firstShowtime,
        nextMovieName: firstMovieName,
        timeframe: 'today'
      });
    }
  });

  // Sort by distance
  results.sort((a, b) => a.distanceKm - b.distanceKm);

  return results;
}

/**
 * Show location mode controls (radius filter only)
 */
function showLocationModeControls() {
  const summary = document.getElementById('mapSummary');
  if (!summary) return;

  // Replace button with filter controls (radius only)
  const controls = summary.querySelector('.map-controls');
  if (controls) {
    controls.innerHTML = `
      <select id="radiusFilter" class="map-filter-select" onchange="updateLocationFilter()">
        <option value="1">1km</option>
        <option value="2">2km</option>
        <option value="3">3km</option>
        <option value="5" selected>5km</option>
        <option value="10">10km</option>
        <option value="15">15km</option>
      </select>
      <button class="reset-location-btn" onclick="resetToAllCinemas()" title="Εμφάνιση όλων">
        🌍 Όλα
      </button>
    `;
  }
}

/**
 * Update location filter when user changes dropdown
 */
async function updateLocationFilter() {
  const radiusSelect = document.getElementById('radiusFilter');

  if (!radiusSelect) return;

  const radius = parseInt(radiusSelect.value);

  await applyLocationFilter(radius);
}

/**
 * Reset to show all cinemas (disable location mode)
 */
async function resetToAllCinemas() {
  // Remove user marker
  if (userMarker) {
    userMarker.setMap(null);
    userMarker = null;
  }

  mapView.userLocation = null;

  showMapLoading();

  // Reload all cinemas
  const allCinemas = await findCinemasWithTodayShowtimes();

  // Update markers
  addCinemaMarkers(allCinemas);

  // Reset summary
  showMapSummary(allCinemas);

  hideMapLoading();
}

/**
 * Show summary in location mode
 */
function showLocationModeSummary(cinemas, radiusKm) {
  const summary = document.getElementById('mapSummary');
  if (!summary) return;

  // Count cinemas with next showtime
  const cinemasWithShowtimes = cinemas.filter(c => c.nextShowtime).length;

  summary.querySelector('.map-summary-content').innerHTML = `
    <div class="map-stat">
      <span class="map-stat-value">${cinemas.length}</span>
      <span class="map-stat-label">σε ${radiusKm}km</span>
    </div>
    <div class="map-stat success">
      <span class="map-stat-value">${cinemasWithShowtimes}</span>
      <span class="map-stat-label">με προβολές</span>
    </div>
  `;
}

// ============ DIRECTIONS & SHARING ============

/**
 * View cinema in main list - close map and scroll to cinema
 */
function viewCinemaInList(cinemaName) {
  // Close the map view
  hideMapView();

  // Wait for transition to complete, then scroll to cinema
  setTimeout(() => {
    // Find the cinema card in the main list
    const cinemaCards = document.querySelectorAll('.cinema-card');

    for (const card of cinemaCards) {
      const titleElement = card.querySelector('h2');
      if (titleElement && titleElement.textContent.trim() === cinemaName) {
        // Scroll to the cinema card with smooth animation
        card.scrollIntoView({
          behavior: 'smooth',
          block: 'start',
          inline: 'nearest'
        });

        // Add a highlight effect
        card.style.transition = 'background-color 0.5s ease';
        const originalBg = card.style.backgroundColor;
        card.style.backgroundColor = '#fff3cd';

        setTimeout(() => {
          card.style.backgroundColor = originalBg;
        }, 2000);

        break;
      }
    }
  }, 300);
}

/**
 * Open directions to cinema in Google Maps
 */
function openDirections(cinemaName, lat, lng) {
  const url = `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}&destination_place_id=${encodeURIComponent(cinemaName)}`;
  window.open(url, '_blank');
}

/**
 * Share cinema location
 */
async function shareLocation(cinemaName, address) {
  const text = `🎬 ${cinemaName}\n📍 ${address}\n\nΠάμε σινεμά;`;
  const url = window.location.href;

  if (navigator.share) {
    try {
      await navigator.share({ title: cinemaName, text, url });
    } catch (err) {
      console.log('Share cancelled');
    }
  } else {
    // Fallback: copy to clipboard
    navigator.clipboard.writeText(`${text}\n${url}`);
    showToast('✅ Αντιγράφηκε!');
  }
}

/**
 * Show toast notification
 */
function showToast(message) {
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed;
    bottom: 100px;
    left: 50%;
    transform: translateX(-50%);
    background: #28a745;
    color: white;
    padding: 12px 24px;
    border-radius: 24px;
    font-weight: 600;
    z-index: 10000;
    animation: slideUp 0.3s ease-out;
  `;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2000);
}

// ============ ANALYTICS ============

function trackMapViewActivation(cinemaCount) {
  if (typeof gtag !== 'undefined') {
    gtag('event', 'map_view_activated', {
      cinema_count: cinemaCount,
      view_type: 'simple_today'
    });
  }
}

// ============ EXPORT ============

window.showMapView = showMapView;
window.hideMapView = hideMapView;
window.toggleView = toggleView;
window.enableLocationMode = enableLocationMode;
window.updateLocationFilter = updateLocationFilter;
window.resetToAllCinemas = resetToAllCinemas;
window.viewCinemaInList = viewCinemaInList;
window.openDirections = openDirections;
window.shareLocation = shareLocation;
window.hideLocationModal = hideLocationModal;
