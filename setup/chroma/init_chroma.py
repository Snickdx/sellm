"""
Initialize/warm the local ChromaDB store from Excel data.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rag_backend import RequirementsRAG


def main() -> int:
    load_dotenv()
    excel_file = os.getenv("EXCEL_FILE", "data.xlsx")
    chroma_path = os.getenv("CHROMA_PERSIST_DIRECTORY", "./storage/chroma_db_v2")

    print("Initializing ChromaDB...")
    print(f"Excel file: {excel_file}")
    print(f"Persist path: {chroma_path}")

    rag = RequirementsRAG(excel_file=excel_file, persist_directory=chroma_path)
    print(f"ChromaDB ready. Document count: {rag.collection.count()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
