# Chapter 4 — Database Design and Conceptual Data Model

## 4.1 Introduction

The Hebron University RAG Chatbot is designed to assist students and staff by answering questions about the university in Arabic, using both statically uploaded documents and dynamically synchronized live data. To ensure that the system is well structured, maintainable, and aligned with its functional requirements, a formal conceptual data model was developed as part of this graduation project.

This chapter presents the **Entity-Relationship Diagram (ERD)** of the proposed system. The diagram describes the main data objects in the chatbot environment, the relationships among them, and the cardinality constraints that govern how information is stored, updated, and used during runtime. The model covers the full scope of the project, including external university APIs, administrative knowledge management, retrieval-augmented generation (RAG), chatbot configuration, and end-user conversation handling.

The ERD was constructed using **Chen notation**, which represents entities as rectangles, relationships as diamonds, and attributes within entity descriptions. Primary keys are underlined. Solid connectors indicate persistent structural associations, while dashed connectors represent runtime interactions that occur during chat or administration but are not necessarily implemented as direct database foreign keys. This distinction helps separate **what is stored permanently** from **what happens when the system is in operation**.

The authoritative diagram for this project is shown in **Figure 4.1** and is maintained in the file `docs/diagrams/hebron-chatbot-erd-me.drawio`.

---

**Figure 4.1 — Entity-Relationship Diagram of the Hebron University RAG Chatbot System**

*(Insert exported image of `hebron-chatbot-erd-me.drawio` here.)*

*Figure 4.1 illustrates the integrated conceptual data model of the chatbot system. The model connects external data ingestion, administrative document management, configuration settings, vector-based retrieval, and user conversation flow within a single unified structure.*

---

## 4.2 Objectives of the Conceptual Model

The purpose of developing this ERD was to achieve the following objectives:

1. **Represent the complete system scope.** The chatbot is not limited to a simple question-and-answer database. It integrates uploaded files, live university API feeds, vector embeddings, administrative settings, and conversational history. The diagram captures all of these domains in one connected model.

2. **Clarify data ownership and flow.** The model shows how information enters the system—either through administrator uploads or automated synchronization—and how it eventually reaches the chatbot during answer generation.

3. **Support implementation planning.** Although the diagram is conceptual, it guided the design of the PostgreSQL relational schema and the ChromaDB vector store used in the implemented system.

4. **Document runtime behaviour.** Relationships such as *asks*, *reads*, and *generates* describe how the chatbot interacts with stored data during a live session, which is essential for understanding system behaviour beyond table definitions alone.

5. **Provide a formal project artefact.** As part of the graduation project documentation, the ERD serves as evidence of structured analysis and system design before implementation.

---

## 4.3 Modeling Approach

The data model was developed in three stages:

**Requirement analysis.** Functional requirements were extracted from the project scope: users must be able to chat with the bot; administrators must upload and manage documents; live university data must be synchronized periodically; unanswered questions must be logged; and responses must be grounded in retrieved knowledge.

**Entity identification.** Major nouns and actors in the requirements were mapped to entities. Some entities correspond directly to database tables, such as *Conversation* and *Message*. Others are **logical** or **external**, such as *End User* and *University API*, because they represent actors or systems outside the local database boundary.

**Relationship definition.** Associations between entities were defined and validated against expected system behaviour. Cardinalities were assigned to express whether one instance of an entity may relate to one or many instances of another. For example, one *Conversation* may contain many *Messages*, while each *Message* receives at most one *Feedback* record in this model.

Chen notation was selected because it clearly distinguishes entities from relationships and is widely accepted in academic system analysis documentation. The diagram uses colour grouping to improve readability across domains, but the formal meaning of the model is defined by entity shapes, relationship diamonds, line types, and cardinality labels.

---

## 4.4 Overview of System Domains

The ERD organizes the chatbot system into five interconnected domains.

### 4.4.1 External Ingestion Domain

This domain represents live university information obtained from external REST APIs. The *University API* is modeled as an external system with a double border to indicate that it lies outside the chatbot application. It **provides** multiple *Live Data Source* entries, each describing a specific feed such as the academic calendar or announcements. Each live source is identified by a `source_id`, classified by `source_type`, and linked to a concrete `endpoint_url`.

