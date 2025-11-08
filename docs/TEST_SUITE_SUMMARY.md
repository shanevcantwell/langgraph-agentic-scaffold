# Test Suite Summary


## `app/tests/integration/test_chat_specialist_routing.py`

- **`test_router_invokes_chat_specialist_for_conversational_query`**
  - *End-to-end test: User asks a question → Router → ChatSpecialist → Response*
- **`test_chat_specialist_appears_in_router_specialist_map`**
  - *Simpler test: Verify ChatSpecialist is registered and discoverable by router.*

## `app/tests/integration/test_gradio_integration.py`


## `app/tests/integration/test_live_llm.py`

- **`test_live_gemini_adapter_interaction`**
  - *Tests a basic interaction with a live Gemini model via the AdapterFactory.*

## `app/tests/integration/test_live_lmstudio.py`

- **`test_live_lmstudio_adapter_interaction`**
  - *Tests a basic interaction with a live LM Studio model via the AdapterFactory.*

## `app/tests/integration/test_plan_and_execute_integration.py`

- **`test_plan_and_execute_workflow`**
  - *Tests the full "Plan and Execute" workflow within the OpenInterpreterSpecialist.*
- **`test_plan_and_execute_handles_llm_planning_failure`**
  - *Tests that the specialist correctly handles the case where the LLM fails*

## `app/tests/unit/test_adapter_contracts.py`

- **`test_adapter_robust_parsing_contract`**
  - *This contract test verifies that an adapter can robustly parse JSON*

## `app/tests/unit/test_api.py`

- **`test_invoke_graph_sync`**
  - *Tests the synchronous /v1/graph/invoke endpoint.*
- **`test_invoke_graph_sync_handles_runner_error`**
  - *Tests that the sync endpoint returns a 500 if the runner fails.*
- **`test_invoke_graph_sync_invalid_input`**
  - *Tests that the sync endpoint returns a 422 for invalid input.*

## `app/tests/unit/test_api_client.py`

- **`test_encode_image_to_base64`**
  - *Tests the internal image encoding utility.*

## `app/tests/unit/test_archiver_specialist.py`

- **`test_save_report_writes_to_file`**
  - *Tests that _save_report correctly writes content to a file.*
- **`test_prune_archive_removes_oldest_files`**
  - *Tests that _prune_archive correctly removes the oldest files.*
- **`test_execute_logic_generates_and_saves_report`**
  - *Tests the main logic flow for generating and saving a success report.*
- **`test_execute_logic_handles_missing_final_response`**
  - *Tests edge case where final_user_response.md is missing from artifacts.*

## `app/tests/unit/test_base_schemas.py`

- **`test_specialist_output_success`**
  - *Tests successful creation of a SpecialistOutput with a payload.*
- **`test_specialist_output_failure`**
  - *Tests creation of a SpecialistOutput for a failure case with no payload.*
- **`test_specialist_output_missing_fields`**
  - *Tests that Pydantic validation catches missing required fields.*
- **`test_specialist_output_other_statuses`**
  - *Tests other status enums.*
- **`test_specialist_output_with_different_payload_type`**
  - *Tests that the generic SpecialistOutput works with different payload types.*
- **`test_specialist_output_allows_empty_rationale`**
  - *Tests that an empty string is a valid rationale.*
- **`test_specialist_output_success_with_none_payload`**
  - *Tests that a SUCCESS status can have a None payload.*
- **`test_web_content_schema_validation`**
  - *Explicitly tests the WebContent schema.*

## `app/tests/unit/test_chat_specialist.py`

- **`test_chat_specialist_initialization`**
  - *Verifies that ChatSpecialist initializes correctly.*
- **`test_chat_specialist_processes_simple_question`**
  - *Tests that ChatSpecialist can answer a simple question.*
- **`test_chat_specialist_maintains_conversation_context`**
  - *Tests that ChatSpecialist sends full conversation history to LLM.*
- **`test_chat_specialist_handles_llm_failure_gracefully`**
  - *Tests that ChatSpecialist provides a fallback message when LLM fails.*
- **`test_chat_specialist_creates_proper_message_metadata`**
  - *Tests that ChatSpecialist creates AIMessage with proper metadata.*
