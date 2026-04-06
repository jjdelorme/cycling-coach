# Upgrading AI Coach Memory to pgvector (RAG)

## Objective
Migrate the current AI Coach memory system (`DbMemoryService`) from a naive exact-keyword matching algorithm to a Retrieval-Augmented Generation (RAG) architecture using semantic vector embeddings and PostgreSQL's `pgvector` extension.

This will allow the ADK agent to recall previous conversations based on *meaning* rather than exact words, drastically improving the coaching experience.

## Phase 1: Infrastructure & Database Updates

1. **Update Local Development Container:**
   Modify the local PostgreSQL container to use an image that includes the `pgvector` extension.
   *Current command (AGENTS.md):*
   `podman run -d --name coach-db -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust docker.io/library/postgres:16-alpine`
   *New command:*
   `podman run -d --name coach-db -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust docker.io/pgvector/pgvector:pg16`

2. **Update Integration Test Container:**
   Update `scripts/run_integration_tests.sh` to use `pgvector/pgvector:pg16` for the `coach-test-db` container so that integration tests have access to the `vector` extension.

3. **Database Migration Script:**
   Create a new SQL migration script (e.g., `scripts/migrate_add_pgvector_memory.sql`) with the following operations:
   ```sql
   -- Enable the pgvector extension
   CREATE EXTENSION IF NOT EXISTS vector;

   -- Add an embedding column to the coach_memory table
   -- Note: 768 is our explicit truncated dimension size for the gemini-embeddings-002 model
   ALTER TABLE coach_memory ADD COLUMN IF NOT EXISTS embedding vector(768);

   -- Optional but recommended: Create an HNSW index for faster similarity searches
   CREATE INDEX ON coach_memory USING hnsw (embedding vector_cosine_ops);
   ```

## Phase 2: Implement Embedding Generation

1. **Add Embedding Utility:**
   In `server/coaching/` (or a new `server/llm/embeddings.py` file), create a utility function to generate embeddings using the Google GenAI SDK.
   
   **CRITICAL NOTE FOR IMPLEMENTATION:** 
   You MUST use the `gemini-embeddings-002` model. This model has a default output dimensionality of >3000, which is unnecessarily large for our application and will cause performance/storage bloat. You **MUST explicitly set `output_dimensionality=768`** in the `EmbedContentConfig` to reduce the vector size. Do not rely on older knowledge defaults.

   ```python
   from google import genai
   from google.genai.types import EmbedContentConfig

   def generate_embedding(text: str) -> list[float]:
       # Ensure ADC (Application Default Credentials) is utilized
       client = genai.Client()
       
       response = client.models.embed_content(
           model="gemini-embeddings-002",
           contents=text,
           config=EmbedContentConfig(
               task_type="RETRIEVAL_DOCUMENT",
               output_dimensionality=768  # MUST BE EXACTLY 768
           )
       )
       return response.embeddings[0].values
   ```

## Phase 3: Update `DbMemoryService` (Ingestion)

Modify the `add_session_to_memory` method in `server/coaching/memory_service.py`:
1.  Extract the `content_text` from the session events (as it currently does).
2.  Pass the `content_text` to your new `generate_embedding()` function.
3.  Update the SQL `INSERT` statement to include the generated embedding vector.

```python
# Updated SQL execution
conn.execute(
    "INSERT INTO coach_memory (user_id, author, content_text, timestamp, embedding) VALUES (%s, %s, %s, %s, %s)",
    (session.user_id, author, content_text, now, embedding_vector),
)
```

## Phase 4: Update `DbMemoryService` (Retrieval/Search)

Modify the `search_memory` method in `server/coaching/memory_service.py`:
1.  Remove the naive Python regex keyword matching logic (`_extract_words_lower`).
2.  Generate an embedding vector for the incoming `query` string.
3.  Use `pgvector`'s cosine distance operator (`<=>`) directly in the SQL query to find the most semantically similar memories.
4.  Limit the results to the top `K` most relevant entries (e.g., `LIMIT 10` or `LIMIT 20`) to avoid blowing out the context window.

```python
# Updated SQL query
rows = conn.execute(
    """
    SELECT content_text, author, timestamp 
    FROM coach_memory 
    WHERE user_id = %s 
    ORDER BY embedding <=> %s 
    LIMIT 15
    """,
    (user_id, query_embedding_vector),
).fetchall()
```

## Phase 5: Backfill Existing Memories (Optional)

Create a script `scripts/backfill_memory_embeddings.py`:
1.  Connect to the database and select all rows from `coach_memory` where `embedding IS NULL`.
2.  Iterate through the rows, call the embedding API for `content_text`, and update the row with the new vector.
3.  Add a sleep/delay to respect Vertex AI quota limits.

## Phase 6: Testing & Validation

1. **Run Unit Tests:** `pytest tests/unit/`
2. **Run Integration Tests:** `./scripts/run_integration_tests.sh` to ensure the new DB schema and pgvector search logic functions correctly without regressions.
3. **Manual Verification:** Start the dev server (`./scripts/dev.sh`). Ask the AI coach a conceptual question about a past conversation (using synonyms, not exact keywords) to verify it successfully retrieves the memory via semantic match.
