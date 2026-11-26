# System Architecture — Q&A on BOLD Employee Handbook (RAG)

Source document: *Employee Handbook v2025-26* — 54 pages, ~17,800 words, 32 TOC headings, 6 pages with tables.

| # | Diagram | Answers the question |
|---|---|---|
| 1 | Component diagram | What are the parts, and how does data flow through them? |
| 2 | Chunking activity diagram | How exactly is the handbook cut into chunks? |
| 3 | Sequence diagram | What happens, in order, when one question is answered? |
| 4 | Class diagram | How is the code organised? |

---

## 1. Component diagram

```mermaid
flowchart TB
    subgraph ING["① Offline ingestion — runs once per embedding model (load_clean.py, ingest.py)"]
        direction LR
        PDF[/"Employee Handbook<br/>v2025-26 PDF, 54 pages"/] --> LOAD["Loader<br/>PyMuPDF text +<br/>find_tables()"]
        LOAD --> CLEAN["Cleaner<br/>drop page header/footer,<br/>TOC page, cover table"]
        CLEAN --> TAB["Table converter<br/>rows → 'Header: value'<br/>sentences"]
        TAB --> SPLIT["Section-aware chunker<br/>32 TOC headings,<br/>≤180 words, 30 overlap"]
        SPLIT --> EMB1["Embedding model<br/>A: all-MiniLM-L6-v2<br/>B: bge-small-en-v1.5"]
    end

    EMB1 --> VS[("FAISS IndexFlatIP x 2<br/>~136 vectors each<br/>+ chunks.json")]

    subgraph QRY["② Online query — generate(query, model) (rag.py)"]
        direction LR
        Q[/"Employee question"/] --> EMB2["Embed query<br/>same model as index"]
        EMB2 --> RET["Retriever<br/>cosine, top-k = 4"]
        RET --> PROMPT["Prompt builder<br/>4 chunks + 'answer only<br/>from the handbook' rule"]
        PROMPT --> LLM["Generator LLM<br/>Groq API"]
        LLM --> ANS[/"Answer + cited<br/>section and page"/]
    end

    VS --> RET

    subgraph EVAL["③ Evaluation (evaluate.py, plots.py)"]
        direction LR
        TS[/"50 questions + reference<br/>answers (incl. 6 out-of-scope)"/] --> RUN["Batch run x 2 models<br/>log Q, contexts, answer,<br/>retrieval_ms, generation_ms"]
        RUN --> RAGAS["Ragas, judge = Gemini<br/>context precision,<br/>faithfulness"]
        RAGAS --> REP[/"Report: model A vs B,<br/>latency plots, samples"/]
    end

    RUN -. calls .-> Q
```

---

## 2. Chunking activity diagram

```mermaid
flowchart TD
    A(["Cleaned text, 53 pages"]) --> B["Split on the 32 TOC headings<br/>→ 30 non-empty sections"]
    B --> C{"Section ≤ 180 words?"}
    C -- "yes (11 sections)" --> D["Keep whole section<br/>as one chunk"]
    C -- "no (19 sections)" --> E["Split at numbered clauses<br/>'1.', '4.1', 'a.'"]
    E --> F{"Clause ≤ 180 words?"}
    F -- yes --> G["Pack consecutive clauses<br/>into chunks ≤ 180 words"]
    F -- no --> H["Sliding window:<br/>180 words, 30 overlap"]
    D --> I["Prefix every chunk with<br/>'[SECTION TITLE] p.N'"]
    G --> I
    H --> I
    I --> J(["~136 chunks → chunks.json"])
```

---

## 3. Sequence diagram — one call to `generate(query, model)`

```mermaid
sequenceDiagram
    autonumber
    actor U as Employee
    participant G as generate()
    participant E as Embedding model (A or B)
    participant V as FAISS index (A or B)
    participant M as chunks.json
    participant L as Groq LLM

    U->>G: query, model
    Note over G: start retrieval timer
    G->>E: encode(query)
    E-->>G: 384-dim vector (normalised)
    G->>V: search(vector, k=4)
    V-->>G: 4 chunk ids + cosine scores
    G->>M: look up ids
    M-->>G: chunk text + section + page
    Note over G: stop retrieval timer
    Note over G: start generation timer
    G->>L: system rule + 4 chunks + query
    L-->>G: answer text
    Note over G: stop generation timer
    G-->>U: answer + sources + timings
```

