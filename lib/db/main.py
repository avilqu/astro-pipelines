import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from .models import Base, FitsFile, Source

class DatabaseManager:
    """Manages database connections and operations for astro-pipelines."""
    
    def __init__(self, db_path: str = None):
        """Initialize the database manager.
        
        Args:
            db_path: Path to the SQLite database file. If None, uses default location.
        """
        if db_path is None:
            # Use default location in the project directory
            project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(project_dir, 'astro_pipelines.db')
        
        self.db_path = db_path
        self.engine = None
        self.SessionLocal = None
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize the database engine and create tables if they don't exist."""
        try:
            # Create SQLite engine
            self.engine = create_engine(f'sqlite:///{self.db_path}', echo=False)
            
            # Create all tables
            Base.metadata.create_all(self.engine)
            
            # Create session factory
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            
            print(f"Database initialized at: {self.db_path}")
            
        except SQLAlchemyError as e:
            print(f"Error initializing database: {e}")
            raise
    
    def get_session(self) -> Session:
        """Get a new database session.
        
        Returns:
            SQLAlchemy session object
        """
        if self.SessionLocal is None:
            raise RuntimeError("Database not initialized")
        return self.SessionLocal()
    
    def add_fits_file(self, fits_data: dict) -> FitsFile:
        """Add a new FITS file to the database.
        
        Args:
            fits_data: Dictionary containing FITS file data
            
        Returns:
            The created FitsFile object
        """
        session = self.get_session()
        try:
            # Create new FitsFile object
            fits_file = FitsFile(**fits_data)
            session.add(fits_file)
            session.commit()
            session.refresh(fits_file)
            return fits_file
        except SQLAlchemyError as e:
            session.rollback()
            print(f"Error adding FITS file: {e}")
            raise
        finally:
            session.close()
    
    def get_fits_file_by_path(self, path: str) -> FitsFile:
        """Get a FITS file by its path.
        
        Args:
            path: File path to search for
            
        Returns:
            FitsFile object if found, None otherwise
        """
        session = self.get_session()
        try:
            return session.query(FitsFile).filter(FitsFile.path == path).first()
        finally:
            session.close()
    
    def get_all_fits_files(self) -> list:
        """Get all FITS files in the database.
        
        Returns:
            List of all FitsFile objects
        """
        session = self.get_session()
        try:
            return session.query(FitsFile).all()
        finally:
            session.close()
    
    def update_fits_file(self, fits_file_id: int, update_data: dict) -> bool:
        """Update an existing FITS file.
        
        Args:
            fits_file_id: ID of the FITS file to update
            update_data: Dictionary containing fields to update
            
        Returns:
            True if successful, False otherwise
        """
        session = self.get_session()
        try:
            fits_file = session.query(FitsFile).filter(FitsFile.id == fits_file_id).first()
            if fits_file:
                for key, value in update_data.items():
                    if hasattr(fits_file, key):
                        setattr(fits_file, key, value)
                session.commit()
                return True
            return False
        except SQLAlchemyError as e:
            session.rollback()
            print(f"Error updating FITS file: {e}")
            return False
        finally:
            session.close()
    
    def delete_fits_file(self, fits_file_id: int) -> bool:
        """Delete a FITS file and its associated sources.
        
        Args:
            fits_file_id: ID of the FITS file to delete
            
        Returns:
            True if successful, False otherwise
        """
        session = self.get_session()
        try:
            fits_file = session.query(FitsFile).filter(FitsFile.id == fits_file_id).first()
            if fits_file:
                session.delete(fits_file)
                session.commit()
                return True
            return False
        except SQLAlchemyError as e:
            session.rollback()
            print(f"Error deleting FITS file: {e}")
            return False
        finally:
            session.close()
    
    def add_sources_to_fits_file(self, fits_file_id: int, sources_data: list) -> bool:
        """Add sources to a FITS file.
        
        Args:
            fits_file_id: ID of the FITS file
            sources_data: List of dictionaries containing source data
            
        Returns:
            True if successful, False otherwise
        """
        session = self.get_session()
        try:
            fits_file = session.query(FitsFile).filter(FitsFile.id == fits_file_id).first()
            if not fits_file:
                return False
            
            for source_data in sources_data:
                source_data['fits_file_id'] = fits_file_id
                source = Source(**source_data)
                session.add(source)
            
            session.commit()
            return True
        except SQLAlchemyError as e:
            session.rollback()
            print(f"Error adding sources: {e}")
            return False
        finally:
            session.close()
    
    def get_sources_for_fits_file(self, fits_file_id: int) -> list:
        """Get all sources for a FITS file.
        
        Args:
            fits_file_id: ID of the FITS file
            
        Returns:
            List of Source objects
        """
        session = self.get_session()
        try:
            return session.query(Source).filter(Source.fits_file_id == fits_file_id).all()
        finally:
            session.close()
    
    def close(self):
        """Close the database connection."""
        if self.engine:
            self.engine.dispose()

# Global database manager instance
db_manager = None

def get_db_manager(db_path: str = None) -> DatabaseManager:
    """Get the global database manager instance.
    
    Args:
        db_path: Optional custom database path
        
    Returns:
        DatabaseManager instance
    """
    global db_manager
    if db_manager is None:
        db_manager = DatabaseManager(db_path)
    return db_manager 