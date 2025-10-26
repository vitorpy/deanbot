"""RAG system for Solana/Anchor knowledge base."""

import os
from pathlib import Path
from typing import Optional

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.tools import BaseTool
from pydantic import BaseModel, Field


class RAGQuerySchema(BaseModel):
    """Schema for RAG queries."""

    query: str = Field(..., description="Search query for Solana/Anchor knowledge base")


class KnowledgeBaseRAG:
    """RAG system for Solana/Anchor examples and documentation."""

    def __init__(self, kb_dir: str = "kb", persist_dir: str = ".chroma_db"):
        """Initialize RAG system.

        Args:
            kb_dir: Knowledge base directory path
            persist_dir: ChromaDB persistence directory
        """
        self.kb_dir = Path(kb_dir)
        self.persist_dir = persist_dir
        self.vectorstore: Optional[Chroma] = None

    def load_and_index(self):
        """Load documents and create vector store."""
        print("🔍 Loading knowledge base...")

        # Load Rust source files (Anchor programs)
        rust_loader = DirectoryLoader(
            str(self.kb_dir),
            glob="**/*.rs",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
            show_progress=True,
        )
        rust_docs = rust_loader.load()

        # Load markdown files (documentation)
        md_loader = DirectoryLoader(
            str(self.kb_dir),
            glob="**/*.md",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
            show_progress=True,
        )
        md_docs = md_loader.load()

        print(f"📚 Loaded {len(rust_docs)} Rust files, {len(md_docs)} markdown files")

        # Split code with language-aware splitter
        rust_splitter = RecursiveCharacterTextSplitter.from_language(
            language="rust", chunk_size=2000, chunk_overlap=200
        )
        rust_chunks = rust_splitter.split_documents(rust_docs)

        # Split markdown
        md_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        md_chunks = md_splitter.split_documents(md_docs)

        all_chunks = rust_chunks + md_chunks
        print(f"✂️  Created {len(all_chunks)} chunks")

        # Create embeddings (using local model)
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

        # Create vector store
        print("💾 Creating vector store...")
        self.vectorstore = Chroma.from_documents(
            documents=all_chunks, embedding=embeddings, persist_directory=self.persist_dir
        )

        print(f"✅ Indexed {len(all_chunks)} chunks into ChromaDB")

    def load_existing(self):
        """Load existing vector store from disk."""
        if not Path(self.persist_dir).exists():
            raise FileNotFoundError(f"No existing vector store at {self.persist_dir}")

        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

        self.vectorstore = Chroma(
            persist_directory=self.persist_dir, embedding_function=embeddings
        )
        print(f"✅ Loaded existing vector store from {self.persist_dir}")

    def query(self, query: str, k: int = 3) -> str:
        """Query the knowledge base.

        Args:
            query: Search query
            k: Number of results to return

        Returns:
            Formatted results
        """
        if not self.vectorstore:
            return "Error: Vector store not initialized"

        results = self.vectorstore.similarity_search(query, k=k)

        if not results:
            return "No relevant information found in knowledge base."

        formatted = []
        for i, doc in enumerate(results, 1):
            source = doc.metadata.get("source", "Unknown")
            formatted.append(f"--- Result {i} (from {source}) ---\n{doc.page_content}\n")

        return "\n".join(formatted)

    def get_retriever_tool(self) -> BaseTool:
        """Get LangChain tool for RAG queries."""

        class RAGTool(BaseTool):
            """Tool to search Solana/Anchor knowledge base."""

            name: str = "search_knowledge_base"
            description: str = (
                "Search the Solana/Anchor knowledge base for examples and documentation. "
                "Use this to find similar code patterns, understand Anchor concepts, or get examples. "
                "Query examples: 'anchor vault program', 'pinocchio optimization', 'PDAs and seeds'"
            )
            args_schema: type[BaseModel] = RAGQuerySchema

            rag_system: "KnowledgeBaseRAG"

            class Config:
                arbitrary_types_allowed = True

            def _run(self, query: str) -> str:
                """Search knowledge base."""
                return self.rag_system.query(query, k=3)

            async def _arun(self, query: str) -> str:
                """Async version."""
                return self._run(query)

        return RAGTool(rag_system=self)


def initialize_rag(force_reindex: bool = False) -> KnowledgeBaseRAG:
    """Initialize RAG system, loading or creating index.

    Args:
        force_reindex: If True, rebuild index even if it exists

    Returns:
        Initialized RAG system
    """
    rag = KnowledgeBaseRAG()

    if force_reindex or not Path(rag.persist_dir).exists():
        rag.load_and_index()
    else:
        rag.load_existing()

    return rag
