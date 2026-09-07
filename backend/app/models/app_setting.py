from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class AppSetting(Base):
    """Reglages internes generes par l'application elle-meme.

    Sert aujourd'hui a conserver la cle de signature des jetons quand
    l'administrateur n'en a pas fourni : elle doit survivre aux
    redemarrages, sinon toutes les sessions sautent a chaque `up -d`.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
