#!/usr/bin/env python3
"""
Clear all stories from the database (for testing).
This allows re-generation of stories to test performance improvements.
"""

import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import session_scope
from sqlalchemy import text

def clear_all_stories():
    """Delete all stories and story_articles from database."""
    with session_scope() as session:
        # Get count before deletion
        story_count = session.execute(text("SELECT COUNT(*) FROM stories")).scalar()
        article_links_count = session.execute(text("SELECT COUNT(*) FROM story_articles")).scalar()

        print(f"Found {story_count} stories and {article_links_count} article links")

        if story_count == 0:
            print("No stories to delete")
            return

        # Confirm
        response = input(f"Delete all {story_count} stories? (yes/no): ")
        if response.lower() != 'yes':
            print("Cancelled")
            return

        # Delete (CASCADE will handle story_articles)
        session.execute(text("DELETE FROM stories"))
        session.commit()

        print(f"✅ Deleted {story_count} stories")
        print("You can now generate fresh stories to test performance")

if __name__ == "__main__":
    clear_all_stories()