---

## 4. Class diagram — code modules

```mermaid
classDiagram
    direction LR

    class load_clean {
        +load_pages(pdf_path) list
        +find_repeated_lines(pages) set
        +is_toc_page(text) bool
        +tables_to_text(page) str
        +clean_page(text, repeated) str
        +load_and_clean(pdf_path) list
    }

    class ingest {
        +MAX_WORDS : int = 180
        +OVERLAP_WORDS : int = 30
        +EMBED_MODELS : dict
        +split_sections(pages) list
        +chunk_section(section) list
        +embed_chunks(chunks, model) ndarray
        +build_index(vectors) faiss.Index
        +save(index, chunks, model)
    }

    class rag {
        +TOP_K : int = 4
        +GROQ_MODEL : str
        +load_index(model) faiss.Index
        +retrieve(query, model, k) list
        +build_prompt(query, chunks) str
        +generate(query, model) dict
    }

    class evaluate {
        +JUDGE_MODEL : str
        +load_questions(path) list
        +run_batch(questions, model) DataFrame
        +score_with_ragas(df) DataFrame
        +compare_models() DataFrame
    }

    class plots {
        +plot_latency(df)
        +plot_metrics_by_model(df)
    }

    load_clean <.. ingest : uses
    ingest ..> rag : FAISS indexes + chunks.json
    rag <.. evaluate : calls generate()
    evaluate ..> plots : results.csv
```

---

## Design decisions and evidence from the handbook

| Decision | Value | Why (evidence from this handbook) |
|---|---|---|
| Loader | PyMuPDF + `find_tables()` | The PDF is born-digital (exported from Word), so no OCR is needed. 6 pages contain tables. |
| Cleaning | Remove repeated header, TOC page, cover table | Every page carries a letter-spaced header ("I n t e r n a l  u s e  o n l y …"). Without removal it appears in every chunk. The TOC page lists every section title, so it would match almost every query while containing no answers. |
| Tables | Convert each row to "Header: value" text; drop blank forms | Plain text extraction scrambles tables (e.g. shift allowance, travel booking deadlines, travel class by rank). Facts in these tables are likely test questions. The travel request form on p.26 is an empty template and is dropped. |
| Chunk boundaries | Section first (32 TOC headings), then numbered clauses | Section lengths vary from 61 to 2,603 words (median 266). One fixed window would cut short policies in half and mix two policies in one chunk. Policies are written as numbered clauses, which are natural break points. |
| Chunk size | ≤180 words (~240 tokens), 30-word overlap | `all-MiniLM-L6-v2` silently truncates input beyond 256 tokens. 180 words keeps every chunk under that limit, so the A/B comparison uses identical chunks for both models. The overlap keeps a rule intact when it crosses a boundary. |
| Section-title prefix | `[SHIFT POLICY] p.17 …` | "Scope" appears as a sub-heading 8 times and "Deviation/Exception" 11 times across different policies. Without the title, these chunks are indistinguishable. |
| Vector store | FAISS `IndexFlatIP`, one index per model | ~136 vectors: exact search is instant and runs in-process with no server. Comparing two models = two small index files. Chroma's metadata filtering and persistence add nothing for one static document. |
| Embeddings | Compare MiniLM vs bge-small (both 384-dim) | Same dimension and similar size, so the comparison isolates retrieval quality. Vectors are normalised, so inner product = cosine similarity. |
| top-k | 4 | A chunk is ~170 words, and most answers sit in one clause. 4 chunks (~700 words) cover questions that span clauses (e.g. leave types) without flooding the prompt. |
| Generator | Groq API | Fast, free tier, no local GPU. |
| Ragas judge | Gemini API | A different model from the generator, so the system does not grade its own answers. |
| Prompt rule | Answer only from the context; otherwise say "not in the handbook" | Raises faithfulness. 6 of the 50 test questions are deliberately out of scope to test this. |
