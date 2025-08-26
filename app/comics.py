"""
Comics blueprint for Comic Book Collection Manager.
Handles comic book CRUD operations, search, and filtering.
"""

import os
import requests
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from PIL import Image
from . import db
from .models import Comic
from .forms import ComicForm, SearchForm

comics_bp = Blueprint('comics', __name__)

def search_comicvine_api(query, api_key):
    """Search ComicVine API with enhanced filters."""
    search_url = "https://comicvine.gamespot.com/api/issues/"
    
    # Create enhanced search filters
    search_filters = []
    
    # Add the original query
    search_filters.append(f'name:{query}')
    
    # If query has spaces, try URL encoded version
    if ' ' in query:
        search_filters.append(f'name:{query.replace(" ", "%20")}')
    
    # Try without spaces
    no_spaces = query.replace(" ", "")
    if no_spaces != query:
        search_filters.append(f'name:{no_spaces}')
    
    # Try first word only
    first_word = query.split()[0]
    if first_word != query:
        search_filters.append(f'name:{first_word}')
    
    # Try common variations for superhero names
    if 'iron' in query.lower() and 'man' in query.lower():
        search_filters.extend([
            'name:Iron Man',
            'name:Ironman',
            'name:Invincible Iron Man',
            'name:Iron Man 2.0'
        ])
    elif 'spider' in query.lower() and 'man' in query.lower():
        search_filters.extend([
            'name:Spider-Man',
            'name:Amazing Spider-Man',
            'name:Ultimate Spider-Man'
        ])
    elif 'batman' in query.lower():
        search_filters.extend([
            'name:Batman',
            'name:Batman: The Dark Knight Returns',
            'name:Batman: Year One'
        ])
    
    # Remove duplicates
    search_filters = list(dict.fromkeys(search_filters))
    
    all_results = []
    for search_filter in search_filters:
        try:
            headers = {
                'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x'
            }
            
            params = {
                'api_key': api_key,
                'format': 'json',
                'filter': search_filter,
                'limit': 20,
                'field_list': 'id,name,issue_number,publisher,character_credits,deck,store_date,image,volume,upc'
            }
            
            response = requests.get(search_url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if 'results' in data:
                for result in data['results']:
                    # Check if we already have this result
                    if not any(r.get('id') == result.get('id') for r in all_results):
                        # Format the result to match our expected structure
                        formatted_result = {
                            'id': result.get('id'),
                            'title': result.get('name', ''),
                            'issue_number': result.get('issue_number', ''),
                            'publisher': result.get('publisher', {}).get('name', '') if result.get('publisher') else '',
                            'characters': ', '.join([char.get('name', '') for char in result.get('character_credits', [])]),
                            'genre': 'Superhero',
                            'release_date': result.get('store_date', ''),
                            'description': result.get('deck', ''),
                            'cover_image_url': result.get('image', {}).get('super_url', '') if result.get('image') else '',
                            'volume': result.get('volume', {}).get('name', '') if result.get('volume') else '',
                            'upc': result.get('upc', ''),
                            'isbn': '',  # ComicVine doesn't provide ISBN
                            'source': 'ComicVine'
                        }
                        all_results.append(formatted_result)
            
            if len(all_results) >= 15:
                break
                
        except Exception as e:
            print(f"❌ ComicVine search failed for filter {search_filter}: {e}")
            continue
    
    return all_results

def search_marvel_api(query, api_key, private_key):
    """Search Marvel Comics API."""
    import hashlib
    import time
    
    # Marvel API requires timestamp and hash
    # According to Marvel API docs: hash = md5(ts + privateKey + publicKey)
    timestamp = str(int(time.time()))
    hash_input = timestamp + private_key + api_key
    hash_value = hashlib.md5(hash_input.encode('utf-8')).hexdigest()
    
    search_url = "https://gateway.marvel.com/v1/public/comics"
    
    try:
        headers = {
            'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x'
        }
        
        # Clean up the query for Marvel API (remove special characters)
        clean_query = query.replace('#', '').replace('@', '').replace('!', '').replace('?', '')
        
        params = {
            'apikey': api_key,
            'ts': timestamp,
            'hash': hash_value,
            'titleStartsWith': clean_query,
            'limit': 20,
            'format': 'comic',
            'formatType': 'comic'
        }
        
        print(f"🔍 Marvel API params: {params}")
        print(f"🔍 Hash Input (timestamp + private_key + public_key): {timestamp + '***' + api_key}")
        print(f"🔍 Generated Hash: {hash_value}")
        
        response = requests.get(search_url, params=params, headers=headers, timeout=10)
        print(f"📡 Marvel API Response status: {response.status_code}")
        
        if response.status_code == 401:
            print(f"❌ Marvel API Authentication failed. Check your API keys.")
            print(f"🔑 Public Key: {api_key[:10]}...")
            print(f"🔑 Private Key: {private_key[:10]}...")
            print(f"🔍 Full URL: {response.url}")
            print(f"🔍 Response Text: {response.text[:500]}...")
            print(f"📋 According to Marvel API docs, check:")
            print(f"   - API key is valid and not expired")
            print(f"   - Private key is correct")
            print(f"   - Hash generation: md5(ts + privateKey + publicKey)")
            return []
        elif response.status_code == 409:
            print(f"❌ Marvel API Error 409: Missing required parameters")
            print(f"📋 Required: apikey, ts, hash for server-side applications")
            return []
        
        response.raise_for_status()
        
        data = response.json()
        results = []
        
        if 'data' in data and 'results' in data['data']:
            for comic in data['data']['results']:
                result = {
                    'id': comic.get('id'),
                    'title': comic.get('title', ''),
                    'issue_number': comic.get('issueNumber', ''),
                    'publisher': 'Marvel Comics',
                    'characters': ', '.join([char.get('name', '') for char in comic.get('characters', {}).get('items', [])]),
                    'genre': 'Superhero',
                    'release_date': comic.get('dates', [{}])[0].get('date', '') if comic.get('dates') else '',
                    'description': comic.get('description', ''),
                    'cover_image_url': comic.get('thumbnail', {}).get('path', '') + '.' + comic.get('thumbnail', {}).get('extension', '') if comic.get('thumbnail') else '',
                    'volume': comic.get('series', {}).get('name', '')
                }
                results.append(result)
        
        print(f"📚 Marvel API found {len(results)} results")
        return results
        
    except Exception as e:
        print(f"❌ Marvel API search failed: {e}")
        return []

def search_local_database(query):
    """Enhanced local database search including barcode search."""
    try:
        # More flexible local search
        search_terms = [query, query.replace(' ', ''), query.split()[0]]
        
        all_results = []
        for term in search_terms:
            local_results = Comic.query.filter(
                db.or_(
                    Comic.title.ilike(f'%{term}%'),
                    Comic.characters.ilike(f'%{term}%'),
                    Comic.publisher.ilike(f'%{term}%'),
                    Comic.genre.ilike(f'%{term}%'),
                                                 Comic.upc.ilike(f'%{term}%'),  # Add UPC search
                             Comic.isbn.ilike(f'%{term}%')   # Add ISBN search
                )
            ).limit(10).all()
            
            for comic in local_results:
                result = {
                    'id': comic.id,
                    'title': comic.title,
                    'issue_number': comic.issue_number,
                    'publisher': comic.publisher,
                    'characters': comic.characters,
                    'genre': comic.genre,
                    'release_date': comic.release_date.strftime('%Y-%m-%d') if comic.release_date else '',
                    'description': comic.notes,
                    'cover_image_url': '',
                    'volume': '',
                                                'upc': comic.upc or '',  # Include UPC in results
                            'isbn': comic.isbn or '',  # Include ISBN in results
                    'source': 'Local Database'
                }
                all_results.append(result)
        
        return all_results
        
    except Exception as e:
        print(f"❌ Local search failed: {e}")
        return []

def search_openlibrary_api(query):
    """Search Open Library API for comics with ISBN barcode information."""
    search_url = "https://openlibrary.org/search.json"
    
    try:
        headers = {
            'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x'
        }
        
        # Open Library API parameters - search for comics
        params = {
            'q': f'{query} comic',
            'subject': 'comic',
            'limit': 20,
            'fields': 'title,author_name,isbn,publish_date,publisher,cover_i,key'
        }
        
        print(f"🔍 Searching Open Library API for: {query}")
        response = requests.get(search_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        results = []
        
        if 'docs' in data:
            for book in data['docs']:
                # Extract ISBN information
                isbn = ''
                if book.get('isbn'):
                    # Get the first ISBN (usually the main one)
                    isbns = book['isbn'] if isinstance(book['isbn'], list) else [book['isbn']]
                    if isbns:
                        isbn = isbns[0]
                
                # Only include if it has an ISBN
                if isbn:
                    result = {
                        'id': book.get('key', ''),
                        'title': book.get('title', ''),
                        'issue_number': '1',  # Open Library doesn't have issue numbers
                        'publisher': ', '.join(book.get('publisher', [])) if book.get('publisher') else '',
                        'characters': ', '.join(book.get('author_name', [])) if book.get('author_name') else '',
                        'genre': 'Comic',
                        'release_date': book.get('publish_date', [''])[0] if book.get('publish_date') else '',
                        'description': f"Comic book found via Open Library with ISBN: {isbn}",
                        'cover_image_url': f"https://covers.openlibrary.org/b/id/{book.get('cover_i')}-M.jpg" if book.get('cover_i') else '',
                        'volume': '',
                        'upc': '',  # Open Library doesn't provide UPC
                        'isbn': isbn,
                        'source': 'Open Library'
                    }
                    results.append(result)
        
        print(f"📚 Open Library API found {len(results)} results with barcodes")
        return results
        
    except Exception as e:
        print(f"❌ Open Library API search failed: {e}")
        return []

def search_upc_database_api(query, api_key):
    """Search UPC Database API for comic book data."""
    if not api_key:
        return []
    
    # Clean the query (remove any non-numeric characters for UPC)
    upc_code = ''.join(filter(str.isdigit, query))
    
    if len(upc_code) < 10:  # UPC codes are typically 12-13 digits
        return []
    
    # Use OAuth Bearer token authentication
    url = f"https://api.upcdatabase.org/product/{upc_code}"
    
    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Check if we got valid product data
            if data.get('valid') and data.get('product'):
                product = data['product']
                
                # Check if this looks like a comic book
                title = product.get('title', '')
                category = product.get('category', '').lower()
                
                # Filter for comic book related items
                comic_keywords = ['comic', 'graphic novel', 'marvel', 'dc', 'superhero', 'spider-man', 'batman', 'superman']
                is_comic = any(keyword in title.lower() or keyword in category for keyword in comic_keywords)
                
                if is_comic or 'book' in category:
                    # Extract publisher from brand or manufacturer
                    publisher = product.get('brand') or product.get('manufacturer') or 'Unknown'
                    
                    # Try to extract issue number from title
                    issue_number = '1'  # Default
                    if '#' in title:
                        try:
                            issue_match = title.split('#')[1].split()[0]
                            if issue_match.isdigit():
                                issue_number = issue_match
                        except:
                            pass
                    
                    result = {
                        'id': f"upc_{upc_code}",
                        'title': title,
                        'issue_number': issue_number,
                        'publisher': publisher,
                        'characters': '',
                        'genre': 'Comic Book',
                        'release_date': '',
                        'description': product.get('description', ''),
                        'cover_image_url': product.get('image', ''),
                        'volume': '',
                        'upc': upc_code,
                        'isbn': product.get('isbn', ''),
                        'source': 'UPC Database'
                    }
                    
                    return [result]
        
        elif response.status_code == 401:
            print(f"❌ UPC Database API: Invalid API key")
        elif response.status_code == 404:
            print(f"❌ UPC Database API: Product not found for UPC {upc_code}")
        else:
            print(f"❌ UPC Database API: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"❌ UPC Database API error: {e}")
    
    return []

def search_barcode_lookup_api(query, api_key):
    """Search Barcode Lookup API for comic book data."""
    if not api_key:
        return []
    
    # Clean the query (remove any non-numeric characters for UPC)
    upc_code = ''.join(filter(str.isdigit, query))
    
    if len(upc_code) < 10:  # UPC codes are typically 12-13 digits
        return []
    
    url = "https://api.barcodelookup.com/v3/products"
    
    try:
        headers = {
            'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x'
        }
        
        params = {
            'barcode': upc_code,
            'key': api_key
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('products') and len(data['products']) > 0:
                product = data['products'][0]
                
                # Check if this looks like a comic book
                title = product.get('title', '')
                category = product.get('category', '').lower()
                
                # Filter for comic book related items
                comic_keywords = ['comic', 'graphic novel', 'marvel', 'dc', 'superhero', 'spider-man', 'batman', 'superman']
                is_comic = any(keyword in title.lower() or keyword in category for keyword in comic_keywords)
                
                if is_comic or 'book' in category:
                    # Extract publisher from brand
                    publisher = product.get('brand') or 'Unknown'
                    
                    # Try to extract issue number from title
                    issue_number = '1'  # Default
                    if '#' in title:
                        try:
                            issue_match = title.split('#')[1].split()[0]
                            if issue_match.isdigit():
                                issue_number = issue_match
                        except:
                            pass
                    
                    result = {
                        'id': f"barcode_{upc_code}",
                        'title': title,
                        'issue_number': issue_number,
                        'publisher': publisher,
                        'characters': '',
                        'genre': 'Comic Book',
                        'release_date': '',
                        'description': product.get('description', ''),
                        'cover_image_url': product.get('images', [{}])[0].get('url', '') if product.get('images') else '',
                        'volume': '',
                        'upc': upc_code,
                        'isbn': product.get('isbn', ''),
                        'source': 'Barcode Lookup'
                    }
                    
                    return [result]
        
        elif response.status_code == 401:
            print(f"❌ Barcode Lookup API: Invalid API key")
        elif response.status_code == 404:
            print(f"❌ Barcode Lookup API: Product not found for UPC {upc_code}")
        else:
            print(f"❌ Barcode Lookup API: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"❌ Barcode Lookup API error: {e}")
    
    return []

def save_cover_image(file):
    """Save uploaded cover image and return filename."""
    if file and file.filename:
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        
        # Save original file
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        
        # Ensure upload directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        try:
            file.save(filepath)
            print(f"File saved successfully: {filepath}")
        except Exception as e:
            print(f"Error saving file: {e}")
            return None
        
        # Create thumbnail without cropping
        try:
            with Image.open(filepath) as img:
                # Convert to RGB if necessary (for PNG with transparency)
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Create a white background
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                
                # Calculate new size maintaining aspect ratio
                width, height = img.size
                max_size = (300, 300)
                
                # Calculate scaling factor
                scale = min(max_size[0] / width, max_size[1] / height)
                new_size = (int(width * scale), int(height * scale))
                
                # Resize image
                img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Create a white background of the target size
                thumb = Image.new('RGB', max_size, (255, 255, 255))
                
                # Calculate position to center the image
                x = (max_size[0] - new_size[0]) // 2
                y = (max_size[1] - new_size[1]) // 2
                
                # Paste the resized image onto the background
                thumb.paste(img_resized, (x, y))
                
                thumb_filename = f"thumb_{filename}"
                thumb_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], thumb_filename)
                thumb.save(thumb_filepath, 'JPEG', quality=85)
                print(f"Thumbnail created: {thumb_filepath}")
        except Exception as e:
            print(f"Error creating thumbnail: {e}")
        
        return filename
    return None

@comics_bp.route('/comics')
@login_required
def index():
    """Display all comics with search and filtering."""
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '')
    publisher_filter = request.args.get('publisher', '')
    condition_filter = request.args.get('condition', '')
    genre_filter = request.args.get('genre', '')
    wishlist_only = request.args.get('wishlist', False, type=bool)
    
    # Build query
    query = Comic.query.filter_by(user_id=current_user.id)
    
    if search_query:
        query = query.filter(
            db.or_(
                Comic.title.ilike(f'%{search_query}%'),
                Comic.characters.ilike(f'%{search_query}%'),
                Comic.publisher.ilike(f'%{search_query}%')
            )
        )
    
    if publisher_filter:
        query = query.filter(Comic.publisher == publisher_filter)
    
    if condition_filter:
        query = query.filter(Comic.condition == condition_filter)
    
    if genre_filter:
        query = query.filter(Comic.genre.ilike(f'%{genre_filter}%'))
    
    if wishlist_only:
        query = query.filter(Comic.is_wishlist == True)
    
    # Get unique publishers for filter dropdown
    publishers = db.session.query(Comic.publisher).filter_by(
        user_id=current_user.id
    ).distinct().all()
    publishers = [pub[0] for pub in publishers if pub[0]]
    
    comics = query.order_by(Comic.title, Comic.issue_number).paginate(
        page=page, per_page=12, error_out=False
    )
    
    return render_template('comics/index.html',
                         title='My Comics',
                         comics=comics,
                         search_query=search_query,
                         publisher_filter=publisher_filter,
                         condition_filter=condition_filter,
                         genre_filter=genre_filter,
                         wishlist_only=wishlist_only,
                         publishers=publishers)

@comics_bp.route('/comics/new', methods=['GET', 'POST'])
@login_required
def new():
    """Add a new comic to the collection."""
    form = ComicForm()
    
    if form.validate_on_submit():
        comic = Comic(
            title=form.title.data,
            issue_number=form.issue_number.data,
            publisher=form.publisher.data,
            characters=form.characters.data,
            genre=form.genre.data,
            release_date=form.release_date.data,
            upc=form.upc.data,
            isbn=form.isbn.data,
            condition=form.condition.data,
            estimated_value=form.estimated_value.data or 0.0,
            notes=form.notes.data,
            is_wishlist=form.is_wishlist.data,
            user_id=current_user.id
        )
        
        # Handle cover image upload or fetched cover
        fetched_cover = request.form.get('fetched_cover')
        if fetched_cover:
            comic.cover_image = fetched_cover
        elif form.cover_image.data:
            filename = save_cover_image(form.cover_image.data)
            if filename:
                comic.cover_image = filename
        
        try:
            db.session.add(comic)
            db.session.commit()
            flash('Comic added successfully!', 'success')
            return redirect(url_for('comics.index'))
        except Exception as e:
            db.session.rollback()
            flash('Error adding comic. Please try again.', 'danger')
    
    return render_template('comics/form.html', title='Add Comic', form=form)

@comics_bp.route('/comics/<int:id>')
@login_required
def show(id):
    """Display a specific comic."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    return render_template('comics/show.html', title=comic.title, comic=comic)

@comics_bp.route('/comics/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit an existing comic."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    form = ComicForm(obj=comic)
    
    if form.validate_on_submit():
        comic.title = form.title.data
        comic.issue_number = form.issue_number.data
        comic.publisher = form.publisher.data
        comic.characters = form.characters.data
        comic.genre = form.genre.data
        comic.release_date = form.release_date.data
        comic.upc = form.upc.data
        comic.isbn = form.isbn.data
        comic.condition = form.condition.data
        comic.estimated_value = form.estimated_value.data or 0.0
        comic.notes = form.notes.data
        comic.is_wishlist = form.is_wishlist.data
        
        # Handle cover image upload or fetched cover
        fetched_cover = request.form.get('fetched_cover')
        if fetched_cover:
            # Delete old image and thumbnail if exists
            if comic.cover_image:
                old_file = os.path.join(current_app.config['UPLOAD_FOLDER'], comic.cover_image)
                if os.path.exists(old_file):
                    os.remove(old_file)
                
                old_thumb = os.path.join(current_app.config['UPLOAD_FOLDER'], f"thumb_{comic.cover_image}")
                if os.path.exists(old_thumb):
                    os.remove(old_thumb)
            comic.cover_image = fetched_cover
        elif form.cover_image.data:
            filename = save_cover_image(form.cover_image.data)
            if filename:
                # Delete old image and thumbnail if exists
                if comic.cover_image:
                    old_file = os.path.join(current_app.config['UPLOAD_FOLDER'], comic.cover_image)
                    if os.path.exists(old_file):
                        os.remove(old_file)
                    
                    old_thumb = os.path.join(current_app.config['UPLOAD_FOLDER'], f"thumb_{comic.cover_image}")
                    if os.path.exists(old_thumb):
                        os.remove(old_thumb)
                comic.cover_image = filename
        
        try:
            db.session.commit()
            flash('Comic updated successfully!', 'success')
            return redirect(url_for('comics.show', id=comic.id))
        except Exception as e:
            db.session.rollback()
            flash('Error updating comic. Please try again.', 'danger')
    
    return render_template('comics/form.html', title='Edit Comic', form=form, comic=comic)

@comics_bp.route('/comics/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Delete a comic from the collection."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    
    try:
        # Delete cover image and thumbnail if exists
        if comic.cover_image:
            # Delete original image
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], comic.cover_image)
            if os.path.exists(file_path):
                os.remove(file_path)
            
            # Delete thumbnail
            thumb_path = os.path.join(current_app.config['UPLOAD_FOLDER'], f"thumb_{comic.cover_image}")
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
        
        db.session.delete(comic)
        db.session.commit()
        flash('Comic deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting comic. Please try again.', 'danger')
    
    return redirect(url_for('comics.index'))

@comics_bp.route('/comics/export')
@login_required
def export():
    """Export collection to CSV."""
    import csv
    from io import StringIO
    
    comics = Comic.query.filter_by(user_id=current_user.id, is_wishlist=False).all()
    
    si = StringIO()
    cw = csv.writer(si)
    
    # Write header
    cw.writerow(['Title', 'Issue Number', 'Publisher', 'Characters', 'Genre', 
                 'Release Date', 'Condition', 'Estimated Value', 'Notes'])
    
    # Write data
    for comic in comics:
        cw.writerow([
            comic.title,
            comic.issue_number,
            comic.publisher,
            comic.characters or '',
            comic.genre or '',
            comic.release_date.strftime('%Y-%m-%d') if comic.release_date else '',
            comic.condition or '',
            comic.estimated_value or 0.0,
            comic.notes or ''
        ])
    
    output = si.getvalue()
    si.close()
    
    return send_file(
        StringIO(output),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'comic_collection_{datetime.now().strftime("%Y%m%d")}.csv'
    )

@comics_bp.route('/comics/wishlist')
@login_required
def wishlist():
    """Display wishlist items."""
    page = request.args.get('page', 1, type=int)
    wishlist_comics = Comic.query.filter_by(
        user_id=current_user.id, is_wishlist=True
    ).order_by(Comic.title, Comic.issue_number).paginate(
        page=page, per_page=12, error_out=False
    )
    
    return render_template('comics/wishlist.html',
                         title='Wishlist',
                         comics=wishlist_comics)

@comics_bp.route('/comics/search-api')
@login_required
def search_api():
    """Search for comics via external API."""
    query = request.args.get('q', '')
    search_comicvine = request.args.get('comicvine', '1') == '1'
    search_marvel = request.args.get('marvel', '0') == '1'
    search_gcd = request.args.get('gcd', '0') == '1'
    search_upc_database = request.args.get('upc_database', '0') == '1'
    search_barcode_lookup = request.args.get('barcode_lookup', '0') == '1'
    search_local = request.args.get('local', '1') == '1'
    
    print(f"🔍 Search API called with query: '{query}'")
    print(f"🔍 Search sources: ComicVine={search_comicvine}, Marvel={search_marvel}, GCD={search_gcd}, UPC Database={search_upc_database}, Barcode Lookup={search_barcode_lookup}, Local={search_local}")
    
    if not query:
        print("❌ No search query provided")
        return jsonify({'error': 'No search query provided'}), 400
    
    try:
        # ComicVine API search
        api_key = current_app.config.get('COMICVINE_API_KEY', '')
        print(f"🔑 API Key configured: {'Yes' if api_key else 'No'}")
        print(f"🔑 API Key length: {len(api_key) if api_key else 0}")
        print(f"🔑 API Key preview: {api_key[:10] if api_key else 'None'}...")
        
        # Check if API key looks valid (ComicVine keys are typically 40+ characters)
        if not api_key or len(api_key) < 20:
            print("⚠️ API key appears invalid or too short, returning enhanced mock data")
            print("📝 ComicVine API keys are typically 40+ characters long")
            
            # Enhanced mock data based on search query
            query_lower = query.lower()
            mock_results = []
            
            if 'iron' in query_lower and 'man' in query_lower:
                mock_results = [
                    {
                        'id': 1,
                        'title': 'Invincible Iron Man',
                        'issue_number': '1',
                        'publisher': 'Marvel Comics',
                        'characters': 'Iron Man, Tony Stark, Pepper Potts',
                        'genre': 'Superhero',
                        'release_date': '2008-05-07',
                        'description': 'The beginning of the Invincible Iron Man series',
                        'cover_image_url': '',
                        'volume': 'Volume 1',
                        'upc': '75960607800100111',
                        'isbn': ''
                    },
                    {
                        'id': 2,
                        'title': 'Iron Man',
                        'issue_number': '1',
                        'publisher': 'Marvel Comics',
                        'characters': 'Iron Man, Tony Stark',
                        'genre': 'Superhero',
                        'release_date': '1968-05-01',
                        'description': 'The first appearance of Iron Man',
                        'cover_image_url': '',
                        'volume': 'Volume 1',
                        'upc': '75960607800100112',
                        'isbn': ''
                    },
                    {
                        'id': 3,
                        'title': 'Iron Man 2.0',
                        'issue_number': '1',
                        'publisher': 'Marvel Comics',
                        'characters': 'Iron Man, James Rhodes',
                        'genre': 'Superhero',
                        'release_date': '2011-01-26',
                        'description': 'James Rhodes takes on the Iron Man mantle',
                        'cover_image_url': '',
                        'volume': 'Volume 1',
                        'upc': '75960607800100113',
                        'isbn': ''
                    }
                ]
            elif 'spider' in query_lower:
                mock_results = [
                    {
                        'id': 4,
                        'title': 'Amazing Spider-Man',
                        'issue_number': '1',
                        'publisher': 'Marvel Comics',
                        'characters': 'Spider-Man, Peter Parker, Uncle Ben',
                        'genre': 'Superhero',
                        'release_date': '1963-03-01',
                        'description': 'The first appearance of Spider-Man',
                        'cover_image_url': '',
                        'volume': 'Volume 1',
                        'upc': '75960607800100114',
                        'isbn': ''
                    },
                    {
                        'id': 5,
                        'title': 'Ultimate Spider-Man',
                        'issue_number': '1',
                        'publisher': 'Marvel Comics',
                        'characters': 'Spider-Man, Peter Parker, Mary Jane',
                        'genre': 'Superhero',
                        'release_date': '2000-10-03',
                        'description': 'The Ultimate Universe version of Spider-Man',
                        'cover_image_url': '',
                        'volume': 'Volume 1',
                        'upc': '75960607800100115',
                        'isbn': ''
                    }
                ]
            elif 'batman' in query_lower:
                mock_results = [
                    {
                        'id': 6,
                        'title': 'Batman',
                        'issue_number': '1',
                        'publisher': 'DC Comics',
                        'characters': 'Batman, Bruce Wayne, Commissioner Gordon',
                        'genre': 'Superhero',
                        'release_date': '1940-03-01',
                        'description': 'The first appearance of Batman',
                        'cover_image_url': '',
                        'volume': 'Volume 1',
                        'upc': '76194126700100116',
                        'isbn': ''
                    },
                    {
                        'id': 7,
                        'title': 'Batman: The Dark Knight Returns',
                        'issue_number': '1',
                        'publisher': 'DC Comics',
                        'characters': 'Batman, Bruce Wayne',
                        'genre': 'Superhero',
                        'release_date': '1986-02-01',
                        'description': 'Frank Miller\'s iconic Batman story',
                        'cover_image_url': '',
                        'volume': 'Volume 1',
                        'upc': '76194126700100117',
                        'isbn': ''
                    }
                ]
            else:
                # Generic results for other searches
                mock_results = [
                    {
                        'id': 8,
                        'title': f'Search Results for "{query}"',
                        'issue_number': '1',
                        'publisher': 'Various Publishers',
                        'characters': 'Various Characters',
                        'genre': 'Various Genres',
                        'release_date': '2023-01-01',
                        'description': f'Search results for "{query}" - API key may need to be updated',
                        'cover_image_url': '',
                        'volume': 'Volume 1',
                        'upc': '123456789012',
                        'isbn': ''
                    }
                ]
            
            print(f"📚 Returning {len(mock_results)} mock results for query: '{query}'")
            return jsonify({'results': mock_results, 'source': 'mock_data'})
        
        # Multi-API search system based on user selection
        all_results = []
        
        # 1. ComicVine API (if selected)
        if search_comicvine:
            print("🔍 Searching ComicVine API...")
            comicvine_results = search_comicvine_api(query, api_key)
            all_results.extend(comicvine_results)
            print(f"📚 ComicVine found: {len(comicvine_results)} results")
        else:
            print("⏭️ Skipping ComicVine search (not selected)")
        
        # 2. Marvel API (if selected and configured)
        if search_marvel:
            marvel_api_key = current_app.config.get('MARVEL_API_KEY', '')
            marvel_private_key = current_app.config.get('MARVEL_PRIVATE_KEY', '')
            print(f"🔑 Marvel API Key configured: {'Yes' if marvel_api_key else 'No'}")
            print(f"🔑 Marvel Private Key configured: {'Yes' if marvel_private_key else 'No'}")
            if marvel_api_key and marvel_private_key:
                print("🔍 Searching Marvel API...")
                marvel_results = search_marvel_api(query, marvel_api_key, marvel_private_key)
                all_results.extend(marvel_results)
                print(f"📚 Marvel found: {len(marvel_results)} results")
            else:
                print("⚠️ Marvel API keys not configured, skipping Marvel search")
        else:
            print("⏭️ Skipping Marvel search (not selected)")
        
        # 3. Open Library API (if selected) - Has ISBN barcode information
        if search_gcd:
            print("🔍 Searching Open Library API...")
            openlibrary_results = search_openlibrary_api(query)
            all_results.extend(openlibrary_results)
            print(f"📚 Open Library found: {len(openlibrary_results)} results")
        else:
            print("⏭️ Skipping Open Library search (not selected)")
        
        # 4. UPC Database API (if selected and query looks like UPC code)
        is_upc_query = len(''.join(filter(str.isdigit, query))) >= 10
        if search_upc_database and is_upc_query:
            upc_database_key = current_app.config.get('UPC_DATABASE_API_KEY', '')
            if upc_database_key:
                print("🔍 Searching UPC Database API...")
                upc_results = search_upc_database_api(query, upc_database_key)
                all_results.extend(upc_results)
                print(f"📚 UPC Database found: {len(upc_results)} results")
            else:
                print("⚠️ UPC Database API key not configured")
        elif search_upc_database and not is_upc_query:
            print("⏭️ Skipping UPC Database search (query doesn't look like UPC code)")
        else:
            print("⏭️ Skipping UPC Database search (not selected)")
        
        # 5. Barcode Lookup API (if selected and query looks like UPC code)
        if search_barcode_lookup and is_upc_query:
            barcode_lookup_key = current_app.config.get('BARCODE_LOOKUP_API_KEY', '')
            if barcode_lookup_key:
                print("🔍 Searching Barcode Lookup API...")
                barcode_results = search_barcode_lookup_api(query, barcode_lookup_key)
                all_results.extend(barcode_results)
                print(f"📚 Barcode Lookup found: {len(barcode_results)} results")
            else:
                print("⚠️ Barcode Lookup API key not configured")
        elif search_barcode_lookup and not is_upc_query:
            print("⏭️ Skipping Barcode Lookup search (query doesn't look like UPC code)")
        else:
            print("⏭️ Skipping Barcode Lookup search (not selected)")
        
        # 6. Local database search (if selected)
        if search_local:
            print("🔍 Searching local database...")
            local_results = search_local_database(query)
            all_results.extend(local_results)
            print(f"📚 Local found: {len(local_results)} results")
        else:
            print("⏭️ Skipping local search (not selected)")
        
        # Remove duplicates based on title and issue number
        unique_results = []
        seen_titles = set()
        for result in all_results:
            title_key = f"{result.get('title', '')}_{result.get('issue_number', '')}"
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_results.append(result)
        
        print(f"📚 Total unique results: {len(unique_results)}")
        
        # Process the results for JSON response
        results = []
        for issue in unique_results:
            result = {
                'id': issue.get('id'),
                'title': issue.get('title', issue.get('name', '')),
                'issue_number': issue.get('issue_number', ''),
                'publisher': issue.get('publisher', ''),
                'characters': issue.get('characters', ''),
                'genre': issue.get('genre', 'Superhero'),
                'release_date': issue.get('release_date', ''),
                'description': issue.get('description', ''),
                'cover_image_url': issue.get('cover_image_url', ''),
                'volume': issue.get('volume', ''),
                'upc': issue.get('upc', ''),
                'isbn': issue.get('isbn', ''),
                'source': issue.get('source', 'Unknown')
            }
            results.append(result)
            
            # Log barcode information
            barcode_info = []
            if result['upc']:
                barcode_info.append(f"UPC: {result['upc']}")
            if result['isbn']:
                barcode_info.append(f"ISBN: {result['isbn']}")
            barcode_text = ' | '.join(barcode_info) if barcode_info else 'No barcode'
            print(f"📖 Processed result: {result['title']} #{result['issue_number']} ({barcode_text})")
        
        print(f"✅ Returning {len(results)} results")
        return jsonify({'results': results})
        
    except requests.RequestException as e:
        print(f"❌ API request failed: {e}")
        print(f"🔍 Request details: {e.request.url if hasattr(e, 'request') else 'No request info'}")
        # Fallback to local search if API fails
        try:
            print("🔄 Falling back to local search...")
            local_results = Comic.query.filter(
                db.or_(
                    Comic.title.ilike(f'%{query}%'),
                    Comic.characters.ilike(f'%{query}%'),
                    Comic.publisher.ilike(f'%{query}%')
                )
            ).limit(5).all()
            
            results = []
            for comic in local_results:
                result = {
                    'id': comic.id,
                    'title': comic.title,
                    'issue_number': comic.issue_number,
                    'publisher': comic.publisher,
                    'characters': comic.characters,
                    'genre': comic.genre,
                    'release_date': comic.release_date.strftime('%Y-%m-%d') if comic.release_date else '',
                    'description': comic.notes,
                    'cover_image_url': '',
                    'volume': '',
                    'upc': comic.upc or '',
                    'isbn': comic.isbn or '',
                    'source': 'Local Database'
                }
                results.append(result)
            
            print(f"📚 Local search found {len(results)} results")
            return jsonify({'results': results, 'source': 'local'})
        except Exception as local_error:
            print(f"❌ Local search also failed: {local_error}")
            return jsonify({'error': f'Search failed: {str(e)}'}), 500
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return jsonify({'error': f'Search failed: {str(e)}'}), 500

@comics_bp.route('/comics/fetch-cover')
@login_required
def fetch_cover():
    """Fetch cover image from URL and save it."""
    image_url = request.args.get('url', '')
    if not image_url:
        return jsonify({'error': 'No image URL provided'}), 400
    
    try:
        headers = {
            'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x'
        }
        response = requests.get(image_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_api_cover.jpg"
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        
        # Ensure upload directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Save the image
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        # Create thumbnail
        try:
            with Image.open(filepath) as img:
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                
                # Calculate new size maintaining aspect ratio
                width, height = img.size
                max_size = (300, 300)
                scale = min(max_size[0] / width, max_size[1] / height)
                new_size = (int(width * scale), int(height * scale))
                
                # Resize image
                img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Create a white background of the target size
                thumb = Image.new('RGB', max_size, (255, 255, 255))
                
                # Calculate position to center the image
                x = (max_size[0] - new_size[0]) // 2
                y = (max_size[1] - new_size[1]) // 2
                
                # Paste the resized image onto the background
                thumb.paste(img_resized, (x, y))
                
                thumb_filename = f"thumb_{filename}"
                thumb_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], thumb_filename)
                thumb.save(thumb_filepath, 'JPEG', quality=85)
        except Exception as e:
            print(f"Error creating thumbnail: {e}")
        
        return jsonify({'filename': filename})
        
    except requests.RequestException as e:
        return jsonify({'error': f'Failed to fetch image: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': f'Failed to save image: {str(e)}'}), 500

@comics_bp.route('/comics/test-search')
def test_search():
    """Test route to verify search functionality."""
    api_key = current_app.config.get('COMICVINE_API_KEY', '')
    return jsonify({
        'status': 'Search API is working',
        'api_key_configured': bool(api_key),
        'api_key_length': len(api_key) if api_key else 0,
        'api_key_preview': api_key[:10] + '...' if api_key else 'None',
        'message': 'Try searching for "Spider-Man" or "Batman"',
        'env_file_exists': 'Check if .env file exists in project root'
    })

@comics_bp.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded cover images."""
    from flask import send_from_directory
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)
