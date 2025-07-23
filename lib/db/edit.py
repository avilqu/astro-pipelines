import sys
from lib.db.manager import get_db_manager
from lib.db.models import FitsFile
from lib.fits import set_fits_header_value
from lib.db.scan import normalize_object_name, rescan_single_file
from sqlalchemy.orm import Session

def rename_target_across_database(old_target: str, new_target: str, commit: bool = True):
    """
    Rename a target across the database and FITS files.
    Args:
        old_target: The current (old) target name
        new_target: The new target name to set
        commit: Whether to commit DB changes (default True)
    Returns:
        dict: Summary of the operation
    """
    db = get_db_manager()
    session: Session = db.get_session()
    old_norm = normalize_object_name(old_target)
    new_norm = normalize_object_name(new_target)
    results = {
        'files_updated': 0,
        'errors': [],
        'files': []
    }
    try:
        files = session.query(FitsFile).filter(FitsFile.target == old_norm).all()
        for fits_file in files:
            try:
                set_fits_header_value(fits_file.path, 'OBJECT', new_norm)
                fits_file.target = new_norm
                if commit:
                    session.commit()
                rescan_result = rescan_single_file(fits_file.path)
                results['files_updated'] += 1
                results['files'].append({'path': fits_file.path, 'rescan': rescan_result})
            except Exception as e:
                session.rollback()
                results['errors'].append({'path': fits_file.path, 'error': str(e)})
        if commit:
            session.commit()
    finally:
        session.close()
    return results

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m lib.db.edit <old_target> <new_target>")
        sys.exit(1)
    old_target, new_target = sys.argv[1], sys.argv[2]
    summary = rename_target_across_database(old_target, new_target)
    print(f"Updated {summary['files_updated']} files.")
    if summary['errors']:
        print("Errors:")
        for err in summary['errors']:
            print(f"  {err['path']}: {err['error']}") 