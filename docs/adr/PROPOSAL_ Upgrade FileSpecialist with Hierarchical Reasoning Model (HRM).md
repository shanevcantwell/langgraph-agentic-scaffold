

---

## **ADR: 000X \- Upgrade FileSpecialist with Hierarchical Reasoning Model (HRM)**

Date: August 21, 2025  
Status: Proposed  
Author: Shane Cantwell

### **1\. Context**

The current FileSpecialist relies on the primary LLM to determine the appropriate file operation and parameters. As demonstrated in the analysis of the "Display the last 20 rows of the log file" request, this leads to an inefficient multi-step process involving reading the entire file into memory and subsequent processing by a TextAnalysisSpecialist. This approach is resource-intensive, slow, and prone to failure with large files.

The Hierarchical Reasoning Model (HRM), a small but powerful reasoning engine, offers a more efficient and logical approach to such structured tasks. By embedding the reasoning for optimal tool usage directly within the FileSpecialist (powered by an HRM), we can streamline file operations and improve the overall performance and robustness of the agentic system.

##### **Further research: ./external/sapientinc/HRM github repo clone**

### **2\. Proposal**

We propose to upgrade the FileSpecialist to utilize a locally-run Hierarchical Reasoning Model (HRM) for determining the most efficient file operation and its parameters. This involves:

* **Integrating an HRM:** Incorporating a lightweight HRM (e.g., a 27M parameter model) that runs directly on the host CPU, similar to the proposed upgrade for the RouterSpecialist.  
* **Enhancing Tool Capabilities:** Modifying the underlying file operation tools (e.g., read\_file) to accept more specific parameters (e.g., head, tail, start\_line, end\_line).  
* **HRM-Driven Tool Selection & Parameterization:** Training the HRM to analyze user requests related to file manipulation and directly generate the most efficient tool\_name and tool\_input with appropriate parameters for the enhanced tools.

### **3\. Decision**

The FileSpecialist will be refactored to use a local HRM for reasoning about file operations. The underlying file operation tools will be enhanced to support more granular data access. The HRM will be trained to directly invoke these tools with optimal parameters based on the user's request.

### **4\. Consequences**

This architectural change will result in:

* **Significant Performance Improvement:** File operations will be executed much faster due to reduced overhead and more efficient data access.  
* **Reduced Resource Consumption:** We will eliminate the need to load entire files into memory for simple operations like displaying the last few lines. This lowers RAM usage and overall compute costs.  
* **Increased Robustness:** The system will be able to handle much larger files without failure.  
* **Simplified Workflow:** Many multi-step file-related tasks will be handled within a single step by the FileSpecialist.

However, this also introduces:

* **HRM Training Overhead:** We will need to dedicate resources to training an HRM specifically for the domain of file operations and efficient tool usage.  
* **Increased Complexity within the Specialist:** The FileSpecialist's internal logic will become more complex as it integrates and interacts with the HRM.

### **5\. Similar Considerations: String Manipulation**

The approach outlined for file operations is highly applicable to string manipulation tasks. Consider a request like "Extract all email addresses from the last 100 lines of the log file."

**Current Approach:**

1. FileSpecialist reads the entire log file.  
2. TextAnalysisSpecialist receives the entire file and uses an LLM to extract the last 100 lines.  
3. Another TextAnalysisSpecialist (or the same one in a subsequent call) receives the 100 lines and uses an LLM with regex capabilities to extract email addresses.

**HRM-Powered Approach:**

1. FileSpecialist (with HRM) analyzes the request.  
2. HRM determines the need to read\_file with tail=100.  
3. The (potentially enhanced) TextAnalysisSpecialist (also potentially HRM-powered or guided by the FileSpecialist's intent) receives the 100 lines.  
4. An efficient, potentially regex-based tool or a focused reasoning step within the TextAnalysisSpecialist (guided by the initial request's intent understood by the FileSpecialist's HRM) extracts the email addresses.

While string manipulation might still involve a subsequent TextAnalysisSpecialist, the crucial efficiency gain comes from the FileSpecialist's ability to retrieve only the necessary portion of the data *before* any text analysis occurs, significantly reducing the context size and computational cost.

### **6\. Training Data for the HRM**

Training an HRM for file and string operations would require a dataset that captures the mapping between user intents and optimal tool usage. A potential dataset structure could look like this:

**Examples:**

| User Request | Available Tools | Optimal Tool Call |
| :---- | :---- | :---- |
| "Display the first 10 lines of my notes.txt" | \["read\_file"\] (enhanced with head), \["write\_file"\], \["list\_directory"\] | {"tool\_name": "read\_file", "tool\_input": {"file\_path": "notes.txt", "head": 10}} |
| "Append 'Remember to buy milk' to my todo.txt" | \["read\_file"\], \["write\_file"\] (enhanced with append), \["list\_directory"\] | {"tool\_name": "write\_file", "tool\_input": {"file\_path": "todo.txt", "mode": "append", "content": "Remember to buy milk\\n"}} |
| "List all .py files in the current folder" | \["read\_file"\], \["write\_file"\], \["list\_directory"\] (enhanced with file\_extension\_filter) | {"tool\_name": "list\_directory", "tool\_input": {"path": "./", "file\_extension\_filter": ".py"}} |
| "Extract all URLs from the last 50 lines of web\_log.txt" | \["read\_file"\] (enhanced with tail), \["extract\_urls\_from\_text"\] | {"tool\_name": "read\_file", "tool\_input": {"file\_path": "web\_log.txt", "tail": 50}} (followed by TextAnalysis call) |
| "Replace all instances of 'error' with 'warning' in config.ini" | \["read\_file"\], \["write\_file"\] (enhanced with replace\_text), \["list\_directory"\] | {"tool\_name": "read\_file", "tool\_input": {"file\_path": "config.ini"}} (followed by WriteFile with replacement) |
| "Get the size of the image.png file" | \["read\_file"\], \["get\_file\_metadata"\] (enhanced with info=\['size'\]), \["list\_directory"\] | {"tool\_name": "get\_file\_metadata", "tool\_input": {"file\_path": "image.png", "info": \["size"\]}} |

This dataset would need to cover a wide range of common file and string manipulation intents and demonstrate the optimal way to achieve them using the available tools and their parameters. The complexity of the training data would depend on the sophistication of the HRM being used. Techniques like synthetic data generation could be employed to augment the training set.

---

This proposal outlines a significant architectural improvement that leverages the strengths of a reasoning-focused model for structured tasks, leading to a more efficient and robust agentic system.