from copy import deepcopy
from typing import Any, Dict, List, Optional


DEFAULT_SCRAPER_PRESETS: Dict[str, Dict[str, Any]] = {
    "simak": {
        "domain": "simak.ui.ac.id",
        "folder": "simak",
        "seeds": ["https://simak.ui.ac.id/"],
        "allowed_paths": ["/"],
        "disallowed_paths": [
            r"/wp-admin",
            r"/wp-login\.php",
            r"/xmlrpc\.php",
            r"[?&]replytocom=",
        ],
        "max_depth": 4,
        "max_parallelism": 2,
        "rate_limit_ms": 1000,
        "user_agent": "UI-RAG-Scraper/1.0",
        "skip_existing": True,
        "dry_run": False,
        "output_dir": "/app/data",
    },
    "ui_ac_id": {
        "domain": "www.ui.ac.id",
        "folder": "ui_ac_id",
        "seeds": ["https://www.ui.ac.id/"],
        "allowed_paths": ["/"],
        "disallowed_paths": [
            r"/wp-admin",
            r"/wp-login\.php",
            r"/xmlrpc\.php",
            r"[?&]replytocom=",
        ],
        "max_depth": 4,
        "max_parallelism": 2,
        "rate_limit_ms": 1000,
        "user_agent": "UI-RAG-Scraper/1.0",
        "skip_existing": True,
        "dry_run": False,
        "output_dir": "/app/data",
    },
    "kemahasiswaan": {
        "domain": "kemahasiswaan.ui.ac.id",
        "folder": "kemahasiswaan",
        "seeds": ["https://kemahasiswaan.ui.ac.id/"],
        "allowed_paths": ["/"],
        "disallowed_paths": [
            r"/wp-admin",
            r"/wp-login\.php",
            r"/xmlrpc\.php",
            r"[?&]replytocom=",
        ],
        "max_depth": 4,
        "max_parallelism": 2,
        "rate_limit_ms": 1000,
        "user_agent": "UI-RAG-Scraper/1.0",
        "skip_existing": True,
        "dry_run": False,
        "output_dir": "/app/data",
    },
    "beasiswa": {
        "domain": "beasiswa.ui.ac.id",
        "folder": "beasiswa",
        "seeds": ["https://beasiswa.ui.ac.id/web/"],
        "allowed_paths": [],
        "disallowed_paths": [
            r"/wp-admin",
            r"/wp-login\.php",
            r"/xmlrpc\.php",
            r"[?&]replytocom=",
        ],
        "max_depth": 4,
        "max_parallelism": 2,
        "rate_limit_ms": 1000,
        "user_agent": "UI-RAG-Scraper/1.0",
        "skip_existing": True,
        "dry_run": False,
        "output_dir": "/app/data",
    },
    "penerimaan": {
        "domain": "penerimaan.ui.ac.id",
        "folder": "penerimaan",
        "seeds": ["https://penerimaan.ui.ac.id/"],
        "allowed_paths": ["/"],
        "disallowed_paths": [
            r"/user",
            r"/register",
            r"/recovery",
        ],
        "max_depth": 4,
        "max_parallelism": 2,
        "rate_limit_ms": 1000,
        "user_agent": "UI-RAG-Scraper/1.0",
        "skip_existing": True,
        "dry_run": False,
        "output_dir": "/app/data",
    },
    "enrollment": {
        "domain": "enrollment.ui.ac.id",
        "folder": "enrollment",
        "seeds": ["https://enrollment.ui.ac.id/"],
        "allowed_paths": ["/"],
        "disallowed_paths": [],
        "max_depth": 3,
        "max_parallelism": 1,
        "rate_limit_ms": 1000,
        "user_agent": "UI-RAG-Scraper/1.0",
        "skip_existing": True,
        "dry_run": False,
        "output_dir": "/app/data",
    },
}


def list_presets() -> Dict[str, Dict[str, Any]]:
    return deepcopy(DEFAULT_SCRAPER_PRESETS)


def get_preset(name: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if name not in DEFAULT_SCRAPER_PRESETS:
        raise KeyError(name)
    preset = deepcopy(DEFAULT_SCRAPER_PRESETS[name])
    for key, value in (overrides or {}).items():
        if value is not None:
            preset[key] = value
    return preset


def preset_names() -> List[str]:
    return sorted(DEFAULT_SCRAPER_PRESETS)
