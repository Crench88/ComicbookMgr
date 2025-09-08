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
├── app.py                 # Main Flask application factory
├── models.py              # Database models (User, Comic)
├── forms.py               # WTForms for user input
├── auth.py                # Authentication blueprint
├── main.py                # Main routes blueprint
├── dashboard.py           # Dashboard blueprint
├── comics.py              # Comics management blueprint
├── app.py                 # Application entry point
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── templates/            # HTML templates
│   ├── base.html         # Base template with navigation
│   ├── main/             # Main page templates
│   ├── auth/             # Authentication templates
│   ├── dashboard/        # Dashboard templates
│   └── comics/           # Comics management templates
├── static/               # Static files
│   ├── css/              # Custom CSS styles
│   ├── js/               # JavaScript functionality
│   └── uploads/          # Uploaded images (created automatically)
├── tests/                # Unit tests
│   └── test_app.py       # Test cases
└── instance/             # Instance-specific files (created automatically)
    ├── comicbook.db      # SQLite database
    └── uploads/          # Uploaded files
```

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
