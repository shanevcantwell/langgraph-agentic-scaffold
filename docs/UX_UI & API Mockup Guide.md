# **UX/UI & API Integration Guide**

# **Version: 1.0**

# **Status: ACTIVE**

This document defines the API contracts and data structures required to build a user interface for the agentic system. It is a technical specification for front-end developers and UI-focused AI agents.

## **1.0 Core Philosophy: Skinning & Theming**

The backend is headless and exposes a consistent data flow. The front-end's primary role is to provide a "skin" for this flow. This guide enables the creation of diverse themes (e.g., "1970s retro," "cyberpunk terminal," "minimalist clinical," "ADHD-friendly focus mode") by defining the key information that any UI must present to the user.

## **2.0 Conceptual UI Components**

Any user interface for this system is composed of four primary conceptual components that are powered by the backend API.

### **2.1 The Command Bar (User Input)**

The user's entry point for interacting with the agent.

*   **Description:** A simple text input area where the user types their prompt or command.
*   **API Interaction:** Submitting a prompt triggers a `POST` request to the `/v1/invoke` endpoint.

### **2.2 The Agent Log (Real-time Feedback)**

Provides a live, streaming view of the agent's internal state and actions. This is crucial for user trust and transparency.

*   **Description:** A scrolling log that displays messages from the various specialists as they work. It should feel like watching a team of experts collaborate in a chat room.
*   **API Interaction:** The UI should connect to the `WS /v1/ws/agent_monitor` WebSocket endpoint. Upon connection, it will receive a stream of `TurnUpdate` objects as the agent works.

### **2.3 The Artifact Display (The Result)**

The area where the final output of the agent's work is presented.

*   **Description:** A flexible component that can render different types of final products. The UI should be able to handle various artifact types gracefully.
*   **API Interaction:** The final `Artifact` object is delivered as part of the JSON response from the `POST /v1/invoke` endpoint once the entire workflow is complete.

### **2.4 The Settings Panel (User Configuration)**

Allows the user to make choices from a pre-approved list of options, as defined in user\_settings.yaml.

*   **Description:** A panel (modal, sidebar, etc.) where users can customize the agent's behavior for their session.
*   **API Interaction:** The UI should populate this panel by making a `GET` request to the `/v1/settings` endpoint, which returns a `SettingsConfiguration` object.

## **3.0 API Endpoints**

### **3.1 `POST /v1/invoke`**

*   **Description:** The primary endpoint to initiate an agentic workflow. This is a blocking call that returns when the agent has finished its task or encountered a terminal error.
*   **Request Body:**
    ```json
    {
      "prompt": "Your detailed request for the agent goes here."
    }
    ```
*   **Success Response (200 OK):** Returns the final state of the graph, containing the artifact and message history.
    ```json
    {
      "final_artifact": {
        "type": "html" | "json" | "text" | "markdown",
        "content": "...",
        "source_specialist": "web_builder"
      },
      "message_history": [
        {"type": "human", "content": "...", "name": "user"},
        {"type": "ai", "content": "...", "name": "router_specialist"}
      ],
      "turn_count": 5,
      "error": null
    }
    ```

### **3.2 `GET /v1/settings`**

*   **Description:** Retrieves the user-configurable settings as defined by the system's configuration files.
*   **Request Body:** None.
*   **Success Response (200 OK):** Returns a `SettingsConfiguration` object.

### **3.3 `WS /v1/ws/agent_monitor`**

*   **Description:** A WebSocket endpoint for receiving real-time updates from the agent as it works. This is the recommended way to power a live "Agent Log".
*   **Messages:** The server will push `TurnUpdate` objects to the client for each significant event in the graph.

## **4.0 Data Contracts**

### **4.1 `TurnUpdate` (for WebSocket)**

This object provides a rich, real-time view into the agent's turn-by-turn progress.

```json
{
  "turn_id": 1,
  "timestamp": "2025-08-23T15:30:00Z",
  "event_type": "specialist_start" | "specialist_end" | "workflow_end",
  "specialist_name": "file_specialist",
  "status_message": "FileSpecialist is attempting to read 'my_document.txt'.",
  "state_delta": {
    "messages": [
      {"type": "ai", "content": "Reading file...", "name": "file_specialist"}
    ],
    "text_to_process": "The content of the file..."
  }
}
```
*   `event_type` (enum): The type of event that occurred.
*   `specialist_name` (string): The name of the specialist that is currently active.
*   `status_message` (string): A human-readable message about the current action.
*   `state_delta` (object): A dictionary containing only the *new keys* that were added or changed in the `GraphState` during this turn. This allows the UI to incrementally build its own view of the state.

### **4.2 `Artifact` (in final response)**

The final, user-facing result of the agent's work.

```json
{
  "artifact_id": "uuid-5678-efgh",
  "type": "html" | "json" | "text" | "markdown" | "file_list",
  "content": "The raw content of the artifact, e.g., an HTML string or a JSON object.",
  "source_specialist": "web_builder",
  "metadata": {
    "title": "1970s Installation Guide",
    "character_count": 4502
  }
}
```

### **4.3 `SettingsConfiguration` (from `GET /settings`)**

Defines the structure for populating a settings panel in the UI.

```json
{
  "schema_version": "1.0",
  "settings": [
    {
      "id": "router_specialist_llm_binding",
      "label": "Primary Reasoning Model",
      "description": "Choose the main LLM for routing and complex tasks.",
      "type": "dropdown",
      "options": [
        { "value": "gemini_pro", "label": "Gemini 1.5 Pro (Balanced)" },
        { "value": "gemini_flash", "label": "Gemini 1.5 Flash (Fast)" }
      ],
      "current_value": "gemini_pro"
    }
  ]
}
```