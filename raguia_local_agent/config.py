"""Chargement configuration YAML + variables d'environnement.

Ordre de priorite :
  1. Argument --config
  2. Env RAGUIA_AGENT_CONFIG
  3. ~/.raguia/config.yaml  (cree par le wizard)
  4. ./raguia_agent.yaml    (compat arriere)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_ROOT_NAME = "RAGUIA"
APP_DATA_DIR = Path.home() / ".raguia"


def _detect_documents_folder() -> str:
    home = Path.home()
    if sys.platform == "darwin":
        candidates = [home / "Documents", home / "Library" / "Documents"]
    elif sys.platform == "win32":
        candidates = [home / "Documents", home / "OneDrive" / "Documents"]
    else:
        candidates = [home / "Documents"]
    for p in candidates:
        if p.exists() and p.is_dir():
            return str(p)
    return str(home / "Documents")


@dataclass
class AgentConfig:
    api_base: str = "http://127.0.0.1:8000"
    client_slug: str = ""
    agent_token: str = ""
    watch_parent: str = ""
    root_folder_name: str = DEFAULT_ROOT_NAME
    poll_interval_seconds: float = 30.0
    stability_seconds: float = 2.0
    sync_cooldown_seconds: float = 900.0
    burst_threshold: int = 20
    max_files_per_cycle: int = 100
    auto_update: bool = True
    auto_update_check_hours: float = 24.0
    dry_run: bool = False
    # Extensions supportees (normalisees en minuscules au chargement)
    supported_extensions: tuple[str, ...] = (
        ".pdf", ".txt", ".md", ".docx", ".doc",
        ".xlsx", ".xls", ".csv", ".html", ".htm",
        ".pptx", ".png", ".jpg", ".jpeg", ".webp",
    )
    extra: dict[str, Any] = field(default_factory=dict)
    cfg_path: Path | None = None

    def save_token(self, token: str) -> None:
        """Enregistre le nouveau token dans le fichier YAML et en mémoire."""
        self.agent_token = token
        if not self.cfg_path or not self.cfg_path.is_file():
            return
        try:
            with open(self.cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            data["agent_token"] = token
            with open(self.cfg_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Impossible de sauvegarder le nouveau token dans %s : %s", self.cfg_path, e)

    @property
    def root_path(self) -> Path:
        parent = Path(self.watch_parent).expanduser().resolve()
        return parent / self.root_folder_name

    @property
    def app_data_dir(self) -> Path:
        """Dossier de donnees de l'agent (~/.raguia/) — independant du dossier surveille."""
        d = APP_DATA_DIR
        # mode=0o700 : seul le proprietaire peut lire/ecrire/lister (protege queue.db, state.json)
        d.mkdir(mode=0o700, exist_ok=True)
        return d

    def check_root_exists(self) -> bool:
        """Retourne True si le dossier surveille existe."""
        return self.root_path.is_dir()

    def find_relocated_root(self) -> Path | None:
        """Cherche si le dossier RAGUIA a ete deplace sous le meme parent.
        
        Retourne le nouveau chemin ou None.
        """
        parent = Path(self.watch_parent).expanduser().resolve()
        # Chercher sous le meme parent
        candidate = parent / self.root_folder_name
        if candidate.is_dir():
            return candidate
        # Chercher dans le home si le parent lui-meme a change
        for search_root in [Path.home() / "Documents", Path.home()]:
            candidate2 = search_root / self.root_folder_name
            if candidate2.is_dir():
                return candidate2
        return None


def load_config(path: Path | None = None) -> AgentConfig:
    """Charge la config depuis YAML (plusieurs emplacements) + surcharges env."""
    cfg = AgentConfig()

    # Determine le fichier de config a utiliser
    if path is None:
        env_path = os.environ.get("RAGUIA_AGENT_CONFIG")
        if env_path:
            path = Path(env_path)
        elif (APP_DATA_DIR / "config.yaml").is_file():
            path = APP_DATA_DIR / "config.yaml"
        elif Path("raguia_agent.yaml").is_file():
            path = Path("raguia_agent.yaml")

    if path and path.is_file():
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        for k, v in raw.items():
            if k == "extra":
                continue
            if k == "supported_extensions":
                # Normalise en tuple de str minuscules
                v = tuple(str(e).lower() for e in v) if isinstance(v, list) else v
            if hasattr(cfg, k):
                setattr(cfg, k, v)
            else:
                cfg.extra[k] = v

    # Surcharges par variables d'environnement
    if os.environ.get("RAGUIA_API_BASE"):
        cfg.api_base = os.environ["RAGUIA_API_BASE"].rstrip("/")
    if os.environ.get("RAGUIA_CLIENT_SLUG"):
        cfg.client_slug = os.environ["RAGUIA_CLIENT_SLUG"]
    if os.environ.get("RAGUIA_AGENT_TOKEN"):
        cfg.agent_token = os.environ["RAGUIA_AGENT_TOKEN"]
    if os.environ.get("RAGUIA_WATCH_PARENT"):
        cfg.watch_parent = os.environ["RAGUIA_WATCH_PARENT"]
    if os.environ.get("RAGUIA_DRY_RUN", "").lower() in ("1", "true", "yes"):
        cfg.dry_run = True
    if os.environ.get("RAGUIA_AUTO_UPDATE", "").lower() in ("0", "false", "no"):
        cfg.auto_update = False

    if not cfg.watch_parent:
        cfg.watch_parent = _detect_documents_folder()

    cfg.cfg_path = path

    return cfg


def is_first_launch() -> bool:
    """Retourne True si aucune config n'existe encore."""
    return (
        not (APP_DATA_DIR / "config.yaml").is_file()
        and not Path("raguia_agent.yaml").is_file()
        and not os.environ.get("RAGUIA_AGENT_TOKEN")
    )