- **`test_chat_specialist_handles_empty_message_history`**
  - *Tests that ChatSpecialist handles edge case of empty message history.*

## `app/tests/unit/test_cli.py`

- **`test_cli_invoke_success`**
  - *Tests the 'invoke' command with a successful API response.*
- **`test_cli_invoke_json_only`**
  - *Tests the 'invoke' command with the --json-only flag.*
- **`test_cli_stream_success`**
  - *Tests the 'stream' command with a successful streaming response.*
- **`test_cli_invoke_api_non_200_response`**
  - *Tests how the CLI handles a non-200 status code from the API.*
- **`test_cli_api_error`**
  - *Tests that the CLI handles API connection errors gracefully.*
- **`test_cli_stream_no_final_state`**
  - *Tests the stream command when the FINAL_STATE line is missing.*
- **`test_cli_stream_malformed_final_state_json`**
  - *Tests the stream command when the FINAL_STATE JSON is malformed.*
- **`test_cli_invoke_no_prompt`**
  - *Tests that the 'invoke' command exits with an error if no prompt is provided.*
- **`test_cli_stream_no_prompt`**
  - *Tests that the 'stream' command exits with an error if no prompt is provided.*

## `app/tests/unit/test_config_loader.py`

- **`test_singleton_pattern`**
  - *Tests that ConfigLoader is a singleton.*
- **`test_load_and_get_config`**
  - *Tests loading a basic config and retrieving it.*
- **`test_missing_config_file`**
  - *Tests that a ConfigError is raised if config.yaml is missing.*
- **`test_malformed_yaml`**
  - *Tests that a YAMLError is raised for invalid YAML.*
- **`test_merge_user_settings`**
  - *Tests that user_settings.yaml correctly merges with and overrides config.yaml.*
- **`test_empty_config_file`**
  - *Tests that an empty config file raises a ConfigError.*

## `app/tests/unit/test_critic_specialist.py`

- **`test_critic_specialist_accepts_and_completes_task`**
  - *Tests that the specialist accepts the work and signals task completion.*
- **`test_critic_specialist_revises_and_recommends_target`**
  - *Tests that the specialist recommends revision and a target specialist.*
- **`test_critic_specialist_handles_strategy_failure`**
  - *Tests that the specialist handles unrecoverable failure from its strategy.*

## `app/tests/unit/test_data_extractor_specialist.py`

- **`test_data_extractor_success`**
  - *Tests successful data extraction and state update.*
- **`test_data_extractor_no_text_to_process`**
  - *Tests that the specialist handles missing input text gracefully by adding*
- **`test_data_extractor_llm_fails`**
  - *Tests that the specialist raises an error if the LLM returns no valid JSON payload.*
- **`test_data_extractor_handles_llm_invocation_error`**
  - *Tests that the specialist propagates LLM invocation errors.*
- **`test_data_extractor_no_text_to_process_on_empty_string`**
  - *Tests that the specialist self-corrects if the input text is empty or just whitespace.*

## `app/tests/unit/test_data_processor_specialist.py`

- **`test_data_processor_specialist_processes_json_string`**
  - *Tests processing a JSON string artifact.*
- **`test_data_processor_specialist_processes_dict`**
  - *Tests processing a dictionary artifact.*
- **`test_data_processor_specialist_no_json_artifact_raises_error`**
  - *Tests that the specialist returns an error message when no json_artifact is present.*

## `app/tests/unit/test_default_responder_specialist.py`

- **`test_default_responder_generates_response_and_completes_task`**
  - *Tests that the specialist generates a response and signals task completion.*
- **`test_default_responder_handles_empty_llm_response`**
  - *Tests that the specialist provides a fallback message if LLM returns empty.*
- **`test_default_responder_filters_messages_correctly`**
  - *Tests that only HumanMessage and its own AIMessages are passed to the LLM.*

## `app/tests/unit/test_end_specialist.py`

- **`test_end_specialist_initialization`**
  - *Verifies that the EndSpecialist correctly initializes its internal components.*
