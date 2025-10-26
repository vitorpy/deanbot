#!/usr/bin/env python3
"""Build the knowledge base RAG index."""

import sys
sys.path.insert(0, "src")

from rag import initialize_rag

if __name__ == "__main__":
    print("🔨 Building knowledge base index...")
    rag = initialize_rag(force_reindex=True)
    print("✅ Done! Index saved to .chroma_db/")
