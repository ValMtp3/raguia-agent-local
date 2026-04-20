"""Connecteurs de sources de documents.

FileSystemConnector.scan() ne charge plus les fichiers en RAM :
il yield des DocumentSource avec content=b"" (lazy).
L'upload lit le fichier au moment de l'envoi via api_client.upload_files().
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


@dataclass
class DocumentSource:
    """Represente un document source a synchroniser."""
    path: Path
    relative_path: str
    metadata: dict = field(default_factory=dict)
    # content n'est PAS charge ici (evite de tout charger en RAM)


class SourceConnector(ABC):
    name: str = "base"

    @abstractmethod
    def initialize(self, config: dict) -> None:
        pass

    @abstractmethod
    def scan(self) -> Iterator[DocumentSource]:
        """Scanne la source. Ne doit PAS lire le contenu des fichiers."""
        pass

    @abstractmethod
    def watch_callback(self, path: Path, kind: str) -> None:
        pass

    def cleanup(self) -> None:
        pass


class FileSystemConnector(SourceConnector):
    """Connecteur fichier systeme (surveillance de dossier)."""

    name = "filesystem"

    def __init__(self) -> None:
        self.root: Path | None = None
        self.supported_extensions: tuple[str, ...] = ()
        self._dirty: set[Path] = set()

    def initialize(self, config: dict) -> None:
        from .config import AgentConfig
        cfg = AgentConfig()
        for k, v in config.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        self.root = cfg.root_path
        self.supported_extensions = cfg.supported_extensions

    def scan(self) -> Iterator[DocumentSource]:
        """Parcourt le dossier sans charger les fichiers en memoire."""
        if not self.root or not self.root.is_dir():
            return
        for p in self.root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in self.supported_extensions:
                continue
            # Filtrage fichiers temporaires (meme logique que watcher)
            from .watcher import _should_ignore
            if _should_ignore(p):
                continue
            try:
                yield DocumentSource(
                    path=p,
                    relative_path=str(p.relative_to(self.root)),
                    metadata={},
                )
            except Exception:
                pass

    def watch_callback(self, path: Path, kind: str) -> None:
        if path.suffix.lower() not in self.supported_extensions:
            return
        self._dirty.add(path)

    def get_dirty(self) -> list[Path]:
        out = list(self._dirty)
        self._dirty.clear()
        return out


class ConnectorRegistry:
    _connectors: dict[str, type[SourceConnector]] = {}

    @classmethod
    def register(cls, name: str, connector_cls: type[SourceConnector]) -> None:
        cls._connectors[name] = connector_cls

    @classmethod
    def get(cls, name: str) -> type[SourceConnector] | None:
        return cls._connectors.get(name)

    @classmethod
    def available(cls) -> list[str]:
        return list(cls._connectors.keys())


ConnectorRegistry.register("filesystem", FileSystemConnector)