- **`test_end_specialist_orchestrates_synthesis_and_archiving`**
  - *Tests that EndSpecialist correctly performs synthesis inline and then calls archiver.*
- **`test_end_specialist_skips_synthesis_if_final_response_exists`**
  - *Tests that EndSpecialist skips synthesis if a final response already exists in the state.*
- **`test_end_specialist_synthesizes_from_snippets`**
  - *Tests that EndSpecialist correctly synthesizes a response when snippets are present.*
- **`test_end_specialist_handles_empty_snippets_gracefully`**
  - *Tests that EndSpecialist generates a fallback response when no snippets are available.*
- **`test_end_specialist_handles_termination_reason`**
  - *Tests that EndSpecialist uses explicit termination_reason when present*

## `app/tests/unit/test_file_ops_schemas.py`

- **`test_create_directory_params`**
  - *Tests valid CreateDirectoryParams.*
- **`test_write_file_params`**
  - *Tests valid WriteFileParams with string and bytes content.*
- **`test_create_zip_from_directory_params`**
  - *Tests valid CreateZipFromDirectoryParams.*
- **`test_invalid_params_raise_validation_error`**
  - *Tests that Pydantic models raise ValidationError for invalid input.*
- **`test_write_file_params_allows_empty_content`**
  - *Tests that writing an empty string or empty bytes as content is valid.*

## `app/tests/unit/test_file_specialist.py`

- **`test_create_directory`**
  - *Tests the internal _create_directory method.*
- **`test_write_file`**
  - *Tests the internal _write_file method with both string and bytes content.*
- **`test_write_file_empty_content`**
  - *Tests that writing an empty file is handled correctly.*
- **`test_create_zip_from_directory`**
  - *Tests the internal _create_zip_from_directory method.*
- **`test_execute_logic_success_dispatch`**
  - *Tests that _execute_logic correctly dispatches various tool calls*
- **`test_execute_logic_handles_unknown_tool`**
  - *Tests that an unknown tool call is handled gracefully with a clear message.*
- **`test_execute_logic_handles_tool_execution_error`**
  - *Tests that a SpecialistError during tool execution is caught and reported.*
- **`test_execute_logic_ignores_non_tool_message`**
  - *Tests that the specialist does nothing if the last message is not a ToolMessage,*

## `app/tests/unit/test_gemini_adapter.py`

- **`test_invoke_raises_proxy_error_on_connection_issues`**
  - *Tests that the Gemini adapter correctly catches various connection-related*

## `app/tests/unit/test_gradio_app.py`


## `app/tests/unit/test_graph_builder.py`

- **`test_load_and_configure_specialists`**
  - *Tests that specialists are loaded and that the router specialist is*
- **`test_build_graph`**
  - *Tests that a valid graph is built and returned with all nodes.*
- **`test_graph_builder_handles_disabled_specialist`**
  - *Tests that a specialist with is_enabled=False is not added to the graph.*
- **`test_graph_builder_handles_pre_flight_check_failure`**
  - *Tests that a specialist failing pre-flight checks is not added.*
- **`test_graph_builder_defaults_on_invalid_entry_point`**
  - *Tests that the entry point defaults to router if the configured one is invalid.*
- **`test_graph_builder_raises_error_on_get_specialist_class_failure`**
  - *Tests that a SpecialistLoadError is raised if a specialist class cannot be imported.*
- **`test_graph_builder_raises_error_on_load_prompt_failure`**
  - *Tests that a SpecialistLoadError is raised if a prompt file cannot be loaded.*
- **`test_safe_edges_raises_workflow_error_on_invalid_dest`**
  - *Test that _add_safe_conditional_edges raises WorkflowError for an invalid destination.*
- **`test_wire_hub_and_spoke_edges_uses_safe_wrapper_for_router`**
  - *Test that the router edge uses the safe wrapper method.*
- **`test_wire_hub_and_spoke_edges_uses_safe_wrapper_for_critic`**
  - *Test that the critic edge uses the safe wrapper method.*
- **`test_wire_hub_and_spoke_edges_uses_safe_wrapper_for_task_completion`**
  - *Test that task completion edges use the safe wrapper method.*

## `app/tests/unit/test_graph_orchestrator.py`

