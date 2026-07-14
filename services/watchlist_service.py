"""
services/watchlist_service.py — CineLog (feature/watchlist branch)

Business logic for the watchlist feature.
"""

from sqlalchemy.exc import IntegrityError

from app import db
from models import Film, WatchlistEntry
from services.collection_service import FilmNotFoundError


class AlreadyInWatchlistError(Exception):
    """Raised when a film is already in the user's watchlist."""
    pass


def _is_duplicate_watchlist_error(error):
    """Return whether an integrity error names the watchlist uniqueness rule."""
    original_error = error.orig
    diagnostic = getattr(original_error, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)

    if constraint_name == "unique_user_film_watchlist":
        return True

    message = str(original_error).lower()
    return (
        "unique_user_film_watchlist" in message
        or (
            "unique constraint failed" in message
            and "watchlist_entry.user_id" in message
            and "watchlist_entry.film_id" in message
        )
    )


def add_to_watchlist(user_id, film_id):
    """
    Add a film to a user's watchlist.

    Args:
        user_id (str): UUID of the user.
        film_id (str): UUID of the film.

    Returns:
        WatchlistEntry: The newly created entry.

    Raises:
        FilmNotFoundError: If film_id does not exist.
        AlreadyInWatchlistError: If the film is already in the user's watchlist.
    """
    film = db.session.get(Film, film_id)
    if film is None:
        raise FilmNotFoundError(f"No film found with id '{film_id}'")

    existing = WatchlistEntry.query.filter_by(
        user_id=user_id, film_id=film_id
    ).first()

    if existing:
        raise AlreadyInWatchlistError(
            f"Film '{film_id}' is already in this user's watchlist"
        )

    entry = WatchlistEntry(user_id=user_id, film_id=film_id)
    db.session.add(entry)

    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()

        if not _is_duplicate_watchlist_error(error):
            raise

        raise AlreadyInWatchlistError(
            f"Film '{film_id}' is already in this user's watchlist"
        ) from error

    return entry


def get_watchlist(user_id):
    """
    Return all films on a user's watchlist.

    Args:
        user_id (str): UUID of the user.

    Returns:
        list[dict]: List of film dicts with watchlist metadata attached.
    """
    entries = (
        WatchlistEntry.query
        .filter_by(user_id=user_id)
        .join(Film)
        .order_by(WatchlistEntry.date_added.desc())
        .all()
    )

    result = []
    for entry in entries:
        film_dict = entry.film.to_dict()
        film_dict["date_added"] = entry.date_added.isoformat()
        film_dict["public"] = entry.public
        result.append(film_dict)

    return result
