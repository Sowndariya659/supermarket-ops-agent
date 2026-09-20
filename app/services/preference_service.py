"""Persistent owner preferences and memory service."""

from typing import Dict, Optional, Any
from sqlalchemy.orm import Session
from app.database.repositories import PreferenceRepository
from app.database.models import OwnerPreference


class PreferenceService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = PreferenceRepository(session)

    def get_preference(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve a stored preference value by key."""
        return self.repo.get(key, default)

    def set_preference(self, key: str, value: str) -> Dict[str, Any]:
        """Store or update a persistent preference."""
        pref = self.repo.set(key, value)
        self.session.commit()
        return {
            "key": pref.key,
            "value": pref.value,
            "updated_at": pref.updated_at.isoformat() if pref.updated_at else None,
        }

    def get_all_preferences(self) -> Dict[str, str]:
        """Retrieve all preferences as a key-value mapping."""
        prefs = self.session.query(OwnerPreference).all()
        return {p.key: p.value for p in prefs}
