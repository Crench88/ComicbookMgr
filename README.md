# Comic Book Collection Manager

A comprehensive web application for managing personal comic book collections, built with Python, Flask, and Bootstrap 5.

## Features

### 🔐 User Authentication
- Secure user registration and login
- Session management with Flask-Login
- Password hashing and validation

### 📚 Comic Book Management
- **CRUD Operations**: Add, edit, delete, and view comic entries
- **Comprehensive Data**: Track title, issue number, publisher, characters, genre, release date, condition, estimated value, and notes
- **Cover Images**: Upload and store comic cover images
- **Wishlist**: Separate tracking for comics you want to collect

### 🔍 Search & Filter
- Search by title, publisher, character, or genre
- Filter by condition, publisher, or genre
- Wishlist-only filtering
- Real-time search with debouncing

### 📊 Dashboard & Analytics
- Collection statistics (total comics, estimated value)
- Top publishers and most frequent characters
- Recent additions
- Condition distribution
- Quick action buttons

### 📱 Responsive Design
- Mobile-friendly Bootstrap 5 interface
- Responsive grid layouts
- Touch-friendly navigation
- Optimized for all device sizes

### 📤 Export Functionality
- Export collection to CSV format
- Backup and analysis capabilities
- Formatted data export

## Tech Stack

- **Backend**: Python 3.x, Flask 2.3.3
- **Frontend**: HTML5, CSS3, Bootstrap 5.3.0
- **Database**: SQLite (easily upgradeable to PostgreSQL)
- **Authentication**: Flask-Login
- **Forms**: Flask-WTF with WTForms
- **Testing**: pytest
- **Deployment**: Ready for Heroku/Render

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package installer)

### Setup Instructions

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd ComicbookMgr
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   
   # On Windows
   venv\Scripts\activate
   
   # On macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   # Create a .env file
   echo "SECRET_KEY=your-secret-key-here" > .env
   echo "DATABASE_URL=sqlite:///comicbook.db" >> .env
   ```

5. **Initialize the database**
   ```bash
   python app.py
   ```
   The database will be automatically created on first run.

6. **Run the application**
   ```bash
   python app.py
   ```

7. **Access the application**
   Open your browser and navigate to `http://localhost:5000`

## Usage

### Getting Started
1. **Register an account** or **login** if you already have one
2. **Add your first comic** using the "Add Comic" button
3. **Explore the dashboard** to see your collection statistics
4. **Use search and filters** to find specific comics
5. **Export your data** for backup or analysis

### Adding Comics
- Fill in the required fields (title, issue number, publisher)
- Add optional details like characters, genre, condition, and estimated value
- Upload a cover image (optional)
- Mark as wishlist item if desired
- Add personal notes

### Managing Your Collection
- **View all comics** in a responsive grid layout
- **Search and filter** to find specific items
- **Edit comics** to update information
- **Delete comics** with confirmation dialogs
- **Export data** for backup purposes

## Project Structure

```
ComicbookMgr/
├── app.py                 # Application entry point
├── app/                   # Application package
│   ├── __init__.py        # Flask app factory
│   ├── models.py          # Database models
│   ├── forms.py           # WTForms
│   ├── auth.py / main.py / dashboard.py / admin.py
│   ├── comics/            # Comics blueprint package
│   ├── reader/            # CBZ digital reader blueprint
│   ├── services/          # ComicVine, barcode, covers, archives, etc.
│   │   └── pricing/       # eBay comparables, grade curve, statistics
│   ├── templates/         # comics/, reader/, admin/, ...
│   └── static/            # CSS / JS
├── requirements.txt
├── tests/
└── instance/              # SQLite DB, covers/, digital/, cache
```


### Creator credits from ComicVine
ComicVine returns every role a person held on an issue as one comma-joined string
(`"penciler, inker, cover"`), so credits are matched per role and a person is listed
under each one they held. The stored credits are writer, artist, penciler, inker,
colorist, letterer, cover artist, editor, assistant editor, designer, production,
translator, and other.

