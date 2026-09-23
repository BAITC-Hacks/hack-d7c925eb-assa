"""Small server-only configuration loader; never exposes environment values to the API."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    # Explicit process variables win. Backend overrides the legacy frontend key location.
    for path in (ROOT / 'backend' / '.env', ROOT / '.env', ROOT / 'frontend' / '.env'):
        if not path.is_file():
            continue
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            name, sep, value = line.strip().partition('=')
            if sep and (name.startswith('CQ_') or name in {'OPENAI_API_KEY', 'OPENAI_MODEL'}):
                os.environ.setdefault(name, value.strip().strip('\"\''))


load_env()


def demo_mode() -> bool:
    return os.getenv('CQ_MODE', 'demo') == 'demo'


def external_enabled() -> bool:
    return os.getenv('CQ_ALLOW_EXTERNAL_AI', 'false').lower() == 'true' and bool(os.getenv('OPENAI_API_KEY'))


def model_name() -> str:
    return os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')
