"""Sauvegarde : lecture d'archive sûre (aucun chemin pris dans le zip, tailles bornées)."""

import io
import json
import uuid
import zipfile

import pytest

from app.services import backup, image_service

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _zip(files: dict) -> zipfile.ZipFile:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return zipfile.ZipFile(io.BytesIO(buffer.getvalue()))


def test_only_well_named_real_images_are_read():
    archive = _zip({"images/a.png": PNG, "images/b.png": b"pas une image", "images/../x.png": PNG,
                    "../images/c.png": PNG})
    assert backup._read_image(archive, "images/a.png") == (PNG, "png")
    assert backup._read_image(archive, "images/b.png") is None       # mauvaise signature
    assert backup._read_image(archive, "images/../x.png") is None    # chemin refusé
    assert backup._read_image(archive, "../images/c.png") is None
    assert backup._read_image(archive, "images/absente.png") is None


def test_thumbnail_keeps_web_links_and_drops_anything_else(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "media_dir", str(tmp_path))
    archive = _zip({"images/a.png": PNG})
    rid = uuid.uuid4()
    saved = backup._thumbnail(archive, "images/a.png", rid)
    assert saved.startswith("/media/recipes/") and (tmp_path / saved.removeprefix("/media/")).read_bytes() == PNG
    assert backup._thumbnail(archive, "https://img.ex/a.jpg", rid) == "https://img.ex/a.jpg"
    assert backup._thumbnail(archive, "javascript:alert(1)", rid) is None
    assert backup._thumbnail(archive, "/etc/passwd", rid) is None


@pytest.mark.parametrize("files, message", [
    ({"autre.json": "{}"}, "pas une sauvegarde"),
    ({"popote.json": "pas du json"}, "illisible"),
    ({"popote.json": json.dumps({"format": "mealie"})}, "pas une sauvegarde"),
    ({"popote.json": json.dumps({"format": "popote-backup", "version": 99})}, "plus récente"),
])
def test_foreign_or_broken_archives_are_refused(files, message):
    with pytest.raises(backup.BackupError, match=message):
        backup._read_data(_zip(files))


def test_same_recipe_means_same_link_or_same_title():
    assert backup._key("Tarte", "https://ex.fr/t") == backup._key("Autre titre", "https://ex.fr/t")
    assert backup._key("Tarte  aux pommes", None) == backup._key("tarte aux pommes", None)
    assert backup._key("Tarte", None) != backup._key("Tarte", "https://ex.fr/t")


def test_backup_recipe_is_cleaned_like_a_manual_edit():
    item = backup._BackupRecipe.model_validate({
        "title": " Tarte ", "source_type": "inconnu", "tags": ["a", "", 3],
        "ingredients": [{"name": "farine", "section": "Pâte"}, {"name": " "}],
        "history": [{"cooked_on": "2026-09-01", "rating": 5}],
    })
    assert item.title == "Tarte" and item.source_type.value == "manual" and item.tags == ["a", "3"]
    assert item.ingredients == [{"quantity": None, "unit": None, "name": "farine", "notes": None, "section": "Pâte"}]
    with pytest.raises(Exception):
        backup._BackupRecipe.model_validate({"title": "   "})
