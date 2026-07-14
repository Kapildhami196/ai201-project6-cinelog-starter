"""
tests/test_watchlist.py — CineLog

Tests for the watchlist service and API.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app import create_app, db
from models import Film, User
from services.collection_service import FilmNotFoundError
from services.watchlist_service import AlreadyInWatchlistError, add_to_watchlist


@pytest.fixture
def app():
    """Create an isolated test app with an in-memory database."""
    app = create_app(config={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sample_user(app):
    """Create a user for watchlist tests."""
    with app.app_context():
        user = User(username="watchlistuser", email="watchlist@example.com")
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def sample_film(app):
    """Create a film for watchlist tests."""
    with app.app_context():
        film = Film(title="Paddington 2", year=2017, genre="Comedy")
        db.session.add(film)
        db.session.commit()
        return film.id


def test_add_to_watchlist_nonexistent_film_raises(app, sample_user):
    """
    Adding a film_id that does not exist should raise FilmNotFoundError.
    """
    with app.app_context():
        fake_film_id = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(FilmNotFoundError):
            add_to_watchlist(
                user_id=sample_user,
                film_id=fake_film_id,
            )


def test_add_to_watchlist_integrity_error_rolls_back(
    app,
    sample_user,
    sample_film,
    monkeypatch,
):
    """A uniqueness race should be translated and roll back the session."""
    rollback_called = False

    def fail_commit():
        raise IntegrityError(
            "INSERT",
            {},
            Exception(
                "UNIQUE constraint failed: "
                "watchlist_entry.user_id, watchlist_entry.film_id"
            ),
        )

    def track_rollback():
        nonlocal rollback_called
        rollback_called = True

    with app.app_context():
        monkeypatch.setattr(db.session, "commit", fail_commit)
        monkeypatch.setattr(db.session, "rollback", track_rollback)

        with pytest.raises(AlreadyInWatchlistError):
            add_to_watchlist(user_id=sample_user, film_id=sample_film)

    assert rollback_called


def test_add_to_watchlist_unrelated_integrity_error_propagates(
    app,
    sample_user,
    sample_film,
    monkeypatch,
):
    """A non-duplicate integrity failure should not become a conflict."""
    rollback_called = False
    failure = IntegrityError(
        "INSERT",
        {},
        Exception("FOREIGN KEY constraint failed"),
    )

    def fail_commit():
        raise failure

    def track_rollback():
        nonlocal rollback_called
        rollback_called = True

    with app.app_context():
        monkeypatch.setattr(db.session, "commit", fail_commit)
        monkeypatch.setattr(db.session, "rollback", track_rollback)

        with pytest.raises(IntegrityError) as raised_error:
            add_to_watchlist(user_id=sample_user, film_id=sample_film)

    assert raised_error.value is failure
    assert rollback_called


def test_add_watchlist_route_returns_404_for_missing_film(app, sample_user):
    """The API should expose a missing film as a client error."""
    response = app.test_client().post(
        f"/watchlist/{sample_user}/add",
        json={"film_id": "00000000-0000-0000-0000-000000000000"},
    )

    assert response.status_code == 404
    assert "No film found" in response.get_json()["error"]


def test_add_watchlist_route_returns_409_for_duplicate(
    app,
    sample_user,
    sample_film,
):
    """The API should expose a duplicate entry as a conflict."""
    client = app.test_client()
    payload = {"film_id": sample_film}

    first_response = client.post(
        f"/watchlist/{sample_user}/add",
        json=payload,
    )
    duplicate_response = client.post(
        f"/watchlist/{sample_user}/add",
        json=payload,
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert "already in" in duplicate_response.get_json()["error"]
