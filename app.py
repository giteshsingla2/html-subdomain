import random
import hashlib
from flask import Flask, render_template, request, abort, redirect, url_for, jsonify, Response, send_from_directory
from markupsafe import Markup
from flask_caching import Cache
from jinja2 import Template
import os
import json
import sqlite3
from datetime import datetime
from markupsafe import Markup
import re
import urllib.parse

# Cache for random seeds based on city-state pairs
spintax_seed_cache = {}

app = Flask(__name__)

# Configure Flask-Caching
cache = Cache(app, config={
        'CACHE_TYPE': 'SimpleCache',
        'CACHE_DEFAULT_TIMEOUT': 0  # Never expire cache
    })

app.config['SERVER_NAME'] = 'demo.local:8000'


# Database cache initialization
class DatabaseCache:
    def __init__(self):
        self.states = {}
        self.cities = {}
        self.zip_codes = {}
        self._load_data()
    def _load_data(self):
        with sqlite3.connect('newcities.db') as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 1) load every distinct state
            cursor.execute("SELECT DISTINCT state_code, state_name FROM Cities")
            for row in cursor:
                abbr = row['state_code'].lower()
                self.states[abbr] = row['state_name']

            # 2) load cities grouped by state
            cursor.execute("SELECT city_name, state_code, main_zip_code, zip_codes FROM Cities")
            for row in cursor:
                abbr = row['state_code'].lower()
                city = row['city_name']
                # add city→state index
                self.cities.setdefault(abbr, []).append(city)
                # add zip index
                key = city.lower()
                zips = [z.strip() for z in row['zip_codes'].split(',') if z.strip()]
                self.zip_codes.setdefault(key, []).extend(zips)
                
# Initialize database cache at startup
db_cache = DatabaseCache()

@cache.memoize(timeout=300)
def load_json(filename):
    with open(filename, 'r') as f:
        return json.load(f)

@cache.memoize(timeout=3600)
def load_html_file(file_path):
    """Load HTML file from disk and cache it"""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        return None
    except Exception as e:
        print(f"Error loading HTML file {file_path}: {e}")
        return None

# Function to invalidate HTML cache when JSON files are updated
def invalidate_html_cache():
    """Invalidate the HTML file cache"""
    cache.delete_memoized(load_html_file)

def get_main_domain():
    host = request.host
    main_domain = ".".join(host.split('.')[-2:])
    return main_domain

def parse_subdomain():
    """Parse the subdomain to extract main_service, city, and state.
    
    Returns:
        tuple: (main_service, city_subdomain, state_subdomain)
    """
    host = request.host
    subdomains = host.split('.')[0].split('-')
    
    # Check if we have at least 3 parts: main-service, city, state
    if len(subdomains) >= 3:
        # The last part is the state
        state_subdomain = subdomains[-1]
        # The first part is the main service
        main_service = subdomains[0]
        # Everything in between is the city
        city_subdomain = '-'.join(subdomains[1:-1])
        return main_service, city_subdomain, state_subdomain
    else:
        # Not enough parts for the new format
        return None, None, None

# Before request middleware to load required.json
@app.before_request
def load_required_json():
    """Load required.json for the current domain before processing the request"""
    # Skip for static files
    if request.path.startswith('/static/') or request.path.startswith('/domains/'):
        return
        
    main_domain = get_main_domain()
    required_path = f"domains/{main_domain}/required.json"
    
    try:
        required_data = load_json(required_path)
        request.required_data = required_data
    except Exception as e:
        print(f"Error loading required.json: {e}")
        request.required_data = {}
        
    # Add the main domain to the request for easy access
    request.main_domain = main_domain

