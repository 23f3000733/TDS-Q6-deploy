import os
from pathlib import Path

import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = Path(__file__).resolve().parent

DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

ALIASES = {"num_workers": "workers"}
TRUE_VALUES = {"true", "1", "yes", "on"}

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def norm_key(key: str) -> str:
    """Lowercase, trim, and resolve aliases (NUM_WORKERS -> workers)."""
    key = key.strip().lower()
    return ALIASES.get(key, key)


def strip_app_prefix(key: str) -> str:
    return key[4:] if key.upper().startswith("APP_") else key


def load_yaml_layer() -> dict:
    env_name = os.environ.get("APP_ENV", "development")
    path = BASE_DIR / f"config.{env_name}.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return {norm_key(str(k)): v for k, v in data.items()}


def load_dotenv_layer() -> dict:
    # dotenv_values reads the file WITHOUT touching os.environ,
    # so this layer stays separate from the OS env layer.
    values = dotenv_values(BASE_DIR / ".env")
    return {
        norm_key(strip_app_prefix(k)): v
        for k, v in values.items()
        if v is not None
    }


def load_os_env_layer() -> dict:
    return {
        norm_key(k[4:]): v
        for k, v in os.environ.items()
        if k.upper().startswith("APP_")
    }


def parse_overrides(request: Request) -> dict:
    out = {}
    for item in request.query_params.getlist("set"):
        key, sep, value = item.partition("=")  # split on FIRST '=' only
        if sep and key.strip():
            out[norm_key(key)] = value
    return out


def coerce(key: str, value):
    if key in ("port", "workers"):
        return int(str(value).strip())
    if key == "debug":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in TRUE_VALUES
    return str(value)


@app.get("/effective-config")
def effective_config(request: Request):
    merged = dict(DEFAULTS)
    merged.update(load_yaml_layer())       # config.<env>.yaml
    merged.update(load_dotenv_layer())     # .env
    merged.update(load_os_env_layer())     # OS APP_* env
    merged.update(parse_overrides(request))  # ?set=key=value (highest)

    result = {k: coerce(k, v) for k, v in merged.items() if k != "env"}
    result["api_key"] = "****"  # never expose the real secret
    return result