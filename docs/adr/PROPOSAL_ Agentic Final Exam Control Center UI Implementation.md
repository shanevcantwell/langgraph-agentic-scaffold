# **Agentic Plan: Control Center UI Implementation**

**High-Level Goal:** Implement the necessary backend functionality in the agentic-scaffold project to fully support the agent\_control\_center\_ui.html dashboard.

\*\* Save for local agents to work out\! \*\*

## **Phase 1: System & Log Monitoring Endpoints**

This phase establishes the foundational monitoring capabilities.

### **Task 1.1: Implement System Status Endpoint**

* **Objective:** Create a new API endpoint to provide real-time status of the agent server.  
* **Specialist:** APISpecialist (A new specialist responsible for modifying the FastAPI app).  
* **Plan:**  
  1. **Read File:** Use FileSpecialist to read app/src/api.py.  
  2. **Modify Code:** Instruct a CodeWriterSpecialist to add a new endpoint GET /v1/system/status.  
  3. **Endpoint Logic:** This endpoint should return a JSON object containing:  
     * status: "online"  
     * uptime: (Calculated since server start)  
     * specialists: (A list of specialist names loaded from config.yaml)  
  4. **Write File:** Use FileSpecialist to save the changes to api.py.  
  5. **Audit:** Use an Auditor specialist to run a linter on the modified file.

### **Task 1.2: Implement Log Streaming Endpoint**

* **Objective:** Create an endpoint to provide access to the application's log file.  
* **Specialist:** APISpecialist.  
* **Plan:**  
  1. **Read File:** Use FileSpecialist to read app/src/api.py.  
  2. **Modify Code:** Instruct a CodeWriterSpecialist to add a new endpoint GET /v1/logs.  
  3. **Endpoint Logic:** This endpoint should read the specialisthub\_debug.log file and return the last 100 lines as plain text.  
  4. **Write File:** Use FileSpecialist to save the changes.  
  5. **Audit:** Use an Auditor to validate the syntax.

## **Phase 2: Real-time Agent Activity (WebSocket)**

This is the most complex phase, enabling live monitoring of agent workflows.

### **Task 2.1: Implement WebSocket Endpoint**

* **Objective:** Add a WebSocket endpoint to the FastAPI server for real-time communication.  
* **Specialist:** APISpecialist.  
* **Plan:**  
  1. **Read File:** Use FileSpecialist to read app/src/api.py.  
  2. **Modify Code:** Instruct CodeWriterSpecialist to add a WebSocket endpoint at WS /v1/ws/agent\_monitor. This will require adding a connection manager to handle active WebSocket connections.  
  3. **Write File:** Save changes.

### **Task 2.2: Integrate WebSocket with Workflow Runner**

* **Objective:** Modify the core workflow logic to push status updates to the WebSocket.  
* **Specialist:** WorkflowSpecialist (A new specialist focused on the orchestration logic in app/src/workflow/).  
* **Plan:**  
  1. **Read Files:** Use FileSpecialist to read app/src/workflow/runner.py and the api.py (to access the connection manager).  
  2. **Modify Code:** Instruct CodeWriterSpecialist to modify the WorkflowRunner (or the ChiefOfStaff logic). Before and after each specialist is called, the runner should broadcast a message to all connected WebSocket clients.  
  3. **Message Format:** The messages should be JSON objects, for example:  
     * {"type": "transition", "from": "Router", "to": "FileSpecialist"}  
     * {"type": "state\_update", "state": { ...current\_graph\_state... }}  
  4. **Write File:** Save changes.

## **Phase 3: System Control**

This phase adds the ability to manage the server from the UI.

### **Task 3.1: Implement Restart Endpoint**

* **Objective:** Create an endpoint that can gracefully restart the server process.  
* **Specialist:** APISpecialist.  
* **Plan:**  
  1. **Modify Code:** Instruct CodeWriterSpecialist to add a POST /v1/system/restart endpoint to api.py.  
  2. **Endpoint Logic:** The logic for this is non-trivial. A simple approach is to have it trigger a shell script that kills the current uvicorn process and starts a new one. This is a "proof of concept" implementation.  
  3. **Write File:** Save changes.