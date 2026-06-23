import os
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

DOCS_PATH = r"C:\Users\user\Desktop\Datasentinel\rag\documents"
FAISS_PATH = r"C:\Users\user\Desktop\Datasentinel\rag\faiss_index"


def load_documents():
    documents = []
    for filename in os.listdir(DOCS_PATH):
        if filename.endswith('.txt'):
            filepath = os.path.join(DOCS_PATH, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            documents.append(Document(
                page_content=content,
                metadata={"source": filename}
            ))
            print(f"Loaded: {filename} ({len(content)} characters)")
    return documents


def chunk_documents(documents):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
        separators=["\n\n", "\n", " "]
    )
    chunks = splitter.split_documents(documents)
    print(f"Split into {len(chunks)} chunks")
    return chunks


def get_embeddings():
    """
    Local embedding model — runs on your machine, zero API calls,
    zero timeouts. Downloads once (~90MB), cached locally after that.
    all-MiniLM-L6-v2 is the standard choice: fast, small, good quality.
    """
    print("Loading local embedding model (downloads once, ~90MB)...")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True}
    )
    print("Local embedding model ready.")
    return embeddings


def build_faiss_index(chunks, embeddings):
    print(f"Embedding {len(chunks)} chunks locally...")
    vectorstore = FAISS.from_documents(chunks, embeddings)
    vectorstore.save_local(FAISS_PATH)
    print(f"FAISS index saved to {FAISS_PATH}")
    return vectorstore


def build_knowledge_base(force_rebuild=False):
    print("=" * 50)
    print("Building RAG Knowledge Base")
    print("=" * 50)

    if os.path.exists(FAISS_PATH) and not force_rebuild:
        print("FAISS index already exists. Skipping rebuild.")
        return None

    documents = load_documents()
    chunks = chunk_documents(documents)
    embeddings = get_embeddings()
    vectorstore = build_faiss_index(chunks, embeddings)

    print("\nKnowledge base built successfully.")
    print(f"Total documents: {len(documents)}")
    print(f"Total chunks indexed: {len(chunks)}")
    return vectorstore


if __name__ == "__main__":
    build_knowledge_base()