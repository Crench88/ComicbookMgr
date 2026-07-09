"""
WTForms for Comic Book Collection Manager.
Defines forms for user authentication and comic book management.
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, SelectField, FloatField, DateField, BooleanField, HiddenField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError, Optional

# Import db and User with error handling
try:
    from . import db
    from .models import User
except ImportError:
    # For testing purposes
    db = None
    User = None

class LoginForm(FlaskForm):
    """Form for user login."""
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class RegistrationForm(FlaskForm):
    """Form for user registration."""
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')
    
    def validate_username(self, username):
        """Check if username is already taken."""
        if User and db:
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError('Username already taken. Please choose a different one.')
    
    def validate_email(self, email):
        """Check if email is already registered."""
        if User and db:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('Email already registered. Please use a different one.')

class ForgotPasswordForm(FlaskForm):
    """Form for requesting password reset."""
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Send Reset Link')
    
    def validate_email(self, email):
        """Check if email exists in the system."""
        if User and db:
            user = User.query.filter_by(email=email.data).first()
            if not user:
                raise ValidationError('No account found with that email address.')

class ResetPasswordForm(FlaskForm):
    """Form for resetting password with token."""
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Reset Password')

class ChangePasswordForm(FlaskForm):
    """Form for changing password when logged in."""
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_new_password = PasswordField('Confirm New Password', validators=[DataRequired(), EqualTo('new_password')])
    submit = SubmitField('Change Password')

class ComicForm(FlaskForm):
    """Form for adding/editing comic books."""
    title = StringField('Title', validators=[Optional(), Length(max=200)], 
                       description='Individual issue title (e.g., "Worldwide")')
    series = StringField('Series', validators=[DataRequired(), Length(max=200)], 
                        description='Series name (e.g., "The Amazing Spider-Man")')
    issue_number = StringField('Issue Number', validators=[DataRequired(), Length(max=20)])
    publisher = StringField('Publisher', validators=[DataRequired(), Length(max=100)])
    characters = TextAreaField('Characters (comma-separated)', validators=[Optional(), Length(max=2000)])
    writer = TextAreaField('Writer(s)', validators=[Optional(), Length(max=1000)])
    artist = TextAreaField('Artist(s)', validators=[Optional(), Length(max=1000)])
    colorist = StringField('Colorist(s)', validators=[Optional(), Length(max=500)])
    letterer = StringField('Letterer(s)', validators=[Optional(), Length(max=500)])
    editor = StringField('Editor(s)', validators=[Optional(), Length(max=500)])
    cover_artist = StringField('Cover Artist(s)', validators=[Optional(), Length(max=500)])
    teams = TextAreaField('Teams', validators=[Optional(), Length(max=1000)])
    story_arc = StringField('Story Arc', validators=[Optional(), Length(max=500)])
    description = TextAreaField('Description / Synopsis', validators=[Optional(), Length(max=5000)])
    comicvine_issue_id = HiddenField(validators=[Optional()])
    genre = StringField('Genre', validators=[Optional(), Length(max=100)])
    release_date = DateField('Release Date', validators=[Optional()], format='%Y-%m-%d')
    upc = StringField('UPC Code', validators=[Optional(), Length(max=20)], 
                     description='12-digit Universal Product Code (e.g., 123456789012)')
    isbn = StringField('ISBN Code', validators=[Optional(), Length(max=20)], 
                      description='13-digit International Standard Book Number (e.g., 978-0-7475-3269-9)')
    condition = SelectField('Condition', choices=[
        ('', 'Select Condition'),
        ('Mint', 'Mint'),
        ('Near Mint', 'Near Mint'),
        ('Very Fine', 'Very Fine'),
        ('Fine', 'Fine'),
        ('Very Good', 'Very Good'),
        ('Good', 'Good'),
        ('Fair', 'Fair'),
        ('Poor', 'Poor')
    ], validators=[Optional()])
    estimated_value = FloatField('Estimated Value ($)', validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional(), Length(max=1000)])
    cover_image = FileField('Cover Image', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')
    ])
    is_wishlist = BooleanField('Add to Wishlist')
    submit = SubmitField('Save Comic')


class SeriesForm(FlaskForm):
    """Form for maintaining canonical comic series information."""
    name = StringField('Series Name', validators=[DataRequired(), Length(max=200)])
    volume = StringField('Volume', validators=[Optional(), Length(max=50)],
                         description='Volume identifier (e.g., 1, 2, 2015).')
    publisher = StringField('Publisher', validators=[Optional(), Length(max=100)])
    date_range = StringField('Date Range', validators=[Optional(), Length(max=200)],
                             description='e.g., March 1963 – September 1996')
    notes = TextAreaField('Notes', validators=[Optional(), Length(max=1000)])
    submit = SubmitField('Save Series')

class SearchForm(FlaskForm):
    """Form for searching comics."""
    search_query = StringField('Search', validators=[Optional(), Length(max=100)])
    publisher_filter = SelectField('Publisher', choices=[('', 'All Publishers')], validators=[Optional()])
    condition_filter = SelectField('Condition', choices=[
        ('', 'All Conditions'),
        ('Mint', 'Mint'),
        ('Near Mint', 'Near Mint'),
        ('Very Fine', 'Very Fine'),
        ('Fine', 'Fine'),
        ('Very Good', 'Very Good'),
        ('Good', 'Good'),
        ('Fair', 'Fair'),
        ('Poor', 'Poor')
    ], validators=[Optional()])
    genre_filter = StringField('Genre', validators=[Optional(), Length(max=100)])
    wishlist_only = BooleanField('Wishlist Only')
    submit = SubmitField('Search')


class SeriesIssueForm(FlaskForm):
    """Form for manually adding a canonical issue to a series."""
    series_id = SelectField('Series', coerce=int, validators=[DataRequired()])
    issue_number = StringField('Issue Number', validators=[DataRequired(), Length(max=50)])
    title = StringField('Title', validators=[Optional(), Length(max=255)])
    cover_date = StringField('Cover Date', validators=[Optional(), Length(max=100)])
    featured_characters = TextAreaField('Featured Characters', validators=[Optional()])
    writer = StringField('Writer', validators=[Optional(), Length(max=200)])
    artist = StringField('Artist', validators=[Optional(), Length(max=200)])
    story_arc = StringField('Story Arc', validators=[Optional(), Length(max=200)])
    submit_add = SubmitField('Add Issue')


class SeriesIssueUploadForm(FlaskForm):
    """Form for uploading canonical issues via CSV."""
    series_id = SelectField('Series', coerce=int, validators=[DataRequired()])
    file = FileField('CSV File', validators=[DataRequired(), FileAllowed(['csv'], 'CSV files only')])
    submit_upload = SubmitField('Upload CSV')