def replace_placeholders(text, service_name, city_name, state_abbreviation, state_full_name, required_data, zip_codes=[], city_zip_code=""):
    """Replace placeholders and process spintax in HTML content"""
    pattern = r'\{([^}]*)\}'
    
    # Generate a consistent seed for this city-state pair
    city_state_key = f"{city_name}|{state_abbreviation}"
    
    # Check if we already have a seed for this city-state pair
    if city_state_key not in spintax_seed_cache:
        # Create a reproducible seed by hashing the city-state key
        hash_obj = hashlib.md5(city_state_key.encode())
        seed_value = int(hash_obj.hexdigest(), 16) % (2**32)  # Convert to a 32-bit integer
        spintax_seed_cache[city_state_key] = seed_value
    
    # Get the seed for this city-state pair
    seed = spintax_seed_cache[city_state_key]
    
    # Create a random generator with the consistent seed
    rng = random.Random(seed)
    
    def random_replacer(match):
        options = match.group(1).split('|')
        return rng.choice(options)
        
    # Step 1: Replace random choice patterns with consistent choices
    text = re.sub(pattern, random_replacer, text)

    # Step 2: Replace placeholders
    replacements = {
        "[Service]": service_name,
        "[service]": service_name.lower(),
        "[City-State]": f"{city_name}, {state_abbreviation}",
        "[city-state]": f"{city_name.lower()}, {state_abbreviation.lower()}",
        "[City]": city_name,
        "[city]": city_name.lower(),
        "[CITY]": city_name.upper(),
        "[State]": state_abbreviation,
        "[state]": state_abbreviation.lower(),
        "[STATE]": state_abbreviation.upper(),
        "[State Full]": state_full_name,
        "[Zipcode]": city_zip_code,  # Add new format
        "[City Zip Code]": city_zip_code,
        "[Zip Codes]": ", ".join(str(z) for z in zip_codes if z),
        "[Company Name]": required_data.get("Business Name", "N/A"),
        "[Phone]": required_data.get("Phone", "N/A"),
        "[Email]": required_data.get("Business Email", "N/A"),
        "[Address]": required_data.get("Business Address", "N/A")
    }
    
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, str(value))
        
    return text

def get_db_connection():
    conn = sqlite3.connect('newcities.db')
    conn.row_factory = sqlite3.Row
    return conn

@cache.memoize(timeout=86400)  # Cache for 1 day
def get_state_full_name(state_abbr):
    return db_cache.states.get(state_abbr)

@cache.memoize(timeout=86400)  # Cache for 1 day
def state_exists(state_abbr):
    return state_abbr in db_cache.states

@cache.memoize(timeout=86400)  # Cache for 1 day
def get_cities_in_state(state_abbr):
    return db_cache.cities.get(state_abbr, [])

