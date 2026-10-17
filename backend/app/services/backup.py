"""Sauvegarde complète d'un compte : recettes, images, carnets, historique.

Un seul fichier .zip à garder au chaud (ou à réimporter sur un autre
serveur Popote) :

- ``popote.json`` : les recettes (contenu, notes, favoris, avis, historique)
  et les carnets ;
- ``images/<id>.<ext>`` : les images stockées sur ce serveur. Une image
  externe (vignette YouTube, image d'un site) reste un lien.

À l'import, rien n'est écrit sur le disque d'après un nom pris dans
l'archive (pas de « ../ ») et chaque taille est vérifiée avant lecture :
une archive piégée ne peut ni sortir du dossier des images, ni remplir le
disque.
"""

import json
import logging
import re
import uuid
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.collection import Collection, CollectionRecipe
from ..models.cook_log import CookLog
from ..models.recipe import ExtractionStatus, Recipe, SourceType
from ..schemas.recipe import RecipeUpdate
from . import image_service

logger = logging.getLogger(__name__)

FORMAT = "popote-backup"
VERSION = 1
DATA_FILE = "popote.json"
_IMAGE_TYPES = {"jpg": "jpg", "jpeg": "jpg", "png": "png", "webp": "webp"}
_IMAGE_NAME = re.compile(r"^images/[A-Za-z0-9_-]{1,80}\.(jpg|jpeg|png|webp)$")
_MAX_DATA_BYTES = 100 * 1024 * 1024
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_RECIPES = 10_000
# Signatures des formats acceptés : un .jpg qui n'en est pas un est ignoré.
_MAGIC = {"jpg": (b"\xff\xd8\xff",), "png": (b"\x89PNG\r\n\x1a\n",), "webp": (b"RIFF",)}


class BackupError(ValueError):
    """Archive illisible ou qui n'est pas une sauvegarde Popote."""


# ── Export ───────────────────────────────────────────────────────────────────

def _iso(value) -> str | None:
    return value.isoformat() if isinstance(value, (date, datetime)) else None


def _local_image(url: str | None) -> Path | None:
    prefix = f"/media/{image_service.THUMBNAIL_SUBDIR}/"
    if not url or not url.startswith(prefix):
        return None
    path = Path(settings.media_dir) / url.removeprefix("/media/")
    return path if path.is_file() else None


async def build_backup(db: AsyncSession, owner_id: uuid.UUID, target: Path) -> dict:
    """Écrit la sauvegarde du compte dans [target] (zip). Retourne les totaux."""
    recipes = (await db.execute(
        select(Recipe).where(Recipe.owner_id == owner_id, Recipe.status == ExtractionStatus.done)
        .order_by(Recipe.created_at)
    )).scalars().all()
    logs = (await db.execute(
        select(CookLog).where(CookLog.owner_id == owner_id).order_by(CookLog.cooked_on)
    )).scalars().all()
    collections = (await db.execute(
        select(Collection).where(Collection.owner_id == owner_id).order_by(Collection.created_at)
    )).scalars().all()
    links = (await db.execute(
        select(CollectionRecipe).where(CollectionRecipe.collection_id.in_([c.id for c in collections]))
    )).scalars().all() if collections else []

    history: dict[uuid.UUID, list[dict]] = {}
    for log in logs:
        history.setdefault(log.recipe_id, []).append(
            {"cooked_on": _iso(log.cooked_on), "rating": log.rating, "comment": log.comment}
        )

    images = 0
    with zipfile.ZipFile(target, "w") as archive:
        entries = []
        for recipe in recipes:
            thumbnail = recipe.thumbnail_url
            local = _local_image(thumbnail)
            if local:
                ext = _IMAGE_TYPES.get(local.suffix.lstrip(".").lower(), "jpg")
                thumbnail = f"images/{recipe.id}.{ext}"
                # Images déjà compressées : stockées telles quelles.
                archive.write(local, thumbnail, compress_type=zipfile.ZIP_STORED)
                images += 1
            entries.append({
                "id": str(recipe.id),
                "title": recipe.title,
                "description": recipe.description,
                "source_url": recipe.source_url,
                "source_type": recipe.source_type.value if recipe.source_type else None,
                "language": recipe.language,
                "category": recipe.category,
                "servings": recipe.servings,
                "prep_time": recipe.prep_time,
                "cook_time": recipe.cook_time,
                "ingredients": recipe.ingredients or [],
                "steps": recipe.steps or [],
                "tags": recipe.tags or [],
                "thumbnail_url": thumbnail,
                "nutrition": recipe.nutrition,
                "is_favorite": recipe.is_favorite,
                "notes": recipe.notes,
                "rating": recipe.rating,
                "cook_again": recipe.cook_again,
                "shared_by_name": recipe.shared_by_name,
                "created_at": _iso(recipe.created_at),
                "history": history.get(recipe.id, []),
            })
        by_collection: dict[uuid.UUID, list[str]] = {}
        for link in links:
            by_collection.setdefault(link.collection_id, []).append(str(link.recipe_id))
        data = {
            "format": FORMAT,
            "version": VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "recipes": entries,
            "collections": [
                {"name": c.name, "emoji": c.emoji, "description": c.description,
                 "recipes": by_collection.get(c.id, [])}
                for c in collections
            ],
        }
        archive.writestr(DATA_FILE, json.dumps(data, ensure_ascii=False, indent=1),
                         compress_type=zipfile.ZIP_DEFLATED)
    return {"recipes": len(entries), "collections": len(collections), "images": images}