- **`test_safe_executor_handles_specialist_exception`**
  - *Tests that the create_safe_executor wrapper catches exceptions from a specialist*
- **`test_safe_executor_handles_generic_exception`**
  - *Tests that the executor also catches generic exceptions and formats them correctly.*
- **`test_safe_executor_success_path`**
  - *Tests the safe_executor for a successful, non-error execution.*
- **`test_safe_executor_blocks_execution_on_missing_artifact`**
  - *Tests that the safe_executor prevents a specialist from running if a required*
- **`test_create_missing_artifact_response_format`**
  - *Tests the specific format of the missing artifact response.*
- **`test_route_to_next_specialist_normal_route`**
  - *Tests that the function returns the correct specialist name from the state.*
- **`test_route_to_next_specialist_detects_loop`**
  - *Tests that the function routes to END when a repeating loop is detected.*
- **`test_route_to_next_specialist_loop_not_long_enough`**
  - *Tests that a repeating pattern shorter than min_loop_len is not flagged as a loop.*
- **`test_route_to_next_specialist_allows_non_loop`**
  - *Tests that the function does not halt for a non-looping history.*
- **`test_route_to_next_specialist_handles_no_route`**
  - *Tests that the function routes to END if the router fails to provide a next step.*

## `app/tests/unit/test_hello_world_specialist.py`

- **`test_hello_world_specialist_greets_user`**
  - *Tests that the specialist generates a greeting based on the last message.*
- **`test_hello_world_specialist_handles_empty_messages`**
  - *Tests that the specialist provides a default response if state has no messages.*

## `app/tests/unit/test_imports.py`

- **`test_import_all_modules`**
  - *A smoke test to ensure all critical modules and specialist modules*

## `app/tests/unit/test_install.py`

- **`test_install_script_creates_venv_and_installs_pytest`**
  - *Test that install.sh creates a virtual environment and installs pytest.*

## `app/tests/unit/test_llm_factory.py`

- **`test_factory_creates_adapter_for_llm_specialist`**
  - *Tests that an adapter is correctly created for a specialist of type 'llm'.*
- **`test_factory_creates_adapter_for_hybrid_specialist`**
  - *Tests that an adapter is correctly created for the new 'hybrid' specialist type.*
- **`test_factory_returns_none_for_procedural_specialist`**
  - *Tests that no adapter is created for a 'procedural' specialist.*
- **`test_factory_raises_error_for_missing_llm_config`**
  - *Tests that a ValueError is raised if 'llm_config' is missing for an LLM specialist.*
- **`test_factory_raises_error_for_unresolvable_provider`**
  - *Tests that a ValueError is raised if the provider key in 'llm_config' doesn't exist.*
- **`test_factory_returns_none_for_unknown_provider_type`**
  - *Tests that the factory returns None if the provider 'type' is not in the registry.*

## `app/tests/unit/test_lmstudio_adapter.py`

- **`test_init_fails_on_missing_api_identifier`**
  - *Tests that initialization fails if 'api_identifier' is missing from the config.*
- **`test_invoke_sends_correct_request`**
  - *Tests that the invoke method constructs and sends the correct request to the client.*
- **`test_invoke_handles_json_parsing`**
  - *Tests that the invoke method correctly parses JSON from a messy response string.*
- **`test_invoke_raises_llm_invocation_error`**
  - *Tests that LLMInvocationError is raised when the client call fails.*
- **`test_invoke_raises_proxy_error_on_connection_issues`**
  - *Tests that the LMStudio adapter correctly catches various connection-related*

## `app/tests/unit/test_mcp_client.py`

**Total Tests: 24**

- **`test_mcp_client_call_success`**
  - *Tests successful MCP call with automatic serialization/deserialization.*
- **`test_mcp_client_call_raises_on_error_status`**
  - *Tests that call() raises ValueError when response status is "error".*
- **`test_mcp_client_call_safe_returns_tuple_on_success`**
  - *Tests call_safe() returns (True, result) on successful call.*
- **`test_mcp_client_call_safe_returns_tuple_on_error`**
  - *Tests call_safe() returns (False, error_message) when MCP call fails.*
