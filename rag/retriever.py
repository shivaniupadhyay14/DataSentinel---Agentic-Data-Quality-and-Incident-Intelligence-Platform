import os
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings

FAISS_PATH = r"C:\Users\user\Desktop\Datasentinel\rag\faiss_index"

# Module-level cache
_vectorstore = None
_embeddings = None


def get_embeddings():
    """Load embedding model once and reuse."""
    global _embeddings

    if _embeddings is None:
        print("Loading embedding model...")

        _embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True}
        )

        print("Embedding model loaded.")

    return _embeddings


def get_vectorstore():
    """Load FAISS index once and cache it."""
    global _vectorstore

    if _vectorstore is None:
        print("Loading FAISS index from disk...")

        _vectorstore = FAISS.load_local(
            FAISS_PATH,
            get_embeddings(),
            allow_dangerous_deserialization=True
        )

        print("FAISS index loaded.")

    return _vectorstore


def retrieve_context(query: str, k: int = 2) -> str:
    """
    Retrieve top-k relevant chunks.
    """

    vectorstore = get_vectorstore()

    results = vectorstore.similarity_search(
        query,
        k=k
    )

    context_parts = []

    for doc in results:
        source = doc.metadata.get("source", "Unknown")

        context_parts.append(
            f"[Source: {source}]\n{doc.page_content}"
        )

    return "\n\n---\n\n".join(context_parts)


if __name__ == "__main__":

    test_queries = [
        "schema drift null rate customer_dest",
        "silent row drop pipeline volume missing"
    ]

    for query in test_queries:
        print(f"\nQuery: {query}")
        print("-" * 50)

        context = retrieve_context(query, k=2)

        print(context[:500])
        print("\n...")