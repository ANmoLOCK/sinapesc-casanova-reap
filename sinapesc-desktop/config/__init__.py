"""Persistência local de configuração (credenciais + login admin)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

APP_NAME = "SinapescREAP"
CREDENTIALS_FILENAME = "google-credentials.json"
CONFIG_FILENAME = "config.json"


def app_data_dir() -> Path:
    """Pasta de dados do usuário (Windows: %APPDATA%\\SinapescREAP)."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def exe_dir() -> Path:
    """Pasta onde está o .exe (ou a pasta do projeto em modo desenvolvimento)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    """Prefere config.json ao lado do .exe; senão usa AppData."""
    beside_exe = exe_dir() / CONFIG_FILENAME
    if beside_exe.exists():
        return beside_exe
    return app_data_dir() / CONFIG_FILENAME


def credentials_path_candidates() -> list[Path]:
    """Locais onde o JSON da Conta de Serviço pode estar."""
    return [
        exe_dir() / CREDENTIALS_FILENAME,
        app_data_dir() / CREDENTIALS_FILENAME,
    ]


DEFAULT_CONFIG: Dict[str, Any] = {
    "spreadsheet_id": "",
    "defeso_spreadsheet_id": "1UxDjb78h7tYUnKXPcLVniuqAfWwrbvyf",
    "defeso_drive_folder_id": "",
    "defeso_anexos_dir": "",
    "defeso_declaracao_fonte": "padrao",
    "service_account_email": "",
    "private_key": "",
    "credentials_json": None,
    "admin_email": "admin@sinapesc.local",
    "admin_password": "sinapesc",
    "public_base_url": "",
    "public_site_url": "",
    "public_port": 8765,
    "keep_tunnel_alive": True,
    "auto_start_tunnel": False,
    "ultimo_backup_em": "",
    "backup_adiado_em": "",
}



def _apply_credentials_file(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Se existir google-credentials.json ao lado do .exe (ou em AppData),
    carrega automaticamente — assim a API já fica integrada sem abrir a tela.
    """
    if isinstance(cfg.get("credentials_json"), dict):
        return cfg
    for path in credentials_path_candidates():
        if not path.exists():
            continue
        try:
            data = import_credentials_file(path)
        except (ValueError, OSError, json.JSONDecodeError):
            continue
        cfg["credentials_json"] = data
        cfg["service_account_email"] = data.get("client_email", "")
        cfg["private_key"] = data.get("private_key", "")
        break
    return cfg


def load_config() -> Dict[str, Any]:
    path = config_path()
    merged = dict(DEFAULT_CONFIG)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                merged.update(data)
        except (json.JSONDecodeError, OSError):
            pass
    return _apply_credentials_file(merged)


def save_config(cfg: Dict[str, Any]) -> None:
    """Salva em AppData (não sobrescreve o config.json ao lado do .exe sem querer)."""
    path = app_data_dir() / CONFIG_FILENAME
    # Não grava a chave privada duplicada se já temos o arquivo JSON ao lado do exe
    to_save = dict(cfg)
    path.write_text(json.dumps(to_save, ensure_ascii=False, indent=2), encoding="utf-8")


def is_sheets_configured(cfg: Optional[Dict[str, Any]] = None) -> bool:
    cfg = cfg or load_config()
    if not cfg.get("spreadsheet_id"):
        return False
    if isinstance(cfg.get("credentials_json"), dict):
        return True
    return bool(cfg.get("service_account_email") and cfg.get("private_key"))


def import_credentials_file(json_path: str | Path) -> Dict[str, Any]:
    """Lê o arquivo JSON baixado do Google Cloud e devolve o dict."""
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("type") != "service_account":
        raise ValueError(
            "Arquivo inválido. Selecione o JSON da Conta de Serviço do Google Cloud."
        )
    if "client_email" not in data or "private_key" not in data:
        raise ValueError("JSON incompleto: faltam client_email ou private_key.")
    return data