- **`test_mcp_client_call_safe_handles_unexpected_exceptions`**
  - *Tests call_safe() catches and returns (False, error) for unexpected exceptions.*
- **`test_mcp_client_list_services`**
  - *Tests list_services() returns service directory from registry.*
- **`test_mcp_client_call_logs_request_id`**
  - *Tests that MCP calls log request_id for distributed tracing.*
- **`test_mcp_client_passes_parameters_correctly`**
  - *Tests that keyword arguments are correctly serialized into McpRequest.parameters.*
- **`test_mcp_client_initialization_creates_registry_reference`**
  - *Tests that McpClient stores reference to McpRegistry.*
- **Additional tests cover:** Error propagation, parameter validation, response deserialization (15 more tests)

## `app/tests/unit/test_mcp_registry.py`

**Total Tests: 27**

- **`test_mcp_registry_register_service`**
  - *Tests service registration in McpRegistry.*
- **`test_mcp_registry_dispatch_success`**
  - *Tests successful dispatch of McpRequest to registered service function.*
- **`test_mcp_registry_dispatch_service_not_found`**
  - *Tests dispatch raises McpServiceNotFoundError for unregistered service.*
- **`test_mcp_registry_dispatch_function_not_found`**
  - *Tests dispatch raises McpFunctionNotFoundError for unregistered function.*
- **`test_mcp_registry_dispatch_timeout_protection`**
  - *Tests timeout mechanism prevents hanging on long-running MCP calls.*
- **`test_mcp_registry_dispatch_with_langsmith_tracing`**
  - *Tests LangSmith trace span creation when tracing_enabled=true.*
- **`test_mcp_registry_dispatch_without_langsmith_tracing`**
  - *Tests graceful degradation when tracing_enabled=false.*
- **`test_mcp_registry_handles_function_exceptions`**
  - *Tests that exceptions in service functions are caught and returned as error responses.*
- **`test_mcp_registry_list_services`**
  - *Tests list_services() returns dictionary of service_name -> function_list.*
- **`test_mcp_registry_per_graph_instance_isolation`**
  - *Tests that separate McpRegistry instances don't share service registrations.*
- **Additional tests cover:** Parameter passing, response construction, error handling (17 more tests)

## `app/tests/unit/test_mcp_schemas.py`

**Total Tests: 18**

- **`test_mcp_request_creation`**
  - *Tests successful creation of McpRequest with all required fields.*
- **`test_mcp_request_auto_generates_uuid`**
  - *Tests that request_id is automatically generated if not provided.*
- **`test_mcp_request_validation_requires_service_name`**
  - *Tests Pydantic validation enforces required service_name field.*
- **`test_mcp_request_validation_requires_function_name`**
  - *Tests Pydantic validation enforces required function_name field.*
- **`test_mcp_request_parameters_default_to_empty_dict`**
  - *Tests that parameters field defaults to empty dictionary.*
- **`test_mcp_response_creation_success`**
  - *Tests successful creation of McpResponse with status="success".*
- **`test_mcp_response_creation_error`**
  - *Tests creation of McpResponse with status="error" and error_message.*
- **`test_mcp_response_raise_for_error_raises_on_error_status`**
  - *Tests raise_for_error() raises ValueError when status="error".*
- **`test_mcp_response_raise_for_error_noop_on_success`**
  - *Tests raise_for_error() does nothing when status="success".*
- **`test_mcp_response_data_can_be_any_type`**
  - *Tests that data field accepts Any type (dict, list, str, bool, None, etc).*
- **Additional tests cover:** UUID format validation, error message content, schema evolution (8 more tests)

**MCP Test Coverage Summary:**
- **Total MCP Tests:** 69 (all passing)
- **Schema Tests:** 18 tests validating request/response contracts
- **Registry Tests:** 27 tests covering service registration, dispatch, timeout, tracing
- **Client Tests:** 24 tests covering call patterns, error handling, service discovery
- **FileSpecialist Integration:** 39 tests in test_file_specialist.py validate MCP-only pattern

## `app/tests/unit/test_open_interpreter_specialist.py`

