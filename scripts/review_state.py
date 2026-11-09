"""State preparation exclusively for isolated source review launchers."""
import json

import user_data


def prepare_isolated_history():
    """Block legacy browser fallbacks before any app/server import or exposure.

    A valid empty history is authoritative for OBSState's independent legacy
    fallback readers. Preserve an existing review's history; fail closed if it
    is corrupt rather than letting those readers fall through to checkout data.
    """
    user_data.legacy_data_dirs = lambda: []
    path = user_data.get_data_dir() / user_data.HISTORY_NAME
    if path.exists():
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Isolated review history must be a JSON object.')
        if not isinstance(data.get('bag') or [], list):
            raise ValueError('Isolated review bag must be a list.')
        if not isinstance(data.get('sessions') or [], list):
            raise ValueError('Isolated review sessions must be a list.')
    else:
        user_data.atomic_write_json(path, {'sessions': [], 'bag': []})
    return path
