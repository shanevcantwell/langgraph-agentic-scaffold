---

## **📝 Guide 1: Refactor Specialist Initialization & Configuration**
Completed 8/28/2025 svc & Gemini Code Assist

The goal of this first, most critical step is to **decouple specialists from the global ConfigLoader** and centralize configuration management in the ChiefOfStaff. This makes specialists more modular and testable.

---

### **Step 1: Centralize Environment Variable Loading**

Modify the ConfigLoader to be the single source of truth for the final, runnable configuration, including resolved API keys and URLs from environment variables.

In

app/src/utils/config\_loader.py, add the logic to resolve environment variables directly into the LLM provider configurations1.

---

### **Step 2: Refactor the AdapterFactory**

Update the AdapterFactory so it's no longer a singleton. It will now be initialized with the fully resolved configuration, which it receives from the ChiefOfStaff.

In app/src/llm/factory.py:

* Change the  
  \_\_init\_\_ method to accept full\_config: Dict\[str, Any\] and store it on self.full\_config2.

* In the  
  create\_adapter method, remove the line that calls ConfigLoader().get\_config() and use self.full\_config instead3.

* Update the adapter instantiations (e.g., for Gemini) to get the  
  api\_key and base\_url directly from the provider\_config dictionary instead of calling os.getenv4444.

---

### **Step 3: Update the Base Specialist Contract**

Modify the BaseSpecialist class to accept its configuration via dependency injection instead of fetching it itself.

In app/src/specialists/base.py:

* Change the  
  \_\_init\_\_ method signature to \_\_init\_\_(self, specialist\_name: str, specialist\_config: Dict\[str, Any\])5.

* Remove the line that calls ConfigLoader.  
* Assign the incoming  
  specialist\_config directly to self.specialist\_config6.

---

### **Step 4: Update All Specialist Constructors**

Go through **every single specialist file** and update its \_\_init\_\_ method to match the new signature from BaseSpecialist.

For example, in app/src/specialists/critic\_specialist.py:

* **Change the \_\_init\_\_ method from def \_\_init\_\_(self, specialist\_name: str): to def \_\_init\_\_(self, specialist\_name: str, specialist\_config: Dict\[str, Any\]):**.  
* **Update the super().\_\_init\_\_ call to super().\_\_init\_\_(specialist\_name, specialist\_config)**7.

* Repeat this for all specialists888888888888888888888888888888888888.

---

### **Step 5: Update the ChiefOfStaff Orchestrator**

Finally, modify the ChiefOfStaff to orchestrate this new, decoupled pattern.

In app/src/workflow/chief\_of\_staff.py:

* In  
  \_load\_and\_configure\_specialists, create a single instance of AdapterFactory and pass it self.config9.

* In the specialist loading loop, update the instantiation call to pass both the  
  specialist\_name and the config dictionary: instance \= SpecialistClass(specialist\_name=name, specialist\_config=config)10.

* When creating adapters, use the single  
  adapter\_factory instance you created earlier instead of creating a new one each time111111111111111111.

---

## **🛠️ Guide 2: Implement the Modern Procedural Specialist Pattern**

The goal here is to replace the old, complex WrappedCodeSpecialist pattern with a simpler, more direct **procedural specialist** for integrating pip-installed libraries. We will use open\_interpreter\_specialist as the example.

---

### **Step 1: Update the Configuration**

In config.yaml, change the open\_interpreter\_specialist to reflect the new pattern.

* Change its  
  type from "wrapped\_code" to "procedural"12.

* Remove the obsolete  
  wrapper\_path and class\_name keys13.

* Add the  
  external\_llm\_provider\_binding key to specify which LLM configuration open-interpreter should use, reusing an existing provider definition14.

---


### **Step 2: Refactor the Specialist Class**

Rewrite app/src/specialists/open\_interpreter\_specialist.py completely.

* It should now inherit directly from  
  BaseSpecialist, not WrappedCodeSpecialist15.

* The  
  \_\_init\_\_ method should be simple, primarily calling super and setting up initial state16.

* Create a lazy \_configure\_interpreter method. This method will read  
  self.specialist\_config.get("resolved\_external\_llm\_config") to configure the interpreter with the LLM details injected by the ConfigLoader17. This keeps the specialist decoupled.

* Move the logic for executing the interpreter's  
  chat function into the \_execute\_logic method18181818.

---

### **Step 3: Update Developer Documentation**

Ensure the project's documentation reflects this superior pattern.

* In  
  docs/CREATING\_A\_NEW\_SPECIALIST.md, replace the section on WrappedCodeSpecialist with a new guide on creating a procedural specialist for pip-installed libraries19.

* Use the new  
  open-interpreter integration as the primary example20.

---

## **🛡️ Guide 3: Implement Centralized Precondition Checks**

The final step is to make the system more robust by adding two forms of centralized dependency checking: **environment checks at startup** and **declarative state checks at runtime**.

---

### **Part 1: Environment Pre-flight Checks (Startup-time)**

This pattern ensures a specialist's external dependencies (like a required package) are met before the application finishes starting.

1. **Add the Hook:** In app/src/specialists/base.py, add the new method \_perform\_pre\_flight\_checks(self) \-\> bool to the BaseSpecialist class, which simply returns True by default21.

2. **Enforce the Check:** In app/src/workflow/chief\_of\_staff.py, inside the \_load\_and\_configure\_specialists loop, call instance.\_perform\_pre\_flight\_checks() immediately after a specialist is instantiated. If it returns  
   False, log an error and continue to the next specialist, effectively disabling the one that failed22.

3. **Implement the Check:** In app/src/specialists/open\_interpreter\_specialist.py, override \_perform\_pre\_flight\_checks. Inside, use a try...except ImportError block to check if the interpreter package can be imported. Return  
   True on success and False on failure, with appropriate logging23.

---

### **Part 2: Declarative State Artifact Checks (Runtime)**

This pattern allows specialists to declare their data dependencies in the config file, simplifying their internal logic.

1. **Create a Self-Correction Helper:** In a new file, app/src/specialists/helpers.py, create the function create\_missing\_artifact\_response. This function will generate a standardized message that the  
   Router can use to self-correct the workflow when a dependency is missing24242424.

2. **Declare Dependencies in Config:** In config.yaml, for any specialist that unconditionally requires an artifact from the state, add the requires\_artifacts: \["artifact\_name"\] key. For example, add  
   requires\_artifacts: \["system\_plan"\] to the web\_builder25.

3. **Implement the Centralized Check:** In app/src/workflow/chief\_of\_staff.py, enhance the \_create\_safe\_executor method. This wrapper should now:  
   * Read the  
     requires\_artifacts list from the specialist's config26.

   * At runtime (when  
     safe\_executor is called), check the GraphState for the presence of these artifacts27.

   * If any are missing, call the  
     create\_missing\_artifact\_response helper and return its result immediately, bypassing the specialist's main logic28.

4. **Refactor Specialists:** With the centralized check in place, you can now remove the manual boilerplate checks from specialists like WebBuilder and TextAnalysisSpecialist, as the orchestration layer now handles it for them.