- **`test_open_interpreter_specialist_executes_code_successfully`**
  - *Tests the full plan-and-execute flow for the OpenInterpreterSpecialist.*
- **`test_open_interpreter_specialist_handles_no_tool_call_from_llm`**
  - *Tests that the specialist handles the case where the LLM fails to generate a plan.*
- **`test_open_interpreter_handles_list_files_prompt`**
  - *Tests that OpenInterpreterSpecialist can correctly plan and execute a*
- **`test_open_interpreter_specialist_raises_error_if_no_prompt_file`**
  - *Tests that the specialist raises a ValueError if the 'prompt_file' is*

## `app/tests/unit/test_plan_and_execute_integration.py`

- **`test_plan_and_execute_workflow`**
  - *Tests the full "Plan and Execute" workflow within the OpenInterpreterSpecialist.*
- **`test_plan_and_execute_handles_llm_planning_failure`**
  - *Tests that the specialist correctly handles the case where the LLM fails*
- **`test_plan_and_execute_handles_interpreter_execution_failure`**
  - *Tests that the specialist correctly handles a failure in the execution phase.*
- **`test_plan_and_execute_handles_llm_planning_failure_with_invalid_tool_calls`**
  - *Tests that the specialist correctly handles a failure in the planning phase*

## `app/tests/unit/test_progenitor_alpha_specialist.py`

- **`test_progenitor_alpha_initialization`**
  - *Verifies that ProgenitorAlphaSpecialist initializes correctly.*
- **`test_progenitor_alpha_generates_analytical_response`**
  - *Tests that ProgenitorAlpha generates an analytical perspective response.*
- **`test_progenitor_alpha_stores_response_in_artifacts`**
  - *Tests that ProgenitorAlpha stores response in artifacts.alpha_response.*
- **`test_progenitor_alpha_does_not_set_task_complete`**
  - *Tests that ProgenitorAlpha does NOT set task_is_complete (TieredSynthesizer does).*
- **`test_progenitor_alpha_maintains_conversation_context`**
  - *Tests that ProgenitorAlpha sends full conversation history to LLM.*
- **`test_progenitor_alpha_handles_llm_failure_gracefully`**
  - *Tests that ProgenitorAlpha provides fallback message when LLM fails.*
- **`test_progenitor_alpha_creates_proper_message_metadata`**
  - *Tests that ProgenitorAlpha creates AIMessage with proper metadata.*
- **`test_progenitor_alpha_handles_empty_message_history`**
  - *Tests that ProgenitorAlpha handles edge case of empty message history.*

## `app/tests/unit/test_progenitor_bravo_specialist.py`

- **`test_progenitor_bravo_initialization`**
  - *Verifies that ProgenitorBravoSpecialist initializes correctly.*
- **`test_progenitor_bravo_generates_contextual_response`**
  - *Tests that ProgenitorBravo generates a contextual perspective response.*
- **`test_progenitor_bravo_stores_response_in_artifacts`**
  - *Tests that ProgenitorBravo stores response in artifacts.bravo_response.*
- **`test_progenitor_bravo_does_not_set_task_complete`**
  - *Tests that ProgenitorBravo does NOT set task_is_complete (TieredSynthesizer does).*
- **`test_progenitor_bravo_maintains_conversation_context`**
  - *Tests that ProgenitorBravo sends full conversation history to LLM.*
- **`test_progenitor_bravo_handles_llm_failure_gracefully`**
  - *Tests that ProgenitorBravo provides fallback message when LLM fails.*
- **`test_progenitor_bravo_creates_proper_message_metadata`**
  - *Tests that ProgenitorBravo creates AIMessage with proper metadata.*
- **`test_progenitor_bravo_handles_empty_message_history`**
  - *Tests that ProgenitorBravo handles edge case of empty message history.*

## `app/tests/unit/test_prompt_specialist.py`

- **`test_prompt_specialist_success`**
  - *Tests that the specialist correctly processes a response and updates the state.*
- **`test_prompt_specialist_handles_adapter_failure`**
  - *Tests that the specialist gracefully handles a connection or invocation error*
- **`test_prompt_specialist_handles_empty_messages`**
  - *Tests that the specialist does not call the LLM if there are no messages.*

