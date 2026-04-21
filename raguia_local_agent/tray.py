"""Icone systray cross-platform (pystray + Pillow).

Etats :
  idle     -> cercle vert  (tout va bien)
  syncing  -> cercle bleu  (upload en cours)
  warning  -> cercle orange (token expire bientot, fichiers bloques)
  error    -> cercle rouge  (erreur connexion, token expire)
  stopped  -> cercle gris   (agent arrete)

Necessite : pystray>=0.19, Pillow>=10
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
import time
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .sync_agent import SyncAgent

_COLORS = {
    "idle":    "#22c55e",   # vert
    "syncing": "#3b82f6",   # bleu
    "warning": "#f59e0b",   # orange
    "error":   "#ef4444",   # rouge
    "stopped": "#6b7280",   # gris
}


class TrayStatus(str, Enum):
    IDLE    = "idle"
    SYNCING = "syncing"
    WARNING = "warning"
    ERROR   = "error"
    STOPPED = "stopped"


def _make_icon(color: str, size: int = 64):
    """Genere une image PIL avec un cercle colore."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color,
        outline="#ffffff",
        width=2,
    )
    return img


class RaguiaTray:
    """Icone dans la barre des taches.

    IMPORTANT (macOS) : .run() doit etre appele depuis le thread principal.
    Lancer l'agent dans un thread daemon avant d'appeler run().
    """

    def __init__(
        self,
        agent: "SyncAgent",
        on_quit: Callable[[], None] | None = None,
    ) -> None:
        import pystray
        self._agent = agent
        self._on_quit = on_quit
        self._status = TrayStatus.IDLE
        self._message = ""
        self._icons: dict[str, object] = {}
        self._pystray = pystray
        self._tray: pystray.Icon | None = None

        # Pre-generer les icones
        for name, color in _COLORS.items():
            self._icons[name] = _make_icon(color)

        # L'agent pousse son statut via ce callback
        agent.on_status_change = self._on_agent_status

    # ------------------------------------------------------------------
    # Callback depuis sync_agent (thread background -> thread tray)
    # ------------------------------------------------------------------
    def _on_agent_status(self, status: TrayStatus, message: str = "") -> None:
        self._status = status
        self._message = message
        self._refresh()

    def _refresh(self) -> None:
        if self._tray is None:
            return
        try:
            self._tray.icon  = self._icons[self._status.value]
            self._tray.title = self._title()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------
    def _title(self) -> str:
        labels = {
            TrayStatus.IDLE:    "Raguia — Actif",
            TrayStatus.SYNCING: "Raguia — Synchronisation...",
            TrayStatus.WARNING: f"Raguia — Attention : {self._message}",
            TrayStatus.ERROR:   f"Raguia — Erreur : {self._message}",
            TrayStatus.STOPPED: "Raguia — Arrete",
        }
        return labels.get(self._status, "Raguia")

    def _menu(self):
        pystray = self._pystray

        def open_folder(icon, item):
            import subprocess, sys
            root = self._agent.root
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(root)])
            elif sys.platform == "win32":
                subprocess.Popen(["explorer", str(root)])
            else:
                subprocess.Popen(["xdg-open", str(root)])

        def sync_now(icon, item):
            threading.Thread(
                target=self._agent.force_sync, daemon=True
            ).start()

        def reset_stuck(icon, item):
            n = self._agent.queue.reset_stuck()
            self._on_agent_status(TrayStatus.IDLE, f"{n} fichier(s) remis en file")

        def quit_agent(icon, item):
            self._agent.stop()
            if self._on_quit:
                self._on_quit()
            icon.stop()

        def update_jwt(icon, item):
            try:
                import tkinter as tk
                from tkinter import messagebox, simpledialog
                import yaml
            except Exception:
                self._on_agent_status(TrayStatus.ERROR, "UI JWT indisponible")
                return

            root = tk.Tk()
            root.withdraw()
            try:
                new_token = simpledialog.askstring(
                    "Raguia — Mettre a jour le jeton",
                    "Collez le nouveau jeton JWT agent :",
                    show="*",
                    parent=root,
                )
                if new_token is None:
                    return
                new_token = new_token.strip()
                if not new_token:
                    messagebox.showwarning("Jeton vide", "Aucun jeton saisi.", parent=root)
                    return

                old_token = self._agent.cfg.agent_token
                self._agent.update_agent_token(new_token)
                try:
                    # Validation immediate
                    self._agent.client.sync_status()
                except Exception as e:
                    self._agent.update_agent_token(old_token)
                    messagebox.showerror(
                        "Jeton invalide",
                        f"Le jeton n'a pas ete accepte:\n{e}",
                        parent=root,
                    )
                    return

                cfg_path = os.environ.get("RAGUIA_AGENT_CONFIG")
                if cfg_path:
                    cfg_file = Path(cfg_path)
                else:
                    cfg_file = Path.home() / ".raguia" / "config.yaml"
                cfg_file.parent.mkdir(parents=True, exist_ok=True)

                data = {}
                if cfg_file.is_file():
                    with open(cfg_file, encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                data["agent_token"] = new_token
                with open(cfg_file, "w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
                try:
                    os.chmod(cfg_file, 0o600)
                except Exception:
                    pass

                messagebox.showinfo(
                    "Jeton mis a jour",
                    "Le nouveau jeton est actif immediatement et enregistre.",
                    parent=root,
                )
                self._on_agent_status(TrayStatus.IDLE, "Jeton mis a jour")
            finally:
                root.destroy()

        def uninstall_agent(icon, item):
            try:
                import tkinter as tk
                from tkinter import messagebox
            except Exception:
                self._on_agent_status(TrayStatus.ERROR, "UI desinstallation indisponible")
                return

            root = tk.Tk()
            root.withdraw()
            try:
                ok = messagebox.askyesno(
                    "Raguia — Desinstallation",
                    (
                        "Confirmer la desinstallation complete de l'agent ?\n\n"
                        "- Arret de l'agent\n"
                        "- Suppression du demarrage automatique\n"
                        "- Suppression des fichiers agent/config locaux\n\n"
                        "Le dossier de documents RAGUIA n'est pas supprime."
                    ),
                    icon="warning",
                    parent=root,
                )
                if not ok:
                    return

                cfg_path = os.environ.get("RAGUIA_AGENT_CONFIG")
                cfg_file = Path(cfg_path) if cfg_path else (Path.home() / ".raguia" / "config.yaml")
                agent_dir = cfg_file.parent if cfg_file.name == "raguia_agent.yaml" else None
                app_data_dir = Path.home() / ".raguia"

                # 1) Desactiver le demarrage automatique selon l'OS
                try:
                    if os.name == "nt":
                        startup = Path(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"))
                        lnk = startup / "Raguia Agent.lnk"
                        if lnk.exists():
                            lnk.unlink()
                    elif sys.platform == "darwin":
                        plist = Path.home() / "Library" / "LaunchAgents" / "com.raguia.local.agent.plist"
                        subprocess.run(
                            ["/bin/bash", "-lc", f'launchctl bootout "gui/$(id -u)" "{plist}" 2>/dev/null || launchctl unload "{plist}" 2>/dev/null || true'],
                            check=False,
                        )
                        if plist.exists():
                            plist.unlink()
                    else:
                        unit = Path.home() / ".config" / "systemd" / "user" / "raguia-agent.service"
                        subprocess.run(["systemctl", "--user", "disable", "--now", "raguia-agent.service"], check=False)
                        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
                        if unit.exists():
                            unit.unlink()
                except Exception:
                    pass

                # 2) Programmer la suppression des fichiers apres extinction du process
                to_delete = []
                if agent_dir and agent_dir.name == ".raguia_agent":
                    to_delete.append(agent_dir)
                to_delete.append(app_data_dir)

                if os.name == "nt":
                    quoted = " ".join(f'"{p}"' for p in to_delete)
                    cmd = f'timeout /t 2 /nobreak >nul & for %d in ({quoted}) do if exist "%d" rmdir /s /q "%d"'
                    subprocess.Popen(["cmd", "/c", cmd], creationflags=0x08000000)
                else:
                    quoted = " ".join(shlex.quote(str(p)) for p in to_delete)
                    subprocess.Popen(
                        ["/bin/bash", "-lc", f"sleep 2; rm -rf {quoted}"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )

                messagebox.showinfo(
                    "Desinstallation",
                    "Desinstallation lancee. L'agent va s'arreter.",
                    parent=root,
                )
                quit_agent(icon, item)
            finally:
                root.destroy()

        pending = self._agent.queue.pending_count()
        stuck   = self._agent.queue.stuck_count()
        last_ts = self._agent.queue.last_sync_at()

        last_str = "Jamais"
        if last_ts:
            dt = time.time() - last_ts
            if dt < 60:
                last_str = "Il y a < 1 min"
            elif dt < 3600:
                last_str = f"Il y a {int(dt/60)} min"
            else:
                last_str = f"Il y a {int(dt/3600)} h"

        items = [
            pystray.MenuItem(self._title(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Ouvrir le dossier RAGUIA", open_folder),
            pystray.MenuItem("Synchroniser maintenant", sync_now),
            pystray.MenuItem("Mettre a jour le jeton JWT…", update_jwt),
            pystray.MenuItem("Desinstaller l'agent…", uninstall_agent),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(f"{pending} fichier(s) en attente", None, enabled=False),
            pystray.MenuItem(f"Derniere sync : {last_str}", None, enabled=False),
        ]
        if stuck > 0:
            items += [
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    f"⚠ {stuck} fichier(s) bloques — Reinitialiser", reset_stuck
                ),
            ]
        items += [
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quitter", quit_agent),
        ]
        return pystray.Menu(*items)

    # ------------------------------------------------------------------
    # Lancement (bloque dans le thread appelant — main thread sur macOS)
    # ------------------------------------------------------------------
    def run(self) -> None:
        import pystray
        icon = pystray.Icon(
            "raguia",
            self._icons["idle"],
            title="Raguia",
            menu=pystray.Menu(lambda: self._menu()._items),
        )
        self._tray = icon
        icon.run()
