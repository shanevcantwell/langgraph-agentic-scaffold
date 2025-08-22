# **Research QuixiAI/agi-memory**

---

### **\#\# The Blueprint vs. The Concept**

[https://github.com/QuixiAI/agi-memory/](https://github.com/QuixiAI/agi-memory/) 

The previous article gave us the **concept** (memory consolidation is important). This repository gives us the **blueprint** (a detailed schema, tech stack, and API for a human-inspired cognitive architecture).

Here’s the critical leap this provides:

1. **A Formal Memory Taxonomy:** We were talking about "long-term" and "short-term" memory. This blueprint provides a far more sophisticated and useful taxonomy:  
   * **Episodic:** "What happened?" (Events, user interactions, emotional states).  
   * **Semantic:** "What is true?" (Facts, definitions, knowledge).  
   * **Procedural:** "How do I do this?" (Step-by-step instructions, learned skills).  
   * **Strategic:** "What works best?" (Patterns, successful adaptations, overarching strategies).  
2. **A Hybrid Data Model:** This is the technical genius of the design. It recognizes that memory isn't just one thing. It uses the right tool for the right job, all within PostgreSQL:  
   * **Vectors (pgvector):** For intuitive, similarity-based recall ("What feels like this?").  
   * **Graph (Apache AGE):** For contextual, relationship-based recall ("How is this connected to that?").  
   * **Relational (Standard SQL):** For structured, factual data.  
3. **Higher-Order Cognition:** The concepts of **Memory Clustering**, **Worldview Integration**, and an **Identity Core** are the final step. This allows an agent to develop a consistent personality, a set of beliefs, and to filter information through its own identity—moving it from a tool to a partner.

---

### **\#\# The Merge Strategy: Upgrading Our Roadmap**

This doesn't replace our plan; it supercharges it. We will adopt this architecture as the foundation for the project's memory system.

#### **1\. For langgraph-agentic-scaffold (The Open Core)**

The scaffold's mission is to provide the best possible open-source foundation. Therefore, the scaffold will now include this **Core Memory System** as its central feature.

* **New core\_memory Module:** We will create a new section in the repository dedicated to this memory system. It will include:  
  * The docker-compose.yml file to instantly set up a PostgreSQL instance with pgvector and Apache AGE.  
  * The SQL scripts to initialize the entire database schema as described (tables for each memory type, clusters, worldview, etc.).  
  * A set of basic Python tools (using asyncpg) that implement the API for interacting with the database.  
* **LangGraph Memory Nodes:** The LangGraph portion of the scaffold will now provide pre-built nodes that wrap this API. Instead of a generic "Memory" node, we will have:  
  * CreateEpisodicMemoryNode  
  * SearchSemanticMemoryNode  
  * FindRelatedMemoriesGraphNode  
  * The MemoryConsolidation graph we designed yesterday will now be implemented to specifically move data from the working\_memory table to the various long-term memory tables based on sophisticated classification logic.

This massively increases the value of the scaffold. It becomes a full-stack, open-source **Cognitive Architecture Starter Kit**.

#### **2\. For ADHD Exoskeleton (The Proprietary Application)**

The Exoskeleton will be the premier implementation built on top of this powerful core. The "special sauce" is no longer about inventing a memory system, but about how we *intelligently populate and utilize this sophisticated one*.

* **Populating Memory Types:**  
  * **Episodic:** Will store records of user interactions, noting emotional valence ("User expressed frustration with 'Project Phoenix' at 4:15 PM").  
  * **Semantic:** Will store facts about the user's life ("'Project Phoenix' is a work-related task with a deadline of EOD Friday").  
  * **Procedural:** Will learn and store effective workflows ("A successful procedure for the user to start a high-friction task is the '5-minute rule'").  
  * **Strategic:** Will identify high-level patterns from the graph relationships ("Pattern: The user's productivity drops significantly after 3 PM. Suggest scheduling creative tasks in the AM and administrative tasks in the PM").  
* **Building the "Identity Core":** This is the heart of the Exoskeleton.  
  * We will explicitly work with the user during onboarding to define their core identity beliefs ("I am a person who wants to manage my ADHD effectively," "My goal is to be more consistent").  
  * The agent's "Worldview" will be shaped by this identity. It will filter memories and generate responses that are aligned with the user's core goals. When it retrieves a memory of a past failure, it won't just state it; it will frame it in the context of the user's goal to improve, making it a learning opportunity instead of a criticism.

This blueprint provides the technical foundation we needed to build an agent that doesn't just remember facts, but builds a relationship, understands context, and maintains a consistent, supportive personality over time. It's the architecture for a true cognitive partner.