Scheduled or manual synchronization creates *Sync Run* records, which track the status of each ingestion attempt. Successful runs **sync to** *Vector Chunk* entries stored in the vector database, making live data searchable by the chatbot.

### 4.4.2 Static Knowledge Domain

This domain covers knowledge managed by university administrators through the admin panel. An *Administrator* **uploads** *Knowledge Doc* records, which represent documents in the institutional knowledge base. Each document **has history** recorded as *Doc Revision* entries, supporting audit and version tracking. At the file level, each knowledge document is **stored as** one *Uploaded File*, while semantically it is **chunked into** many *Vector Chunk* records to enable retrieval-augmented generation.

This domain ensures that official PDFs, policies, and static reference material remain separate from live API data while still feeding the same retrieval mechanism.

### 4.4.3 Configuration Domain

Between administration and chatbot operation lies a configuration layer consisting of *FAQ Entry*, *Response Override*, *System Config*, and *Unanswered Question*. These entities allow administrators to define curated answers, exact phrase overrides, global settings, and logs of questions the bot could not answer satisfactorily.

In the diagram, the administrator **manages** these entities, while the chatbot **uses**, **matches**, is **configured by**, and **logs** them at runtime. These links are dashed because they represent operational consultation rather than strict relational containment.

### 4.4.4 Retrieval Domain

*Vector Chunk* acts as the central RAG hub of the system. It receives embeddings produced from both uploaded documents and synchronized live feeds. The *Chatbot* **retrieves** relevant chunks during answer generation. This entity therefore connects the ingestion pipelines to the conversational layer and represents the core innovation of the project: combining structured storage with semantic search.

### 4.4.5 Conversation Domain

The conversation domain models interaction between users and the chatbot. *End User* is a logical entity representing a person using the widget or an integrated messaging channel. Each user **starts** one or more *Conversation* sessions identified by `session_id`. Each conversation **contains** many *Messages* with roles such as user or bot. A message may **receive** *Feedback*, allowing the system to capture user satisfaction with a specific reply.

Runtime relationships show that the user **asks** the chatbot, the chatbot **reads** conversation history for context, and the chatbot **generates** new messages in response.

---

## 4.5 Entity Description

The following sections describe the entities presented in Figure 4.1.

### 4.5.1 University API

The *University API* represents the official external platform that publishes university information through REST endpoints. It is not stored inside the chatbot database. Modeling it explicitly emphasizes that live data originates outside the project and enters the system only through configured sources and synchronization processes.

### 4.5.2 Live Data Source

A *Live Data Source* defines one ingestible feed from the university platform. Its primary identifier is `source_id`. The attribute `source_type` indicates the nature of the feed, such as calendar or announcements, while `endpoint_url` stores the exact API path used to retrieve data. Placing `endpoint_url` on the live source rather than on the external API reflects the implementation reality that one university platform may expose multiple endpoints, each treated as a separate source.

### 4.5.3 Sync Run

Each synchronization attempt is represented by a *Sync Run* entity, characterized mainly by its `status`. This entity supports monitoring, troubleshooting, and historical analysis of the live ingestion pipeline.

### 4.5.4 Vector Chunk

The *Vector Chunk* entity represents a semantically indexed fragment of text stored in the vector database (ChromaDB). It contains an embedding and metadata that identify the origin of the chunk, such as a document filename or dynamic source identifier. This entity is central to the RAG architecture because it allows the chatbot to retrieve contextually relevant information rather than relying on the language model alone.

### 4.5.5 Administrator

The *Administrator* entity represents authorized staff who manage the chatbot through the admin panel. The primary key is `admin_id`, and `username` identifies the account used for authentication and role-based access.

### 4.5.6 Knowledge Doc

*Knowledge Doc* represents a managed document in the institutional knowledge base. It is identified by `document_id` and includes a `status` attribute that reflects lifecycle states such as active, stale, or retired. This abstraction allows the model to focus on document management semantics rather than low-level file details alone.

### 4.5.7 Doc Revision

*Doc Revision* records the historical evolution of a knowledge document. Attributes such as `version_number` and `action` document events including upload, replacement, review, and retirement. This supports accountability and traceability in administrative workflows.

