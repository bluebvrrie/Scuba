# Scuba – Multi-Agent AI Learning Assistant

> **An intelligent AI-powered learning companion built with NitroStack Studio and the Model Context Protocol (MCP).**

##  Overview

Scuba is a **multi-agent AI learning assistant** designed to make studying more effective through personalized guidance. Instead of relying on a single AI chatbot, Scuba uses **three specialized AI agents** that collaborate to provide research, teaching, and learning evaluation.

Built using **NitroStack Studio** and the **Model Context Protocol (MCP)**, the platform enables each agent to access external tools and resources in a modular, scalable, and extensible manner.

---

##  Features

###  Research Agent

The Research Agent gathers accurate and relevant learning material from multiple sources.

**Capabilities**

* Search uploaded PDFs
* Retrieve information from personal notes
* Access textbook content
* Query trusted online educational resources through MCP tools
* Return source references and confidence scores

---

###  Teaching Agent

The Teaching Agent transforms retrieved information into personalized learning content.

**Capabilities**

* Explain concepts according to the student's learning level
* Generate step-by-step explanations
* Provide real-world analogies
* Create worked examples
* Produce concise summaries
* Generate practice questions
* Create flashcards for revision

---

###  Evaluation & Planning Agent

The Evaluation Agent tracks learning progress and helps students improve over time.

**Capabilities**

* Generate quizzes
* Evaluate quiz performance
* Identify weak and strong topics
* Track learning progress
* Recommend personalized revision strategies
* Generate daily and weekly study plans

---

##  Architecture

```
                    User
                      │
                React Frontend
                      │
               NitroStack Backend
                      │
              Agent Orchestrator
          ┌────────┼────────┐
          │        │        │
          ▼        ▼        ▼
    Research   Teaching   Evaluation
      Agent      Agent       Agent
          │
          ▼
     MCP Tool Servers
          │
  PDFs • Notes • Textbooks • Web
```

---

##  Tech Stack

### Frontend

* React
* Tailwind CSS

### Backend

* Python
* NitroStack Studio

### AI

* Multi-Agent Architecture
* Large Language Models

### MCP Tools

* PDF Retrieval
* Notes Retrieval
* Web Search
* File Access

---

##  Project Structure

```
Scuba/
│
├── frontend/
│
├── backend/
│   ├── agents/
│   │   ├── research_agent.py
│   │   ├── teaching_agent.py
│   │   └── evaluation_agent.py
│   │
│   ├── mcp/
│   │   ├── pdf_server.py
│   │   ├── notes_server.py
│   │   └── web_server.py
│   │
│   ├── orchestrator.py
│   ├── api.py
│   └── database.py
│
├── uploads/
├── vector_store/
└── README.md
```

---

##  Workflow

1. The user uploads learning materials (PDFs, notes, textbooks) or asks a question.
2. The **Research Agent** retrieves relevant information using MCP tools.
3. The **Teaching Agent** generates explanations, examples, summaries, and practice questions.
4. The **Evaluation & Planning Agent** assesses quiz performance, identifies weak areas, and creates personalized study plans.
5. The frontend presents an interactive and personalized learning experience.

---

##  Why Scuba?

Traditional AI chatbots answer questions, but they rarely provide a structured learning journey.

Scuba combines specialized AI agents to:

* Deliver accurate, source-backed information
* Adapt explanations to each student's learning level
* Continuously assess progress
* Create personalized revision plans
* Encourage long-term learning rather than one-time answers

---

##  Future Enhancements

* Voice-based tutoring
* Spaced repetition system
* Gamified learning and achievement badges
* Collaborative study groups
* Learning analytics dashboard
* Support for additional MCP tool integrations

---

##  Team

* Member 1 – Research Agent & MCP Integration
* Member 2 – Teaching Agent
* Member 3 – Evaluation & Planning Agent
* Member 4 – Frontend & Agent Orchestration

---

##  License

This project was developed for the **NitroStack Studio + MCP Hackathon**.

Feel free to extend and improve the project for educational purposes.
