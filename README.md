# 🔍 ContractSense — AI-Powered Contract Compliance Scanner
> **Official Submission Assets**  
> 📺 **[Launch Interactive Presentation Slides](https://heyzine.com/flip-book/b9c4379e07.html#page/8)**  
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

---

## 3. Technical Architecture Diagram
Below is the system data flow showing how a contract is parsed, checked, and analyzed:

```mermaid
graph TD
    A[User Interface - Browser] -->|1. Upload PDF/Word| B[FastAPI Backend Server]
    B -->|2. Extract Text| C[Text Extraction Service]
    B -->|3. Run Quick Checks| D[Rule Engine - Regular Expressions]
    B -->|4. Run Context Review| E[AI Engine - OpenAI/Gemini]
    E -->|5. Cross-Check| F[(Laws & Company Policies Database)]
    D -->|6. Compile Results| G[JSON Report Output]
    E -->|6. Compile Results| G
    G -->|7. Display Highlights & Fixes| A
```

### 🛠️ Technical Stack Breakdown
*   **Frontend**: Single Page Application (SPA) designed using clean, high-performance Vanilla HTML5, CSS3, and ES6 JavaScript. Includes custom side-by-side document views and responsive page-state routing.
*   **Backend Framework**: FastAPI (Python) for asynchronous endpoints, low latency, and automatic Swagger/OpenAPI documentation generation.
*   **Text Processing**: `PyPDF2` and custom `docx` binary stream extractors running on the backend, processing payloads safely without writing documents to public folders.
*   **Rule Engine**: Native regex-based scoring engine evaluating seven distinct high-risk categories (Auto-Renewal, Unilateral changes, Hidden fees, Liability limitations, Data transfers, Exclusive remedies, and External URL terms).
*   **LLM Orchestrator**: Async OpenAI API integration, utilizing system prompt directives to inject context (extracted contract text, deterministic rule violations, and reference law databases) to produce targeted executive reviews.

---
## 📊 Business & Monetization Model
ContractSense utilizes a Software-as-a-Service (SaaS) subscription model with tiered packaging designed for different scale requirements:

| Tier | Target Audience | Pricing | Features Included |
| :--- | :--- | :--- | :--- |
| **Starter / Dev** | Startups & Solopreneurs | **Free** (RM 0) | Up to 3 contract scans/month, standard Malaysian laws checks, community support. |
| **Professional** | SMEs & Growing HR Teams | **RM 149 / month** | Unlimited scans, custom company policy uploads, full inline suggestions, PDF export. |
| **Enterprise** | Large Scale / Legal Depts | **RM 499 / month** | Team workspaces, API keys, custom regulatory law reference files, dedicated customer success. |

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
*   OpenAI API Key (optional, for full heuristic LLM analysis)

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
     GEMINI_MODEL=gemini-1.5-flash   # or gemini-1.5-pro for advanced logic
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
* **Hybrid Engine**: Uses quick regex matching for obvious traps (like auto-renewals) and advanced AI (Gemini/OpenAI) for complex compliance logic.
* **Data Privacy**: Everything is processed in memory. We do not store contract files in public folders, and we do not use your contracts to train public AI models.

### Business Value
* **Massive Cost Savings**: Instantly saves SMEs thousands of Ringgit in legal review fees.
* **Speed**: Reduces compliance check times from days to under 30 seconds.
* **Scalable SaaS**: Built on a tiered subscription model (Free Plan, Professional Plan at RM149/month, and Enterprise Plan at RM499/month).
