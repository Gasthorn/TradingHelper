"""Chargement et validation de la configuration (`config/*.yaml`).

Aucun appel réseau ici (R9) : la validation porte uniquement sur le contenu des fichiers.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from yaml.nodes import MappingNode


class ConfigError(Exception):
    """Erreur de configuration lisible : fichier + champ + raison (R8)."""

    def __init__(self, file: Path, field: str | None, reason: str) -> None:
        self.file = file
        self.field = field
        self.reason = reason
        # as_posix : message identique sous Windows et en CI Linux.
        location = f"{file.as_posix()}: {field}" if field else file.as_posix()
        super().__init__(f"{location}: {reason}")


class _DuplicateKeyError(yaml.YAMLError):
    def __init__(self, key: str, line: int) -> None:
        super().__init__(key)
        self.key = key
        self.line = line


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader qui refuse les clés dupliquées (PyYAML garde sinon la dernière en silence)."""

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[object, object]:
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise _DuplicateKeyError(str(key), key_node.start_mark.line + 1)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _read_yaml(path: Path) -> dict[str, object]:
    """Lit un fichier YAML dont la racine doit être un mapping non vide.

    Lève `ConfigError` si le fichier est absent, vide, mal formé, a une clé dupliquée,
    ou si sa racine n'est pas un mapping.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(path, None, "fichier introuvable") from None

    try:
        data = yaml.load(text, Loader=_StrictLoader)  # _StrictLoader dérive de SafeLoader
    except _DuplicateKeyError as exc:
        raise ConfigError(path, exc.key, f"clé dupliquée (ligne {exc.line})") from None
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (ligne {mark.line + 1})" if mark is not None else ""
        raise ConfigError(path, None, f"YAML invalide{where}") from None

    if data is None:
        raise ConfigError(path, None, "fichier vide")
    if not isinstance(data, dict):
        raise ConfigError(path, None, f"la racine doit être un mapping, pas {type(data).__name__}")
    return {str(k): v for k, v in data.items()}
