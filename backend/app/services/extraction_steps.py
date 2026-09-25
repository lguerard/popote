"""Délai et suivi des étapes d'une extraction (sans dépendance FastAPI)."""

import logging
import time

logger = logging.getLogger(__name__)

# Une extraction qui n'a pas fini au bout de ce delai est abandonnee plutot
# que laissee "processing" indefiniment : un scrape ou un appel LLM qui
# reste bloque (page qui ne finit jamais de charger, modele local surcharge)
# ne doit pas transformer la recette en zombie que rien ne relance jamais.
EXTRACTION_TIMEOUT_SECONDS = 300


class StepTracker:
    """Journalise chaque étape d'une extraction avec sa durée.

    Sans cela, une extraction qui dépassait le délai ne laissait aucune
    trace de l'étape qui avait pris tout le temps (téléchargement,
    transcription, OCR, LLM…).
    """

    def __init__(self, label: str):
        self.label = label
        self.started = time.monotonic()
        self.step: str | None = None
        self.step_started = self.started

    def record(self, message: str) -> None:
        now = time.monotonic()
        if self.step:
            logger.info("%s : « %s » en %.0fs", self.label, self.step, now - self.step_started)
        self.step, self.step_started = message, now

    def timeout_message(self, what: str = "Extraction", suffix: str = "abandonnée.") -> str:
        stuck = f", bloquée à l'étape « {self.step.rstrip('…. ')} »" if self.step else ""
        logger.warning(
            "%s : délai dépassé après %.0fs, étape en cours « %s » depuis %.0fs",
            self.label, time.monotonic() - self.started, self.step,
            time.monotonic() - self.step_started,
        )
        return (
            f"{what} trop longue (plus de {EXTRACTION_TIMEOUT_SECONDS // 60} minutes)"
            f"{stuck} : {suffix}"
        )
