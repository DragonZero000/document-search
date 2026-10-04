"""Генерирует docs.json из схемы OpenAPI приложения.

Запуск: python -m scripts.export_openapi
"""

import json
from pathlib import Path

from app.main import create_app

DOCS_PATH = Path(__file__).resolve().parent.parent / "docs.json"


def render() -> str:
    return json.dumps(create_app().openapi(), ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    DOCS_PATH.write_text(render(), encoding="utf-8")
    print(f"Written {DOCS_PATH}")


if __name__ == "__main__":
    main()