`Artist` holds only ComicVine's literal `artist` credit; pencilers and inkers have
their own fields. Roles ComicVine leaves unlabelled (its own `other`) and any role
not yet mapped land in **Other** rather than being discarded, so no credit is lost
when ComicVine adds a role.

### Value estimates from eBay Canada
The value lookup button on the comic form prices an issue against **live eBay
listings**, defaulting to eBay Canada (`EBAY_CA`) so amounts come back in CAD.

```bash
# https://developer.ebay.com/my/keys -> production App ID + Cert ID
EBAY_CLIENT_ID=your-app-id
EBAY_CLIENT_SECRET=your-cert-id
EBAY_MARKETPLACE_ID=EBAY_CA      # EBAY_US, EBAY_GB, EBAY_AU also supported
PRICE_ASK_TO_SOLD_RATIO=0.8
```

The keys use the client-credentials grant, so no eBay user login or consent
screen is involved. Without keys the button still works and falls back to a
labelled offline estimate.

How a number is produced:

1. Search active fixed-price listings for `series #issue`, restricted to items
   that can be delivered to the marketplace's country.
2. Throw out anything that is not a comparable copy: multi-issue lots, posters
   and figures, facsimiles and reprints, signed or remarked copies, collected
   editions, the wrong series, and the wrong issue number.
3. Split graded slabs (CGC/CBCS) from raw copies. A slab price says nothing
   about a raw copy, so slabs never feed a raw estimate — they are shown
   separately for context.
4. Read each listing's grade from its title (`CGC 9.8`, `VF/NM`, `Near Mint`)
   and restate its price at *your* comic's condition using a grade curve.
   Listings that state no grade are assumed Very Fine (8.0).
5. Prefer copies graded within two points of your condition, because restating a
   beaten-up copy five grades higher produces nonsense. Copies further away are
   used only when too few close ones exist, and then confidence drops a level.
6. Discard outliers beyond the interquartile fences, then take the median.
7. Multiply by `PRICE_ASK_TO_SOLD_RATIO` (default 0.8), because asking prices
   sit above real sale prices.

The result is a range rather than a single number, and it always reports its
sample size, its confidence, and the exact listings behind it so you can judge
whether to trust it. Searches and access tokens are cached (six hours and token
lifetime respectively) to stay well inside eBay's free call limits.

Caveat worth knowing: the Browse API only exposes **active** listings, not
completed sales. Asking prices are the best free proxy, which is why the
estimate is discounted and labelled as such.

### Cover barcode scanning (optional)
Cover UPC/EAN scanning uses OpenCV and pyzbar, with an OCR fallback for soft
ComicVine art where the bars themselves will not decode:

```bash
pip install opencv-python-headless pyzbar rapidocr-onnxruntime
```

On Windows, pyzbar also needs the ZBar shared library. If scans fail with a DLL error:
1. Install ZBar for Windows, or copy libzbar-64.dll into a directory on your PATH
2. Restart the app

The scanner tries rotations (comic UPCs are often printed vertically), crops the
trade-dress strip, and if the bars still fail it reads the printed digits and
rebuilds a valid UPC-A code. The **Scan from Cover** button appears on comic
detail/edit pages when a cover image exists.

### Cover image storage
New and updated covers are written under `instance/covers/{user_id}/{comic_id}/` and served from disk. Legacy SQLite BLOBs still work (dual-read). After upgrading, extract existing BLOBs once:

```bash
python scripts/migrate_covers_to_filesystem.py
# Optional: also clear BLOBs after a successful extract
python scripts/migrate_covers_to_filesystem.py --clear-blobs
```

`COVERS_FOLDER` and `COVERS_KEEP_BLOB` can override the defaults via environment variables.

After filesystem covers are trusted (the migrate script has run and thumbnails load from `/comics/<id>/cover` and `/covers/<cover_id>/image`), set `COVERS_KEEP_BLOB=false` so new writes skip the SQLite BLOB. Dual-read stays in place for any leftover legacy rows. Templates serve variants by URL — do not embed Base64 cover bytes in HTML.

