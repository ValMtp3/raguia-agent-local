"""Point d'entree CLI : ``python -m raguia_local_agent`` ou ``raguia-local-agent``."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from pathlib import Path

from .api_client import PortalApiClient
from .config import AgentConfig, is_first_launch, load_config
from .sync_agent import SyncAgent


def test_connection(cfg: AgentConfig) -> bool:
    import httpx
    print(f"Test de connexion vers {cfg.api_base}...")
    try:
        client = PortalApiClient(cfg.api_base, cfg.agent_token)
        st = client.sync_status()
        print("  OK Connecte")
        print(f"  - Sync demandee : {st.get('sync_requested', False)}")
        if st.get("last_sync_at"):
            print(f"  - Derniere sync : {st['last_sync_at']}")
        if st.get("last_error"):
            print(f"  - Derniere erreur : {st['last_error']}")
        return True
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            print("  ERREUR Token invalide ou expire")
        else:
            print(f"  ERREUR HTTP {e.response.status_code}")
        return False
    except Exception as e:
        print(f"  ERREUR {e}")
        return False


def _run_wizard_if_needed(cfg_path: Path | None) -> AgentConfig:
    """Lance le wizard au premier lancement, retourne la config."""
    if is_first_launch():
        print("Premier lancement — ouverture de l'assistant de configuration...")
        try:
            from .wizard import run_wizard
            result = run_wizard()
            if result is None:
                print("Configuration annulee. Arret.")
                sys.exit(0)
        except Exception as e:
            print(f"Wizard indisponible : {e}")
            print("Creez ~/.raguia/config.yaml manuellement.")
            sys.exit(1)
    return load_config(cfg_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent de synchronisation RAGUIA")
    parser.add_argument("-c", "--config", default=None,
                        help="Fichier YAML (defaut : ~/.raguia/config.yaml)")
    parser.add_argument("--test", action="store_true",
                        help="Teste la connexion et quitte")
    parser.add_argument("--no-tray", action="store_true",
                        help="Demarre sans icone systray (mode serveur)")
    args = parser.parse_args()

    logging.basicConfig(
        level=os.environ.get("RAGUIA_LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    cfg_path = Path(args.config) if args.config else None
    cfg = _run_wizard_if_needed(cfg_path)

    if args.test:
        if not cfg.agent_token:
            print("Erreur : agent_token manquant")
            sys.exit(1)
        sys.exit(0 if test_connection(cfg) else 1)

    if not cfg.agent_token:
        logging.error(
            "Jeton agent manquant. Lancez 'raguia-local-agent' sans argument "
            "pour ouvrir l'assistant, ou definissez RAGUIA_AGENT_TOKEN."
        )
        sys.exit(1)

    agent = SyncAgent(cfg)

    # --- Mode sans tray (serveur / terminal) ---
    if args.no_tray:
        try:
            agent.run_forever()
        except KeyboardInterrupt:
            agent.stop()
        return

    # --- Mode avec tray (macOS : tray dans main thread, agent en daemon) ---
    t = threading.Thread(target=agent.run_forever, daemon=True, name="raguia-agent")
    t.start()

    try:
        from .tray import RaguiaTray
        tray = RaguiaTray(agent, on_quit=agent.stop)
        tray.run()          # bloque dans le thread principal (requis sur macOS)
    except ImportError:
        logging.info("pystray/Pillow non disponible — mode sans tray. Ctrl+C pour arreter.")
        try:
            t.join()
        except KeyboardInterrupt:
            agent.stop()


if __name__ == "__main__":
    main()
