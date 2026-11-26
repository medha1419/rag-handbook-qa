# How to explain the architecture

## The 60-second walkthrough (say this while pointing at diagram 1)

1. "The system has three stages. **Ingestion** runs once. **Query** runs for every question. **Evaluation** runs the query stage on 50 test questions and scores it."
2. "**Ingestion:** I load the 54-page handbook with PyMuPDF. I remove the repeated page header and the table-of-contents page. I convert the 6 pages of tables into sentences. Then I cut the text into about 136 chunks, embed each chunk into a 384-number vector, and store the vectors in FAISS."
3. "**Query:** the question is embedded with the *same* model. FAISS finds the 4 closest chunks by cosine similarity. Those 4 chunks and the question go to the Groq LLM with an instruction to answer only from the handbook. I time retrieval and generation separately."
4. "**Evaluation:** 50 questions with my own reference answers, run once per embedding model. Ragas scores context precision and faithfulness, using Gemini as the judge so the generator isn't grading itself."

## Likely questions and your answers

**Why FAISS and not ChromaDB?**
One static document gives about 136 vectors. FAISS does exact search in milliseconds, inside the Python process, with no server. Chroma's advantages (metadata filtering, a persistent database, easy updates) matter for many documents that change. Here they add setup and no benefit. Also, comparing two embedding models in FAISS is just two index files.

**Why 180 words per chunk?**
MiniLM silently cuts off input beyond 256 tokens. 180 words is about 240 tokens, so nothing is lost. Both models get the same chunks, so the comparison is fair.

**Why not a fixed-size splitter, like every 500 characters?**
The handbook's sections range from 61 to 2,603 words. A fixed window would mix two policies in one chunk, or cut a rule in half. I split on the 32 TOC headings first, then on the numbered clauses (1., 4.1, a.), because the policies are already written as self-contained clauses.

**Why prefix each chunk with its section title?**
"Scope" appears as a sub-heading 8 times, and "Deviation/Exception" 11 times, in different policies. A chunk that says "2. Scope: all permanent employees" could belong to any policy. With "[SHIFT POLICY] p.17" in front, both the embedding and the LLM know which policy it is.

**Why the 30-word overlap?**
If a rule is longer than a chunk, the overlap means its end still appears with its start in the next chunk. Without overlap, a rule split across a boundary is half-missing from both chunks.

**Why convert tables?**
Plain extraction scrambles table cells. For example, the shift allowance table comes out as "Type / Night Shift / Onsite Shift Working / INR 1000". Converting each row to "Header: value" sentences keeps the facts readable. They are good test questions (travel booking deadlines, travel class by rank).

**Why k = 4?**
A chunk is about 170 words, and most answers sit in one clause. 4 chunks (about 700 words) also cover questions that span clauses, without filling the prompt with unrelated text.

**Why must the query use the same embedding model?**
Each model has its own vector space. A MiniLM query vector compared with bge chunk vectors is meaningless, even though both have 384 numbers.

**What are context precision and faithfulness?**
- *Context precision:* of the retrieved chunks, how many are actually relevant, and are the relevant ones ranked first? This measures **retrieval**.
- *Faithfulness:* the judge splits the answer into claims and checks how many of them the retrieved context supports. This measures **hallucination**.

**Why include out-of-scope questions?**
To check that the system says "not in the handbook" instead of making something up.

**What would you improve next?**
Hybrid search (BM25 keyword search plus vectors) for exact terms like "INR 1000" or policy names. A re-ranker on the top 10 results. Test k = 3 and k = 5.

## Words to use correctly

| Term | Meaning in one line |
|---|---|
| Embedding | A list of numbers (384 here) that represents a text's meaning; similar texts get nearby vectors |
| Cosine similarity | Angle-based closeness of two vectors. With normalised vectors it equals the inner product, which is why `IndexFlatIP` works |
| `IndexFlatIP` | A FAISS index that compares the query with every vector exactly (no approximation) |
| Chunk overlap | Words repeated at the end of one chunk and the start of the next |
| Grounding | Making the LLM answer only from the retrieved text |