### Digital comic reader (CBZ / CBR)
Attach a `.cbz` or `.cbr` on a comic’s detail page, then open **Read**.

- Archives are stored under `instance/digital/{user_id}/{comic_id}/`
- Pages are extracted on demand, then cached; reading keys are ← → / A D, `S` toggles two-page spread, `Esc` exits
- Last page is remembered per user (`ReadingProgress`). The dashboard shows **Continue Reading**, **Up Next** (next unfinished digital issue in the same series), and **Unread Digital** files you have not started
- Override storage with `DIGITAL_FOLDER`; upload size still respects `MAX_CONTENT_LENGTH` (default 64 MB)

#### CBR support
CBR needs `rarfile` plus an external extraction tool, because RAR decompression is not in the standard library:

```bash
pip install rarfile
```

Then install `unrar` (or `bsdtar` / `7z`) and make sure it is on `PATH`. On Windows the bundled `tar.exe` does **not** count — rarfile looks for a binary literally named `unrar`, `bsdtar`, or `7z`. When no tool is found, CBZ keeps working and the comic page explains what is missing instead of failing at upload time.

#### Reader page cache
Extracted pages go into a size-capped LRU cache (`diskcache`) so repeat views skip decompression entirely:

- `READER_CACHE_DIR` — defaults to `instance/reader_cache/`
- `READER_CACHE_SIZE_LIMIT` — bytes, defaults to 512 MB; least-recently-used pages are evicted first

The cache is keyed by archive content hash, so replacing or removing a file drops its pages automatically. Responses carry an `ETag` for browser-side 304s and an `X-Page-Cache: hit|miss` header that is handy when debugging.

## Testing

Run the test suite to ensure everything is working correctly:

```bash
# Install pytest if not already installed
pip install pytest

# Run all tests
pytest

# Run tests with verbose output
pytest -v

# Run specific test file
pytest tests/test_app.py
```

## Deployment

### Heroku Deployment
1. Create a `Procfile`:
   ```
   web: gunicorn run:app
   ```

2. Set environment variables in Heroku:
   ```bash
   heroku config:set SECRET_KEY=your-secret-key
   heroku config:set DATABASE_URL=postgresql://...
   ```

3. Deploy:
   ```bash
   git push heroku main
   ```

### Render Deployment
1. Connect your repository to Render
2. Set build command: `pip install -r requirements.txt`
3. Set start command: `gunicorn run:app`
4. Configure environment variables

## Configuration

### Environment Variables
- `SECRET_KEY`: Flask secret key for session management
- `DATABASE_URL`: Database connection string
- `UPLOAD_FOLDER`: Path for uploaded files (default: instance/uploads)

### Database Configuration
The application uses SQLite by default but can be easily configured for PostgreSQL:

```python
# In app.py, change the DATABASE_URL
SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'postgresql://user:pass@localhost/comicbook')
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

If you encounter any issues or have questions:

1. Check the [Issues](https://github.com/yourusername/ComicbookMgr/issues) page
2. Create a new issue with detailed information
3. Include steps to reproduce the problem

## Roadmap

### Planned Features
- [ ] Dark mode toggle
- [ ] Advanced analytics and charts
- [ ] Comic price tracking over time
- [ ] Integration with comic price APIs
- [ ] Mobile app companion
- [ ] Social features (sharing collections)
- [ ] Backup and restore functionality
- [ ] Multiple image uploads per comic
- [ ] Comic grading system integration
- [ ] Reading list management

### Technical Improvements
- [ ] API endpoints for mobile app
- [ ] Caching for better performance
- [ ] Background task processing
- [ ] Email notifications
- [ ] Advanced search with Elasticsearch
- [ ] Image optimization and CDN integration

## Acknowledgments

- Flask community for the excellent web framework
- Bootstrap team for the responsive CSS framework
- SQLAlchemy for the powerful ORM
- All contributors and users of this project

---

**Happy collecting! 🦸‍♂️📚**
