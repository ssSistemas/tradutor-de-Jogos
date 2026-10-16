"""Portable configuration and private, atomic runtime storage."""
import json
import os
from pathlib import Path
import tempfile
import tomllib

CODE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get('TG_CONFIG', Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'tradutor-de-jogos' / 'config.toml'))
STATE_DIR = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'tradutor-de-jogos'
CONFIG = {
    'model': 'tradutor-de-jogos:4b',
    'context': 'general',
    'cache_entries': 128,
    'min_available_ram_gib': 4,
    'min_free_vram_mib': 5000,
}


def validate(config):
    if set(config) != set(CONFIG):
        raise ValueError('Configuração contém opções desconhecidas ou incompletas.')
    # Only a dedicated, local alias may be unloaded by this app. Cloud/remote
    # names and arbitrary models from other sessions cannot be configured.
    if config['model'] != 'tradutor-de-jogos:4b':
        raise ValueError('Use o alias local dedicado tradutor-de-jogos:4b.')
    if config['context'] not in ('general', 'eve'):
        raise ValueError('context deve ser general ou eve.')
    for name, high in [('cache_entries', 1024), ('min_available_ram_gib', 1024), ('min_free_vram_mib', 1000000)]:
        if type(config[name]) is not int or not 1 <= config[name] <= high:
            raise ValueError('Valor inválido para ' + name)
    return config


if CONFIG_PATH.exists():
    with CONFIG_PATH.open('rb') as stream:
        supplied = tomllib.load(stream)
    if set(supplied) - set(CONFIG):
        raise ValueError('Configuração contém opções desconhecidas.')
    CONFIG.update(supplied)
validate(CONFIG)
STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
STATE_DIR.chmod(0o700)


def write_private(path, value):
    """Never expose a half-written result or create it with public permissions."""
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name, suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)
