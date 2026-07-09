# 🔍 ContractSense — AI-Powered Contract Compliance Scanner
> **Official Submission Assets**  
> 🚀 **[Live Demo (Vercel Website)](https://nex-hack-2026.vercel.app/)**  
> 📂 **[Read the Pitch Deck (GitHub Markdown)](./pitch_deck.md)**  
> 📺 **[Launch Interactive Presentation Slides](./presentation_slides.html)** | **[Flip-Book Link](https://heyzine.com/flip-book/b9c4379e07.html#page/8)**  
> 
> *Empowering Malaysian SMEs, HR professionals, and Legal teams to screen, flag, and remediate contract compliance risks in under 30 seconds.*

---

## 1. The Problem Chosen
For small and medium businesses (SMEs) in Malaysia, checking contracts (like hiring offers, room rentals, or sales agreements) before signing is a major headache:

1. **High Legal Fees**: Hiring a lawyer to read a simple contract costs between RM500 to RM2,500. Most SMEs cannot afford this and end up signing unchecked contracts.
2. **Too Many Law Changes**: Laws like the *Employment Act 1955* (updated in 2022 with new rules on leaves and work hours) and the *PDPA 2010* (privacy law) are hard for normal business owners to track and understand.
3. **Slow Turnaround**: Waiting for external lawyers to check a contract takes 3 to 7 days, which slows down business deals and hiring.

---

## 2. Target Users
ContractSense is built for three main groups:

* **HR Managers**: Need to check job offers and employment contracts quickly to make sure leaves, overtime, and work hours follow the latest Malaysian laws.
* **SME Business Owners**: Need to check tenancy agreements, NDAs, and supplier contracts to avoid hidden fees or unfair terms.
* **Corporate Teams**: Need a fast way to run a first-pass check on standard agreements before sending them to the main legal department.

## 3. Technical Architecture Diagram
Below is the system data flow showing how a contract is parsed, checked, and analyzed through the 4-stage pipeline:

```mermaid
graph TD
    subgraph Zone 1: Intake Layer
        UI[PDF/DOCX Upload UI - Path A Manual]
        IMAP[Automated IMAP Agent - Path B Proactive]
    end

    subgraph Zone 2: Extraction Layer
        pdf[pdfplumber / pypdf fallback]
        docx[python-docx stream extractor]
        structure[Clause-Numbered Structuring]
    end

    subgraph Zone 3: Evaluation Layer
        regex[Deterministic Regex Rule Engine - 7 Risk Categories]
        llm[Retrieval-Grounded LLM Review - Map-Reduce Chunking over Malaysian Law DB]
        openai[OpenAI Client - Temp=0]
        gemini[Gemini Client - Backup / Failover]
        log[Failure Logging]
    end

    subgraph Zone 4: Output Layer
        report[Clause-Cited Compliance Report]
        chat[Interactive Chat UI]
    end

    UI --> pdf
    UI --> docx
    IMAP --> pdf
    pdf --> structure
    docx --> structure
    structure --> regex
    structure --> llm
    llm --> openai
    openai -->|Failover| gemini
    gemini --> log
    regex --> report
    openai --> report
    gemini --> report
    report --> chat
```

### 🛠️ Technical Stack Breakdown
*   **Frontend**: Single Page Application (SPA) designed using clean, high-performance Vanilla HTML5, CSS3, and ES6 JavaScript. Includes custom side-by-side document views, interactive highlight overlays synced with PDF coordinates, and responsive page-state routing.
*   **Backend Framework**: FastAPI (Python) for asynchronous endpoints, low latency, and automatic Swagger/OpenAPI documentation generation.
*   **Text Processing**: Dynamic text extraction using `pdfplumber` first (handling tables and layouts reliably) and falling back to `pypdf` for maximum stability, alongside `python-docx` for Word documents.
*   **Rule Engine**: Native regex-based scoring engine evaluating seven distinct high-risk categories (Auto-Renewal, Unilateral changes, Hidden fees, Liability limitations, Data transfers, Exclusive remedies, and External URL terms).
*   **LLM Orchestrator**: Async multi-provider LLM calling with automatic failover (tries OpenAI GPT-4o-mini first, and automatically falls back to Gemini 2.5 Flash if needed). Utilizes retrieval-grounded context (local law updates and company policies) at temperature 0 for strict precision.
*   **Background Automation**: Watcher services for folder auto-import (`data/auto_import`) and IMAP email scanning (selectively scanning subject lines first to preserve inbox privacy).
*   **Database**: Sqlite database as local store (default at `backend/data/contractsense.db`) or PostgreSQL/Supabase for cloud deployment.

---
## 📊 Business & Monetization Model
ContractSense utilizes a Software-as-a-Service (SaaS) subscription model with tiered packaging designed for different scale requirements:

| Tier | Target Audience | Pricing | Features Included |
| :--- | :--- | :--- | :--- |
| **Starter / Dev** | Startups & Solopreneurs | **Free** (RM 0) | Up to 3 contract scans/month, standard Malaysian laws checks, community support. |
| **Professional** | SMEs & Growing HR Teams | **RM 99 / month** | Unlimited scans, custom company policy uploads & updates, full inline suggestions, auto editing, PDF export. |
| **Enterprise / Scale** | Large Scale / Legal Depts | **RM 299 / month** | Team workspaces connection, auto-scanning connection, custom regulatory reference files, dedicated customer support. |

---
## 🚀 Go-To-Market (GTM) Strategy
To accelerate product adoption in the Malaysian market, ContractSense leverages a targeted, multi-channel growth plan:
1.  **SME Association Partnerships**: Partner with organizations like SAMENTA (SME Association of Malaysia) and MDEC (Malaysia Digital Economy Corporation) to offer compliance screening masterclasses.
2.  **Product-Led Growth (PLG)**: Offer a free "Quick Scan" tool on the homepage, allowing users to upload short contracts without creating an account, driving sign-ups after value validation.
3.  **Content-driven SEO**: Focus on high-intent local search keywords, publishing guides on employment law amendments, tenancy dispute resolution, and corporate governance in Malaysia.
4.  **Template Library Integration**: Provide free, verified template contracts (employment contracts, NDAs) that link users directly to the scanner to check external modifications.

---
## ⚖️ Competitive Advantage
ContractSense holds key advantages over broad, generic LLM tools:
*   **Precision Focus**: General chatbots (like ChatGPT) analyze documents without legal references. ContractSense anchors its assessments in uploaded **Malaysian law databases** and **internal company guidelines**.
*   **Hybrid Engine Efficiency**: Combining local regex rules with API checks ensures that critical contract flaws (e.g. unilateral changes) are identified instantly, using LLMs primarily for nuance.
*   **Data Isolation**: Text extraction happens dynamically in memory. The system does not save contracts in public repositories or train models on user data, keeping enterprise contracts private.

---
## 🗺️ Future Roadmap
```
  ┌────────────────────────┐       ┌────────────────────────┐       ┌────────────────────────┐
  │        Q3 2026         │       │        Q4 2026         │       │        Q1 2027         │
  ├────────────────────────┤       ├────────────────────────┤       ├────────────────────────┤
  │ • Bahasa Melayu OCR    │──────>│ • DocuSign API         │──────>│ • Fine-tuned Legal LLM │
  │ • Tenancy Act Support  │       │   Integration          │       │   (Reduced API Costs)  │
  └────────────────────────┘       └────────────────────────┘       └────────────────────────┘
```
*   **Q3 2026: OCR Scanning, Bilingual Audits & Inbox Security**  
    - Introduce optical character recognition (OCR) for scanned PDFs and bilingual analysis (English and Bahasa Melayu).
    - **Email Privacy Upgrade**: Transition from raw IMAP connection credentials to scoped Google/Outlook OAuth 2.0. Limit scanner visibility to a specific labels/folders (e.g. `contracts/`) or messages sent to `contracts@company.com` to prevent reading unrelated emails.
*   **Q4 2026: E-Signature Integration & Intake Pre-filtering**  
    - Integrate e-signature providers (like DocuSign) to let users edit, check, and sign compliance-vetted documents in a single workflow.
    - Implement an AI email intake pre-classifier to automatically filter out non-contract attachments before content extraction.
*   **Q1 2027: Specialized Legal LLMs**  
    - Transition to a fine-tuned, open-source legal model (such as Llama-3-Legal-Malaysian) hosted locally, reducing dependency on OpenAI API fees and increasing analysis speed.

---
## 💻 Local Development Setup
To run ContractSense on your local machine:

### Prerequisites
*   Python 3.10+
*   Node.js (optional, for hosting the frontend locally)

### 1. Start the Backend API
1. Open a terminal and navigate to the backend folder:
   ```powershell
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```powershell
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\Activate.ps1
   # macOS/Linux:
   source .venv/bin/activate
   ```
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and configure your variables:
   - To use **Gemini API** (Pro/Free key), add:
     ```env
     GEMINI_API_KEY=your_gemini_api_key
     GEMINI_MODEL=gemini-2.5-flash   # Default 2.5-flash model
     ```
   - To use **OpenAI API**, add:
     ```env
     OPENAI_API_KEY=your_openai_api_key
     OPENAI_MODEL=gpt-4o-mini
     ```
   - To use a **Cloud Database (Supabase / PostgreSQL)**, add:
     ```env
     DATABASE_URL=postgresql://postgres:[password]@db.supabase.co:5432/postgres
     ```
     *(If `DATABASE_URL` is left empty, the application automatically defaults to a local SQLite database stored at `backend/data/contractsense.db`.)*

5. Run the FastAPI development server:
   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

### 2. Run the Frontend
1. Open the `/frontend` directory.
2. Double-click [index.html](file:///c:/Users/gohxu/Downloads/NexHack_2026-1/frontend/index.html) to open the web app directly in your browser.
3. *Alternative (using a local dev server)*:
   ```powershell
   # In frontend folder:
   npx serve .
   ```

---

## 4. Technical & Business Overview

### Technical Highlights
* **4-Zone Hybrid Engine**: Combines background/manual intake, pdfplumber layout-aware text extraction, deterministic regex rules, and retrieval-grounded LLM review with automatic failover (OpenAI -> Gemini).
* **PDF Coordinate Mapping**: Renders actual PDF pages inside the browser and projects highlights directly onto the exact text coordinates.
* **Data Privacy**: Processed in memory without storing contracts publicly or using customer files to train public models.

### Business Value
* **Massive Cost Savings**: Instantly saves SMEs thousands of Ringgit in legal review fees.
* **Speed**: Reduces compliance check times from days to under 30 seconds.
* **Scalable SaaS**: Built on a tiered subscription model (Free Plan, Professional Plan at RM99/month, and Enterprise Plan at RM299/month).