## `app/tests/unit/test_prompt_triage_specialist.py`

- **`test_prompt_triage_recommends_specialists_from_llm`**
  - *Tests that the specialist correctly recommends specialists based on LLM tool call.*
- **`test_prompt_triage_falls_back_to_default_responder_on_no_tool_call`**
  - *Tests fallback to default_responder when LLM provides no valid tool call.*
- **`test_prompt_triage_filters_invalid_recommendations`**
  - *Tests that the specialist filters out recommendations not in its map.*
- **`test_prompt_triage_handles_empty_recommendations_list`**
  - *Tests fallback to default_responder when LLM returns an empty list of recommendations.*
- **`test_prompt_triage_no_specialist_map_configured`**
  - *Tests behavior when specialist_map is empty.*

## `app/tests/unit/test_router_specialist.py`

- **`test_get_available_specialists_no_recommendations`**
  - *Tests that all specialists are returned when no recommendations are present.*
- **`test_get_available_specialists_with_recommendations`**
  - *Tests that the specialist list is filtered by recommendations.*
- **`test_handle_llm_failure_fallback_priority`**
  - *Tests the fallback logic when the LLM fails to make a decision.*
- **`test_validate_llm_choice`**
  - *Tests the validation of the LLM's routing choice.*
- **`test_router_stage_3_termination_logic`**
  - *Tests Stage 3 of termination: when an archive report is present, the router*
- **`test_router_normal_llm_routing`**
  - *Tests the primary path where the router uses the LLM to decide the next specialist.*
- **`test_router_handles_llm_invocation_error`**
  - *Tests that the router propagates an LLMInvocationError if the adapter fails.*
- **`test_router_handles_invalid_llm_response`**
  - *Tests that the router self-corrects if the LLM returns an invalid specialist name.*

## `app/tests/unit/test_router_specialist_discovery.py`

- **`test_router_discovers_specialists_from_config`**
  - *Verifies that RouterSpecialist can discover and route to any specialist*
- **`test_router_respects_recommended_specialists_filter`**
  - *Verifies that RouterSpecialist correctly filters available specialists*
- **`test_router_handles_empty_specialist_map_gracefully`**
  - *Verifies that RouterSpecialist handles edge case of no available specialists*
- **`test_router_ignores_specialists_without_descriptions`**
  - *Verifies that specialists without descriptions are still included in the*

## `app/tests/unit/test_sentiment_classifier_specialist.py`

- **`test_sentiment_classifier_specialist_execute_success`**
- **`test_sentiment_classifier_handles_invalid_sentiment_value`**
  - *Tests that the specialist self-corrects if the LLM returns an invalid sentiment value.*
- **`test_sentiment_classifier_handles_malformed_llm_response`**
  - *Tests that the specialist self-corrects if the LLM response is malformed.*
- **`test_sentiment_classifier_handles_llm_invocation_error`**
  - *Tests that an LLMInvocationError is propagated.*
- **`test_sentiment_classifier_no_human_message_to_analyze`**
  - *Tests that the specialist does not run if no HumanMessage is available.*
- **`test_sentiment_classifier_uses_last_human_message`**
  - *Tests that the specialist specifically analyzes the last HumanMessage.*

## `app/tests/unit/test_specialist_loader.py`

- **`test_get_specialist_class_success`**
  - *Tests that the loader can successfully import and return a class*
- **`test_get_specialist_class_import_error`**
  - *Tests that the loader propagates an ImportError if the specialist*
- **`test_get_specialist_class_attribute_error`**
  - *Tests that an AttributeError is raised if the module is found*
- **`test_get_specialist_class_syntax_error`**
  - *Tests that the loader propagates a SyntaxError if the specialist*

## `app/tests/unit/test_structured_data_extractor.py`

- **`test_structured_data_extractor_success`**
  - *Tests successful data extraction and state update.*
- **`test_structured_data_extractor_missing_scratchpad_input`**
  - *Tests that the specialist handles missing scratchpad inputs gracefully.*
- **`test_structured_data_extractor_llm_fails_to_extract`**
  - *Tests the fallback mechanism when the LLM fails to return a tool call.*