# ── Import ───────────────────────────────────────────────────────────────────

class _HistoryEntry(BaseModel):
    cooked_on: date
    rating: int | None = Field(None, ge=1, le=5)
    comment: str | None = Field(None, max_length=5000)


class _BackupRecipe(RecipeUpdate):
    """Recette de la sauvegarde, avec les mêmes contrôles qu'une modification
    à la main (titre non vide, lignes vides retirées, bornes des colonnes)."""

    id: str | None = None
    title: str = Field(min_length=1, max_length=500)
    source_url: str | None = Field(None, max_length=5000)
    source_type: SourceType = SourceType.manual
    language: str | None = Field(None, max_length=20)
    is_favorite: bool = False
    shared_by_name: str | None = Field(None, max_length=100)
    created_at: datetime | None = None
    history: list[_HistoryEntry] = Field(default_factory=list, max_length=10_000)

    @field_validator("source_type", mode="before")
    @classmethod
    def _known_source(cls, value):
        return value if value in {s.value for s in SourceType} else SourceType.manual

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, value):
        return [str(t)[:50] for t in value if str(t).strip()][:20] if isinstance(value, list) else []


class _BackupCollection(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    emoji: str | None = Field(None, max_length=16)
    description: str | None = Field(None, max_length=5000)
    recipes: list[str] = Field(default_factory=list)


def _read_data(archive: zipfile.ZipFile) -> dict:
    try:
        info = archive.getinfo(DATA_FILE)
    except KeyError:
        raise BackupError("Ce fichier n'est pas une sauvegarde Popote (popote.json absent).")
    if info.file_size > _MAX_DATA_BYTES:
        raise BackupError("Sauvegarde trop volumineuse.")
    try:
        data = json.loads(archive.read(info))
    except (ValueError, UnicodeDecodeError):
        raise BackupError("Sauvegarde illisible (popote.json invalide).")
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise BackupError("Ce fichier n'est pas une sauvegarde Popote.")
    if not isinstance(data.get("version"), int) or data["version"] > VERSION:
        raise BackupError("Sauvegarde faite par une version plus récente de Popote : mettez Popote à jour.")
    return data


def _read_image(archive: zipfile.ZipFile, name: str) -> tuple[bytes, str] | None:
    """(octets, extension) d'une image de l'archive, ou None si suspecte."""
    match = _IMAGE_NAME.match(name)
    if not match:
        return None
    try:
        info = archive.getinfo(name)
    except KeyError:
        return None
    if info.file_size > _MAX_IMAGE_BYTES:
        return None
    ext = _IMAGE_TYPES[match.group(1)]
    data = archive.read(info)
    if not data.startswith(_MAGIC[ext]):
        return None
    return data, ext


def _thumbnail(archive: zipfile.ZipFile, value: str | None, recipe_id: uuid.UUID) -> str | None:
    if not value:
        return None
    if value.startswith("images/"):
        image = _read_image(archive, value)
        return image_service.save_thumbnail_bytes(recipe_id, *image) if image else None
    return value if re.match(r"^https?://", value) and len(value) <= 5000 else None


def _key(title: str, source_url: str | None) -> str:
    """Même recette : même lien d'origine, ou même titre si elle n'en a pas."""
    return f"url:{source_url}" if source_url else f"titre:{' '.join(title.lower().split())}"


async def restore_backup(db: AsyncSession, owner_id: uuid.UUID, path: Path) -> dict:
    """Ajoute au compte le contenu de la sauvegarde [path], sans doublons.

    Les recettes déjà présentes (même lien d'origine, ou même titre sans
    lien) sont gardées telles quelles ; les carnets du même nom sont
    complétés plutôt que dupliqués.
    """
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise BackupError("Fichier illisible : choisissez le .zip d'une sauvegarde Popote.")
    with archive:
        data = _read_data(archive)
        raw_recipes = data.get("recipes") if isinstance(data.get("recipes"), list) else []
        raw_collections = data.get("collections") if isinstance(data.get("collections"), list) else []
        if len(raw_recipes) > _MAX_RECIPES:
            raise BackupError(f"Plus de {_MAX_RECIPES} recettes : sauvegarde refusée.")

        existing = (await db.execute(
            select(Recipe.id, Recipe.title, Recipe.source_url).where(Recipe.owner_id == owner_id)
        )).all()
        known = {_key(title, url): rid for rid, title, url in existing}

        report = {"recipes_added": 0, "recipes_skipped": 0, "invalid": 0, "images": 0, "collections_added": 0}
        new_ids: dict[str, uuid.UUID] = {}  # id dans la sauvegarde → recette du compte
        logs: list[CookLog] = []
        for raw in raw_recipes:
            try:
                item = _BackupRecipe.model_validate(raw)
            except ValidationError:
                report["invalid"] += 1
                continue
            key = _key(item.title, item.source_url)
            if key in known:
                report["recipes_skipped"] += 1
                if item.id:
                    new_ids[item.id] = known[key]
                continue
            recipe_id = uuid.uuid4()
            thumbnail = _thumbnail(archive, item.thumbnail_url, recipe_id)
            report["images"] += bool(thumbnail and thumbnail.startswith("/media/"))
            history = sorted(item.history, key=lambda h: h.cooked_on)
            db.add(Recipe(
                id=recipe_id,
                owner_id=owner_id,
                status=ExtractionStatus.done,
                title=item.title,
                description=item.description,
                source_url=item.source_url,
                source_type=item.source_type,
                language=item.language,
                category=item.category,
                servings=item.servings,
                prep_time=item.prep_time,
                cook_time=item.cook_time,
                ingredients=item.ingredients or [],
                steps=item.steps or [],
                tags=item.tags or [],
                thumbnail_url=thumbnail,
                nutrition=item.nutrition,
                is_favorite=item.is_favorite,
                notes=item.notes,
                rating=item.rating,
                cook_again=item.cook_again,
                shared_by_name=item.shared_by_name,
                cooked_count=len(history),
                last_cooked_at=history[-1].cooked_on if history else None,
                **({"created_at": item.created_at} if item.created_at else {}),
            ))
            logs.extend(
                CookLog(owner_id=owner_id, recipe_id=recipe_id, cooked_on=entry.cooked_on,
                        rating=entry.rating, comment=entry.comment)
                for entry in history
            )
            known[key] = recipe_id
            if item.id:
                new_ids[item.id] = recipe_id
            report["recipes_added"] += 1
        # Recettes d'abord : sans relation déclarée entre les deux tables,
        # SQLAlchemy pourrait écrire l'historique avant la recette (clé étrangère).
        await db.flush()
        db.add_all(logs)
        await db.flush()

        collections = {
            c.name.lower(): c for c in (await db.execute(
                select(Collection).where(Collection.owner_id == owner_id)
            )).scalars()
        }
        for raw in raw_collections:
            try:
                item = _BackupCollection.model_validate(raw)
            except ValidationError:
                report["invalid"] += 1
                continue
            collection = collections.get(item.name.lower())
            if collection is None:
                collection = Collection(owner_id=owner_id, name=item.name, emoji=item.emoji,
                                        description=item.description)
                db.add(collection)
                await db.flush()
                collections[item.name.lower()] = collection
                report["collections_added"] += 1
            inside = set((await db.execute(
                select(CollectionRecipe.recipe_id).where(CollectionRecipe.collection_id == collection.id)
            )).scalars())
            for old_id in item.recipes:
                recipe_id = new_ids.get(old_id)
                if recipe_id and recipe_id not in inside:
                    db.add(CollectionRecipe(collection_id=collection.id, recipe_id=recipe_id))
                    inside.add(recipe_id)
        await db.commit()
    return report