def get_city_info(city_subdomain, state_abbr):
    city_subdomain_lower = city_subdomain.lower()
    state_abbr_lower = state_abbr.lower()
    
    # Convert any hyphens in city_subdomain to spaces
    city_search = city_subdomain_lower.replace('-', ' ')
    
    # Retrieve matching city from database
    with sqlite3.connect('newcities.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Try exact match first
        cursor.execute(
            "SELECT city_name, state_code, main_zip_code FROM Cities WHERE LOWER(city_name) = ? AND LOWER(state_code) = ?",
            (city_search, state_abbr_lower)
        )
        row = cursor.fetchone()

    if row:
        return {
        'city_name': row['city_name'],
        'zip_code': row['main_zip_code']
    }

def get_states():
    """Get list of all states from the database"""
    return list(db_cache.states.keys())

def get_cities_in_state(state_code):
    """Get list of all cities in a state from the database"""
    state_code = state_code.lower()
    cities = []
    
    # Get cities for this state from the cache
    for city_key, state in db_cache.cities.items():
        if state == state_code:
            city_name = city_key.split('|')[0]  # Extract city name from the key
            cities.append(city_name)
    
    # Sort cities alphabetically
    return sorted(cities)

def get_other_cities_in_state(state_code, current_city):
    """Get list of other cities in the same state, excluding the current city"""
    all_cities = get_cities_in_state(state_code)
    # Remove the current city from the list
    return [city for city in all_cities if city.lower() != current_city.lower()]

def get_zip_codes_from_db(city_name):
    # Make sure we're using lowercase for lookup
    city_key = city_name.lower()
    # Get zip codes for this city
    zip_codes = db_cache.zip_codes.get(city_key, [])
    # If no zip codes found, try to find the city in the keys with partial matching
    if not zip_codes:
        for city_in_cache in db_cache.zip_codes.keys():
            if city_key in city_in_cache or city_in_cache in city_key:
                zip_codes = db_cache.zip_codes.get(city_in_cache, [])
                if zip_codes:
                    break
    # Ensure we're returning a list of strings
    return [str(zip_code) for zip_code in zip_codes] if zip_codes else []

def get_canonical_url(path=None):
    """Get canonical URL for the current request or specified path"""
    host = request.host
    scheme = request.scheme
    
    if path is None:
        path = request.path
    
    # Remove trailing slash if present
    if path.endswith('/') and path != '/':
        path = path[:-1]
        
    return f"{scheme}://{host}{path}"

def get_current_month_year():
    now = datetime.now()
    return {
        "month": now.strftime("%B"),
        "year": now.strftime("%Y")
    }

@app.before_request
def before_request():
    # Load only the required.json data
    request.required_data = load_required_json()

@app.context_processor
def inject_date():
    return get_current_month_year()

def get_other_cities_in_state(state_abbr, current_city_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT city_name
          FROM Cities
         WHERE LOWER(state_code) = ?
           AND LOWER(city_name) != ?
         ORDER BY city_name ASC
        """,
        (state_abbr.lower(), current_city_name.lower())
    )
    cities = [row['city_name'] for row in cursor.fetchall()]
    conn.close()
    return cities

@app.route('/')
def handle_home():
    """Main route handler for homepage"""
    host = request.host
    main_domain = get_main_domain()
    
    # Check if we're on the main domain (not a subdomain)
    if host in [main_domain, f"www.{main_domain}"]:
        # This is the main domain homepage - show states list
        states = get_states()
        state_links = {state: f"https://{state}.{main_domain}" for state in states}
        
        # Load required.json for main service
        required_data = request.required_data
        
        # Get HTML content from domain folder
        home_path = f"domains/{main_domain}/home.html"
        
        try:
            # First try to load the HTML file
            content = load_html_file(home_path)
            if content:
                # Render the template with Jinja2
                template = Template(content)
                rendered = template.render(
                    state_links=state_links,
                    required=required_data,
                    canonical_url=get_canonical_url(),
                    favicon=required_data.get("favicon"),
                    main_service=required_data.get("main-service"),
                    company_name=required_data.get("company_name")
                )
                return rendered
            else:
                # Fallback to template rendering if HTML file doesn't exist
                return render_template(
                    'home.html',
                    state_links=state_links,
                    required=required_data,
                    canonical_url=get_canonical_url(),
                    favicon=required_data.get("favicon"),
                    main_service=required_data.get("main-service"),
                    company_name=required_data.get("company_name")
                )
        except Exception as e:
            print(f"Error serving homepage: {e}")
            # Fallback to template rendering
            return render_template(
                'home.html',
                state_links=state_links,
                required=required_data,
                canonical_url=get_canonical_url(),
                favicon=required_data.get("favicon"),
                main_service=required_data.get("main-service"),
                company_name=required_data.get("company_name")
            )
    else:
        # Check if we have a state subdomain
        parts = host.split('.')
        subdomain = parts[0].lower()
        
        # Check if the subdomain is a valid state code
        if state_exists(subdomain) and len(parts) >= 2 and len(subdomain) == 2:
            # It's a state page - list all cities in that state
            state = subdomain
            state_full_name = get_state_full_name(state)
            cities = get_cities_in_state(state)
            
            # Load required.json for main service
            required_data = request.required_data
            main_service = required_data.get("main-service", "")
            
            # Prepare city links - each city gets its own page
            city_links = {}
            for city in cities:
                # Format city name for URL (lowercase, hyphens instead of spaces)
                city_slug = city.lower().replace(' ', '-')
                # Use the subdomain format: main-service-city-state
                if main_service:
                    main_service_slug = main_service.lower().replace(' ', '-')
                    url = f"https://{main_service_slug}-{city_slug}-{state}.{main_domain}"
                    city_links[city] = url
            
            # Get HTML content from domain folder
            state_path = f"domains/{main_domain}/state.html"
            
            try:
                # First try to load the HTML file
                content = load_html_file(state_path)
                if content:
                    # Render the template with Jinja2
                    template = Template(content)
                    rendered = template.render(
                        state=state.upper(),
                        state_full_name=state_full_name,
                        city_links=city_links,
                        required=required_data,
                        canonical_url=get_canonical_url(),
                        favicon=required_data.get("favicon"),
                        main_service=main_service,
                        company_name=required_data.get("company_name")
                    )
                    return rendered
                else:
                    # Fallback to template rendering if HTML file doesn't exist
                    return render_template(
                        'state.html',
                        state=state.upper(),
                        state_full_name=state_full_name,
                        city_links=city_links,
                        required=required_data,
                        canonical_url=get_canonical_url(),
                        favicon=required_data.get("favicon"),
                        main_service=main_service,
                        company_name=required_data.get("company_name")
                    )
            except Exception as e:
                print(f"Error serving state page: {e}")
                # Fallback to template rendering
                return render_template(
                    'state.html',
                    state=state.upper(),
                    state_full_name=state_full_name,
                    city_links=city_links,
                    required=required_data,
                    canonical_url=get_canonical_url(),
                    favicon=required_data.get("favicon"),
                    main_service=main_service,
                    company_name=required_data.get("company_name")
                )
        else:
            # Parse subdomain for city page
            main_service, city_subdomain, state_subdomain = parse_subdomain()
            if not (main_service and city_subdomain and state_subdomain):
                abort(404)
                
            # Get city info
            city_info = get_city_info(city_subdomain, state_subdomain)
            if not city_info or not state_exists(state_subdomain):
                abort(404)
                
            # Load city.html for the main page
            city_path = f"domains/{main_domain}/city.html"
            
            city_name = city_info['city_name'].title()
            city_zip_code = city_info['zip_code']
            state_name = get_state_full_name(state_subdomain)
            state_abbreviation = state_subdomain.upper()
            zip_codes = get_zip_codes_from_db(city_name)
            
            # Load required.json for main service
            required_data = request.required_data
            main_service_name = required_data.get('main-service', main_service)
            
            try:
                content = load_html_file(city_path)
                if content:
                    # Get other cities in the same state for navigation
                    other_cities = get_other_cities_in_state(state_subdomain, city_name)
                    other_city_links = {}
                    
                    # Create links for up to 10 other cities
                    if other_cities:
                        # Use a deterministic selection based on the city name
                        city_index = sum(ord(char) for char in city_name) % len(other_cities)
                        rotated_cities = other_cities[city_index:] + other_cities[:city_index]
                        cities_to_display = rotated_cities[:10]
                        
                        for city in cities_to_display:
                            city_slug = city.lower().replace(' ', '-')
                            main_service_slug = main_service_name.lower().replace(' ', '-')
                            url = f"https://{main_service_slug}-{city_slug}-{state_subdomain}.{get_main_domain()}"
                            other_city_links[city] = url
                    
                    # Replace placeholders in the HTML content
                    processed_content = replace_placeholders(
                        content,
                        main_service_name,
                        city_name,
                        state_abbreviation,
                        state_name,
                        required_data,
                        zip_codes,
                        city_zip_code
                    )
                    
                        # Check if the content has any Jinja2 template tags
                    if "{% for" in processed_content or "{{ " in processed_content:
                        # Create a Jinja2 template from the processed content
                        template = Template(processed_content)
                        # Render the template with all the variables
                        processed_content = template.render(
                            other_city_links=other_city_links,
                            canonical_url=get_canonical_url(),
                            city=city_name,
                            state=state_abbreviation,
                            state_full_name=state_name,
                            main_service=main_service_name,
                            company_name=required_data.get("Company Name", ""),
                            zip_codes=zip_codes,
                            city_zip_code=city_zip_code,
                            phone=required_data.get("Phone No. Placeholder", "")
                        )
                    
                    return processed_content
                else:
                    abort(404)
            except Exception as e:
                print(f"Error serving city page: {e}")
                abort(404)

@app.route('/<page_name>')
def handle_page(page_name):
    """Generic route handler for any HTML page in the domain folder"""
    # Parse subdomain
    main_service, city_subdomain, state_subdomain = parse_subdomain()
    
    if not (main_service and city_subdomain and state_subdomain):
        # Not a valid subdomain
        abort(404)
    
    # Get city info
    city_info = get_city_info(city_subdomain, state_subdomain)
    if not city_info or not state_exists(state_subdomain):
        abort(404)
        
    city_name = city_info['city_name'].title()
    city_zip_code = city_info['zip_code']
    state_name = get_state_full_name(state_subdomain)
    state_abbreviation = state_subdomain.upper()
    zip_codes = get_zip_codes_from_db(city_name)
    
    # Load required.json for main service
    required_data = request.required_data
    main_service_name = required_data.get('main-service', main_service)
    
    # Get HTML content from domain folder - could be a service page or other page like about.html
    main_domain = get_main_domain()
    page_path = f"domains/{main_domain}/{page_name}.html"
    
    try:
        content = load_html_file(page_path)
        if not content:
            abort(404)
            
        # Replace placeholders in the HTML content
        processed_content = replace_placeholders(
            content,
            main_service_name,
            city_name,
            state_abbreviation,
            state_name,
            required_data,
            zip_codes,
            city_zip_code
        )
        
        # Add canonical URL meta tag if not already present
        canonical_url = get_canonical_url(f"/{page_name}")
        if canonical_url and "<head>" in processed_content and "rel=\"canonical\"" not in processed_content:
            canonical_meta = f'<link rel="canonical" href="{canonical_url}" />'
            processed_content = processed_content.replace("</head>", f"{canonical_meta}\n</head>")
            
        # Check if the content has any Jinja2 template tags
        if "{% for" in processed_content or "{{ " in processed_content:
            # Parse subdomain to get city and state info
            main_service, city_subdomain, state_subdomain = parse_subdomain()
            
            if main_service and city_subdomain and state_subdomain:
                # Get city info
                city_info = get_city_info(city_subdomain, state_subdomain)
                if city_info and state_exists(state_subdomain):
                    city_name = city_info['city_name'].title()
                    city_zip_code = city_info['zip_code']
                    state_name = get_state_full_name(state_subdomain)
                    state_abbreviation = state_subdomain.upper()
                    zip_codes = get_zip_codes_from_db(city_name)
                    
                    # Load required.json for main service
                    required_data = request.required_data
                    main_service_name = required_data.get('main-service', main_service)
                    
                    # Create a Jinja2 template from the processed content
                    template = Template(processed_content)
                    # Render the template with all the variables
                    processed_content = template.render(
                        canonical_url=canonical_url,
                        city=city_name,
                        state=state_abbreviation,
                        state_full_name=state_name,
                        main_service=main_service_name,
                        company_name=required_data.get("Company Name", ""),
                        zip_codes=zip_codes,
                        city_zip_code=city_zip_code,
                        phone=required_data.get("Phone No. Placeholder", "")
                    )
        
        return processed_content
    except Exception as e:
        print(f"Error serving page {page_name}: {e}")
        abort(404)

@app.route('/update-json/<filename>', methods=['POST'])
def update_json(filename):
    """Update JSON file and invalidate cache"""
    if not filename.endswith('.json'):
        return jsonify({"error": "Invalid file type"}), 400
        
    main_domain = get_main_domain()
    file_path = f"domains/{main_domain}/{filename}"
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        # Write the updated JSON to file
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
            
        # Invalidate the cache for this file
        cache.delete_memoized(load_json, file_path)
        
        # Also invalidate HTML cache since JSON data changed
        invalidate_html_cache()
        
        return jsonify({"success": True, "message": f"{filename} updated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors"""
    # Try to load a custom 404 page from the domain folder
    main_domain = get_main_domain()
    custom_404_path = f"domains/{main_domain}/404.html"
    
    # Parse subdomain to see if we're on a city page
    main_service, city_subdomain, state_subdomain = parse_subdomain()
    
    if main_service and city_subdomain and state_subdomain:
        # We're on a city page, try to get city info for placeholder replacement
        try:
            city_info = get_city_info(city_subdomain, state_subdomain)
            if city_info and state_exists(state_subdomain):
                city_name = city_info['city_name'].title()
                city_zip_code = city_info['zip_code']
                state_name = get_state_full_name(state_subdomain)
                state_abbreviation = state_subdomain.upper()
                zip_codes = get_zip_codes_from_db(city_name)
                
                # Load required.json for main service
                required_data = request.required_data
                main_service_name = required_data.get('main-service', main_service)
                
                # Try to load and process the 404 page with placeholders
                content = load_html_file(custom_404_path)
                if content:
                    processed_content = replace_placeholders(
                        content,
                        main_service_name,
                        city_name,
                        state_abbreviation,
                        state_name,
                        required_data,
                        zip_codes,
                        city_zip_code
                    )
                    return processed_content, 404
        except Exception as e:
            print(f"Error processing 404 page: {e}")
    
    # Simple fallback if no custom 404 or error in processing
    try:
        content = load_html_file(custom_404_path)
        if content:
            return content, 404
    except:
        pass
        
    # Fallback to a simple 404 message
    return "Page not found", 404

@app.route('/domains/<domain>/<path:filename>')
def serve_domain_static(domain, filename):
    domain_dir = os.path.join('domains', domain)
    return send_from_directory(domain_dir, filename)

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files from the domain folder"""
    main_domain = get_main_domain()
    static_folder = f"domains/{main_domain}/static"
    
    # Make sure the static folder exists
    if not os.path.exists(static_folder):
        os.makedirs(static_folder, exist_ok=True)
    
    return send_from_directory(static_folder, filename)

@app.route('/')
def handle_home():
    """Main route handler for homepage"""
    # Parse subdomain
    main_service, city_subdomain, state_subdomain = parse_subdomain()
    
    if not (main_service and city_subdomain and state_subdomain):
        # Not a valid subdomain
        abort(404)
    
    # Get city info
    city_info = get_city_info(city_subdomain, state_subdomain)
    if not city_info or not state_exists(state_subdomain):
        abort(404)
        
    city_name = city_info['city_name'].title()
    city_zip_code = city_info['zip_code']
    state_name = get_state_full_name(state_subdomain)
    state_abbreviation = state_subdomain.upper()
    zip_codes = get_zip_codes_from_db(city_name)
    
    # Load required.json for main service
    required_data = request.required_data
    main_service_name = required_data.get('main-service', main_service)
    
    # Get HTML content from domain folder
    main_domain = get_main_domain()
    index_path = f"domains/{main_domain}/index.html"
    
    try:
        content = load_html_file(index_path)
        if not content:
            abort(404)
            
        # Replace placeholders in the HTML content
        processed_content = replace_placeholders(
            content,
            main_service_name,
            city_name,
            state_abbreviation,
            state_name,
            required_data,
            zip_codes,
            city_zip_code
        )
        
        return processed_content
    except Exception as e:
        print(f"Error serving homepage: {e}")
        abort(404)

@app.route('/<page_name>')
def handle_page(page_name):
    """Handle generic page requests like about, contact, services, etc."""
    # Parse subdomain
    main_service, city_subdomain, state_subdomain = parse_subdomain()
    
    if not (main_service and city_subdomain and state_subdomain):
        # Not a valid subdomain
        abort(404)
    
    # Get city info
    city_info = get_city_info(city_subdomain, state_subdomain)
    if not city_info or not state_exists(state_subdomain):
        abort(404)
        
    city_name = city_info['city_name'].title()
    city_zip_code = city_info['zip_code']
    state_name = get_state_full_name(state_subdomain)
    state_abbreviation = state_subdomain.upper()
    zip_codes = get_zip_codes_from_db(city_name)
    
    # Load required.json for main service
    required_data = request.required_data
    main_service_name = required_data.get('main-service', main_service)
    
    # Get HTML content from domain folder - could be a service page or other page like about.html
    main_domain = get_main_domain()
    page_path = f"domains/{main_domain}/{page_name}.html"
    
    try:
        content = load_html_file(page_path)
        if not content:
            abort(404)
            
        # Replace placeholders in the HTML content
        processed_content = replace_placeholders(
            content,
            main_service_name,
            city_name,
            state_abbreviation,
            state_name,
            required_data,
            zip_codes,
            city_zip_code
        )
        
        return processed_content
    except Exception as e:
        print(f"Error serving page {page_name}: {e}")
        abort(404)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8001)