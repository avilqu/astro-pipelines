import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from .models import Base, FitsFile, Source, CalibrationMaster
from config import to_display_time

class DatabaseManager:
    """Manages database connections and operations for astro-pipelines."""
    
    def __init__(self, db_path: str = None):
        """Initialize the database manager.
        
        Args:
            db_path: Path to the SQLite database file. If None, uses default location from config.
        """
        if db_path is None:
            # Use default location from config
            import config
            db_path = config.DATABASE_PATH
        
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
    
    def get_unique_targets(self) -> list:
        """Get all unique targets from the database."""
        session = self.get_session()
        try:
            return [row[0] for row in session.query(FitsFile.target).distinct().order_by(FitsFile.target).all() if row[0]]
        finally:
            session.close()

    def get_unique_dates(self) -> list:
        """Get all unique observation dates (YYYY-MM-DD) from the database."""
        session = self.get_session()
        try:
            # Extract date part from datetime, return as string
            dates = session.query(FitsFile.date_obs).distinct().all()
            date_strs = set()
            for (dt,) in dates:
                if dt:
                    date_strs.add(dt.strftime('%Y-%m-%d'))
            return sorted(date_strs)
        finally:
            session.close()

    def get_unique_local_dates(self) -> list:
        """Get all unique observation dates (YYYY-MM-DD) in local time from the database."""
        session = self.get_session()
        try:
            dates = session.query(FitsFile.date_obs).distinct().all()
            date_strs = set()
            for (dt,) in dates:
                if dt:
                    dt_disp = to_display_time(dt)
                    date_strs.add(dt_disp.strftime('%Y-%m-%d'))
            return sorted(date_strs)
        finally:
            session.close()

    def get_file_count_by_target(self, target: str) -> int:
        """Get the number of files for a specific target."""
        session = self.get_session()
        try:
            return session.query(FitsFile).filter(FitsFile.target == target).count()
        finally:
            session.close()

    def get_file_count_by_date(self, date: str) -> int:
        """Get the number of files for a specific date."""
        session = self.get_session()
        try:
            # Convert date string to datetime for comparison
            from datetime import datetime
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            next_date = datetime.strptime(date, '%Y-%m-%d').replace(day=date_obj.day + 1)
            return session.query(FitsFile).filter(
                FitsFile.date_obs >= date_obj,
                FitsFile.date_obs < next_date
            ).count()
        finally:
            session.close()

    def get_file_count_by_local_date(self, date: str) -> int:
        """Get the number of files for a specific local date (YYYY-MM-DD)."""
        session = self.get_session()
        try:
            from datetime import datetime, timedelta
            files = session.query(FitsFile.date_obs).all()
            count = 0
            for (dt,) in files:
                if dt:
                    dt_disp = to_display_time(dt)
                    if dt_disp.strftime('%Y-%m-%d') == date:
                        count += 1
            return count
        finally:
            session.close()

    def get_total_file_count(self) -> int:
        """Get the total number of files in the database."""
        session = self.get_session()
        try:
            return session.query(FitsFile).count()
        finally:
            session.close()

    def get_calibration_file_count(self, frame_type: str) -> int:
        """Get the number of calibration files of a specific type."""
        session = self.get_session()
        try:
            return session.query(CalibrationMaster).filter(CalibrationMaster.frame == frame_type).count()
        finally:
            session.close()
    
    def add_calibration_master(self, master_data: dict) -> CalibrationMaster:
        """Add a new CalibrationMaster to the database.
        Args:
            master_data: Dictionary containing calibration master data
        Returns:
            The created CalibrationMaster object
        """
        session = self.get_session()
        try:
            master = CalibrationMaster(**master_data)
            session.add(master)
            session.commit()
            session.refresh(master)
            return master
        except SQLAlchemyError as e:
            session.rollback()
            print(f"Error adding CalibrationMaster: {e}")
            raise
        finally:
            session.close()

    def get_calibration_master_by_path(self, path: str) -> CalibrationMaster:
        """Get a CalibrationMaster by its path.
        Args:
            path: File path to search for
        Returns:
            CalibrationMaster object if found, None otherwise
        """
        session = self.get_session()
        try:
            return session.query(CalibrationMaster).filter(CalibrationMaster.path == path).first()
        finally:
            session.close()

    def get_files_by_target(self, target: str) -> list:
        """Get all FITS files for a specific target.
        
        Args:
            target: Target name to search for
            
        Returns:
            List of FitsFile objects for the target
        """
        session = self.get_session()
        try:
            return session.query(FitsFile).filter(FitsFile.target == target).all()
        finally:
            session.close()

    def move_target_to_archive(self, target: str, archive_path: str) -> dict:
        """Move all files for a target to the archive and remove from database.
        
        Args:
            target: Target name to archive
            archive_path: Base path for the archive directory
            
        Returns:
            Dictionary with results: {'files_moved': int, 'files_removed': int, 'errors': list}
        """
        import os
        import shutil
        from pathlib import Path
        
        session = self.get_session()
        results = {'files_moved': 0, 'files_removed': 0, 'errors': []}
        
        try:
            # Get all files for this target
            files = session.query(FitsFile).filter(FitsFile.target == target).all()
            
            if not files:
                return results
            
            # Create archive directory structure
            archive_base = Path(archive_path)
            archive_base.mkdir(parents=True, exist_ok=True)
            
            # Track directories that will become empty
            directories_to_cleanup = set()
            
            for fits_file in files:
                try:
                    # Get the original file path
                    original_path = Path(fits_file.path)
                    
                    if not original_path.exists():
                        # File doesn't exist, just remove from database
                        session.delete(fits_file)
                        results['files_removed'] += 1
                        continue
                    
                    # Determine archive path (maintain directory structure relative to DATA_PATH)
                    import config
                    data_path = Path(config.DATA_PATH)
                    try:
                        relative_path = original_path.relative_to(data_path)
                        # Track the directory for cleanup
                        directories_to_cleanup.add(original_path.parent)
                    except ValueError:
                        # File is not under DATA_PATH, use filename only
                        relative_path = original_path.name
                    
                    archive_file_path = archive_base / relative_path
                    archive_file_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Move the file to archive
                    shutil.move(str(original_path), str(archive_file_path))
                    
                    # Remove from database
                    session.delete(fits_file)
                    
                    results['files_moved'] += 1
                    results['files_removed'] += 1
                    
                except Exception as e:
                    error_info = {
                        'path': str(fits_file.path),
                        'error': str(e)
                    }
                    results['errors'].append(error_info)
            
            # Clean up empty directories (in reverse order to handle nested dirs)
            import config
            data_path = Path(config.DATA_PATH)
            target_dir = data_path / target
            
            if target_dir.exists():
                # Remove the target directory and all its subdirectories
                try:
                    shutil.rmtree(str(target_dir))
                except Exception as e:
                    results['errors'].append({
                        'path': f'cleanup_directory_{target}',
                        'error': f'Failed to remove empty directory {target_dir}: {str(e)}'
                    })
            
            # Commit all changes
            session.commit()
            
        except Exception as e:
            session.rollback()
            results['errors'].append({
                'path': 'database_operation',
                'error': f'Database error: {str(e)}'
            })
        finally:
            session.close()
        
        return results
    
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