### 4.5.8 Uploaded File

The *Uploaded File* entity represents the physical storage of a knowledge document on the server filesystem. Its key attribute is `file_path`. Separating this entity from *Knowledge Doc* clarifies the distinction between logical document management and physical file storage.

### 4.5.9 FAQ Entry

An *FAQ Entry* stores a predefined question and answer pair maintained by administrators. These entries improve response quality for common queries and may be used directly or in combination with retrieval-based answering.

### 4.5.10 Response Override

*Response Override* defines exact trigger phrases mapped to fixed answers. This entity allows administrators to enforce precise responses for sensitive or standardized topics without leaving answer selection entirely to the language model.

### 4.5.11 System Config

*System Config* stores configurable system parameters as key-value pairs. Examples include model settings, prompt behaviour, and operational limits. This entity supports flexible administration without modifying application code.

### 4.5.12 Unanswered Question

When the chatbot cannot provide a satisfactory answer, the question may be recorded as an *Unanswered Question* with a textual `question` and explanatory `reason`. This supports continuous improvement of the knowledge base and monitoring of user needs.

### 4.5.13 Chatbot

The *Chatbot* is modeled as a system actor rather than a database table. It represents the RAG engine and language model orchestration layer that processes user input, retrieves knowledge, applies configuration rules, and generates responses. Attributes such as `llm_provider` and `llm_model` indicate the artificial intelligence backend used at runtime.

### 4.5.14 End User

*End User* is a logical entity representing the person interacting with the chatbot through the web widget or external messaging channels. It is identified by `user_id`. The model treats the end user as logical because the implemented system groups sessions by user identifier without maintaining a full user registration table.

### 4.5.15 Conversation

A *Conversation* represents one chat session between an end user and the chatbot. It is identified by `session_id` and may include a `title` for display in chat history interfaces.

### 4.5.16 Message

The *Message* entity represents a single utterance within a conversation. Its attributes include `role`, indicating whether the speaker is the user or the bot, and `content`, which stores the message text.

### 4.5.17 Feedback

*Feedback* captures the end user's evaluation of a bot message, typically through a rating such as like or dislike. In this conceptual model, each message receives at most one feedback record, reflecting the intended one-rating-per-reply interaction in the user interface.

---

## 4.6 Relationship Analysis

The relationships in Figure 4.1 define how entities interact within the system.

### 4.6.1 Structural Relationships

Structural relationships represent persistent associations that underpin the implemented storage design:

- **University API — provides — Live Data Source (1:N):** One external platform provides many source definitions.
- **Live Data Source — runs — Sync Run (1:N):** Each configured source may have many synchronization executions over time.
- **Sync Run — syncs to — Vector Chunk (1:N):** One sync operation may produce or update many vector chunks.
- **Administrator — uploads — Knowledge Doc (1:N):** One administrator may upload and manage many documents.
- **Knowledge Doc — has history — Doc Revision (1:N):** Each document maintains multiple revision records.
- **Knowledge Doc — stored as — Uploaded File (1:1):** Each knowledge document corresponds to one stored file.
- **Knowledge Doc — chunked into — Vector Chunk (1:N):** Document ingestion splits one source document into many searchable chunks.
- **Chatbot — retrieves — Vector Chunk (1:N):** During answer generation, the chatbot may retrieve multiple relevant chunks.
- **End User — starts — Conversation (1:N):** One user may initiate many chat sessions.
- **Conversation — contains — Message (1:N):** Each session includes many messages exchanged over time.
- **Message — receives — Feedback (1:1):** Each message is associated with at most one feedback record in this model.

These relationships form the backbone of the system's data architecture and correspond closely to the PostgreSQL schema and vector store design.

### 4.6.2 Runtime Relationships

Runtime relationships describe dynamic behaviour during system operation:

