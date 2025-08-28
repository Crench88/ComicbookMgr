"""
Migration script to add additional_covers field to Comic table.
Run this script to update your database schema.
"""

import os
import sys
from sqlalchemy import create_engine, text

# Add the parent directory to the path so we can import the app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Comic

def run_migration():
    """Run the migration to add additional_covers field."""
    app = create_app()
    
    with app.app_context():
        try:
            # For SQLite, we'll try to add the column and catch the error if it already exists
            try:
                # Add the new column
                db.session.execute(text("""
                    ALTER TABLE comic 
                    ADD COLUMN additional_covers TEXT
                """))
                
                db.session.commit()
                print("✅ Successfully added 'additional_covers' column to Comic table.")
                
            except Exception as column_error:
                if "duplicate column name" in str(column_error).lower() or "already exists" in str(column_error).lower():
                    print("✅ Column 'additional_covers' already exists. Migration not needed.")
                else:
                    raise column_error
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error during migration: {e}")
            raise

if __name__ == '__main__':
    run_migration()