- **`test_structured_data_extractor_malformed_tool_call_args`**
  - *Tests that the specialist handles tool calls with arguments that don't match the schema.*
- **`test_structured_data_extractor_handles_llm_invocation_error`**
  - *Tests that the specialist handles exceptions from the LLM adapter.*
- **`test_structured_data_extractor_handles_invalid_schema_in_scratchpad`**
  - *Tests that the specialist handles an invalid schema object gracefully.*

## `app/tests/unit/test_systems_architect_specialist.py`

- **`test_systems_architect_creates_system_plan`**
  - *Tests that the specialist successfully creates a system plan.*
- **`test_systems_architect_handles_no_json_response`**
  - *Tests that the specialist raises an error if LLM returns no JSON response.*
- **`test_systems_architect_handles_malformed_json_response`**
  - *Tests that the specialist raises an error if LLM returns malformed JSON.*

## `app/tests/unit/test_text_analysis_specialist.py`

- **`test_text_analysis_with_text`**
  - *Tests the normal execution path where text is provided and successfully analyzed.*
- **`test_text_analysis_without_text_self_correction`**
  - *Tests the self-correction mechanism where no text is provided (is None).*
- **`test_text_analysis_with_empty_text_input`**
  - *Tests self-correction when text_to_process is an empty or whitespace string.*
- **`test_text_analysis_handles_llm_invocation_error`**
  - *Tests that an LLMInvocationError is propagated correctly.*
- **`test_text_analysis_handles_malformed_llm_response`**
  - *Tests that the specialist raises an error if the LLM response is not valid JSON.*

## `app/tests/unit/test_tiered_synthesizer_specialist.py`

- **`test_tiered_synthesizer_initialization`**
  - *Verifies that TieredSynthesizerSpecialist initializes correctly.*
- **`test_tiered_synthesizer_combines_both_responses`**
  - *Tests full tiered response when both Alpha and Bravo succeed (happy path).*
- **`test_tiered_synthesizer_handles_alpha_only`**
  - *Tests graceful degradation when only Alpha succeeds (CORE-CHAT-002.1).*
- **`test_tiered_synthesizer_handles_bravo_only`**
  - *Tests graceful degradation when only Bravo succeeds (CORE-CHAT-002.1).*
- **`test_tiered_synthesizer_raises_error_when_both_missing`**
  - *Tests that TieredSynthesizer raises error when both progenitors fail.*
- **`test_tiered_synthesizer_creates_proper_message`**
  - *Tests that TieredSynthesizer creates AIMessage with status information.*
- **`test_tiered_synthesizer_handles_empty_string_responses`**
  - *Tests edge case where responses are empty strings (not None).*
- **`test_tiered_synthesizer_preserves_markdown_formatting`**
  - *Tests that TieredSynthesizer preserves markdown formatting in responses.*
- **`test_tiered_synthesizer_response_format_structure`**
  - *Tests that the formatted response has proper structure.*
- **`test_tiered_synthesizer_does_not_add_to_user_response_snippets_if_already_present`**
  - *Tests that TieredSynthesizer replaces (not appends to) user_response_snippets.*

## `app/tests/unit/test_web_builder.py`

- **`test_web_builder_generates_html`**
  - *Tests that the WebBuilder correctly invokes the LLM with the current*
- **`test_web_builder_handles_llm_invocation_error`**
  - *Tests that an LLMInvocationError is propagated correctly.*
- **`test_web_builder_handles_malformed_llm_response`**
  - *Tests that the specialist raises an error if the LLM response is malformed.*

## `app/tests/unit/test_workflow_runner.py`

- **`test_workflow_runner_init`**
  - *Tests that the WorkflowRunner initializes correctly.*
- **`test_workflow_runner_run_sync`**
  - *Tests the synchronous run method.*
- **`test_workflow_runner_run_sync_handles_missing_artifact`**
  - *Tests that the sync run method handles a missing final artifact gracefully.*
- **`test_workflow_runner_run_sync_handles_invoke_error`**
  - *Tests that the sync run method raises a WorkflowError on graph invocation failure.*