- **Administrator — manages — configuration and content entities (1:N):** Administrators maintain live sources, documents, FAQs, overrides, settings, and unanswered question logs through the admin interface.
- **FAQ Entry — uses — Chatbot (N:1):** The chatbot consults FAQ data when answering user queries.
- **Response Override — matches — Chatbot (N:1):** The chatbot checks override rules against user input.
- **System Config — configured by — Chatbot (N:1):** Runtime behaviour depends on configured system parameters.
- **Unanswered Question — logs — Chatbot (N:1):** The chatbot records unresolved or weak answers for later review.
- **End User — asks — Chatbot (1:1):** Each user turn represents one question directed to the chatbot.
- **Chatbot — reads — Conversation (1:N):** The chatbot reads session history to maintain conversational context.
- **Chatbot — generates — Message (1:N):** The chatbot produces assistant messages throughout the session.

These dashed relationships are essential for explaining how the implemented application behaves even though they are not all represented as explicit foreign keys.

---

## 4.7 Mapping Between Conceptual Model and Implementation

Although Figure 4.1 is conceptual, it guided the actual implementation of the project. Table 4.1 summarizes how major entities map to the implemented system components.

**Table 4.1 — Mapping of conceptual entities to implementation components**

| Conceptual entity | Implementation component |
|-------------------|--------------------------|
| Administrator | `admins` table |
| Knowledge Doc | `file_records` table |
| Doc Revision | `document_versions` table |
| Uploaded File | File path in `file_records` and `uploads/` directory |
| Live Data Source | `dynamic_sources` table |
| Sync Run | `dynamic_sync_runs` table |
| FAQ Entry | `faqs` table |
| Response Override | `manual_overrides` table |
| System Config | `system_settings` table |
| Unanswered Question | `unanswered_queries` table |
| Conversation | `chat_sessions` table |
| Message | `chat_messages` table |
| Feedback | `feedback` table |
| Vector Chunk | ChromaDB vector store |
| University API | External REST services / mock API server |
| Chatbot | RAG application layer |
| End User | Session-level `user_id` identifier |

This mapping demonstrates that the conceptual model is not merely theoretical; it reflects the structure of the working graduation project prototype.

---

## 4.8 Design Decisions and Justification

Several important design decisions are visible in the ERD:

**Unified retrieval hub.** Static uploads and live API synchronization both feed *Vector Chunk*. This design avoids duplicating retrieval logic and ensures that the chatbot uses one consistent semantic search mechanism for all knowledge sources.

**Separation of logical and physical document concepts.** Distinguishing *Knowledge Doc*, *Doc Revision*, and *Uploaded File* improves clarity in administrative workflows and supports document lifecycle management.

**Explicit external boundary.** Modeling the *University API* as external makes clear that the chatbot depends on institutional data sources it does not control, which is an important architectural assumption in a university setting.

**Runtime versus structural links.** Dashed relationships prevent the model from incorrectly implying that every interaction is stored as a relational foreign key. This improves accuracy when describing chatbot behaviour.

**Logical end-user modeling.** Since the project prioritizes accessible chat rather than full user account management, modeling *End User* as logical accurately represents the chosen scope.

---

## 4.9 Summary

This chapter presented the conceptual data model of the Hebron University RAG Chatbot graduation project. The Entity-Relationship Diagram integrates external API ingestion, administrative knowledge management, chatbot configuration, vector retrieval, and conversational interaction into one coherent structure.

The model shows that the system is designed around a retrieval-augmented architecture in which both static and live university information is transformed into searchable vector chunks. Administrators maintain the knowledge base and configuration settings, while end users interact with the chatbot through structured conversations supported by stored messages and optional feedback.

By documenting entities, relationships, cardinalities, and implementation mapping, this chapter provides a formal foundation for the database and system design presented in the remainder of the graduation project report. Figure 4.1 should be included in the final submission as the primary visual reference for the system's data architecture.

---

## Suggested placement in the graduation report

| Report section | Suggested content from this document |
|----------------|--------------------------------------|
| Chapter 4 — System Design | Sections 4.1–4.4 |
| Chapter 4 — Database Design | Sections 4.5–4.7 |
| Chapter 5 — Implementation | Section 4.7 as bridge to code |
| Appendices | Full-size export of Figure 4.1 |

**Note for final submission:** Export `docs/diagrams/hebron-chatbot-erd-me.drawio` as PNG or PDF at high resolution and insert it as Figure 4.1 in the printed report. Refer to the figure at the first mention of the data model in the chapter introduction.
