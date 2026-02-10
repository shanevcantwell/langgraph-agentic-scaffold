# Test Suite Summary

## Overview

| Category | Files | Tests |
|----------|-------|-------|
| Unit | 72 | 685 |
| Integration | 28 | 193 |
| Other | 7 | 91 |
| **Total** | **107** | **969** |


## `app/tests/integration/test_api_streaming_integration.py`

- **`test_api_streams_multiple_specialist_updates`**
  - *Integration test: Verifies API emits status updates for router AND other specialists.*
- **`test_api_streams_error_updates`**
  - *Integration test: Verifies API streams error updates when specialists fail.*
- **`test_api_streams_tiered_chat_specialists`**
  - *Integration test: Verifies tiered chat subgraph specialists are all streamed.*
- **`test_api_streams_file_operations_specialist`**
  - *Integration test: Verifies file_operations_specialist streams correctly.*
- **`test_api_streams_artifacts_in_response`**
  - *Integration test: Verifies artifacts are included in streamed response.*
- **`test_api_streams_status_for_all_routed_specialists`**
  - *Integration test: Verifies status updates are emitted for every specialist*

## `app/tests/integration/test_archive_validation.py`

- **`test_archive_contains_manifest`**
  - *Verify archive contains a manifest.json file.*
- **`test_archive_contains_report`**
  - *Verify archive contains a report.md file.*
- **`test_manifest_is_valid_json`**
  - *Verify manifest.json is valid JSON.*
- **`test_archive_files_are_readable`**
  - *Verify all files in archive can be read without error.*
- **`test_manifest_has_required_fields`**
  - *Verify manifest contains all required fields.*
- **`test_manifest_run_id_is_uuid_format`**
  - *Verify run_id follows UUID format.*
- **`test_manifest_timestamp_is_iso_format`**
  - *Verify timestamp is valid ISO format.*
- **`test_manifest_routing_history_is_list`**
  - *Verify routing_history is a non-empty list.*
- **`test_manifest_artifacts_have_required_fields`**
  - *Verify each artifact entry has required fields.*
- **`test_manifest_artifacts_exist_in_archive`**
  - *Verify all artifacts listed in manifest exist in archive.*
- **`test_manifest_termination_reason_is_valid`**
  - *Verify termination_reason is a recognized value.*
- **`test_successful_workflow_ends_properly`**
  - *Verify successful workflows have final_response_generated=True.*
- **`test_tiered_chat_has_progenitors`**
  - *Verify tiered chat workflows include progenitor specialists.*
- **`test_router_in_routing_history`**
  - *Verify router_specialist appears in routing_history (Issue #41 fix).*
- **`test_triage_is_entry_point_when_present`**
  - *Verify triage_architect is first when it appears in routing.*
- **`test_log_file_exists`**
  - *Verify server log file exists.*
- **`test_no_unhandled_exceptions_in_recent_logs`**
  - *Check for unhandled exceptions in recent log entries.*
- **`test_successful_startup_in_logs`**
  - *Verify server started successfully.*
- **`test_specialists_initialized_in_logs`**
  - *Verify critical specialists were initialized.*
- **`test_recent_archives_all_have_valid_manifests`**
  - *Verify all recent archives have valid manifest files.*
- **`test_no_empty_archives`**
  - *Verify no archives are empty or corrupted.*
- **`test_archives_have_unique_run_ids`**
  - *Verify each archive has a unique run_id.*

## `app/tests/integration/test_artifact_passing.py`

- **`test_artifact_required_validation_missing_artifact`**
  - *Tests that specialists with required_artifacts fail gracefully when artifacts are missing.*
- **`test_artifact_passing_simple_producer_consumer`**
  - *Tests simple artifact passing: systems_architect → web_builder*
- **`test_artifact_chain_three_specialists`**
  - *Tests artifact chain: systems_architect → web_builder → critic_specialist*
- **`test_conditional_artifacts_any_of`**
  - *Tests conditional artifact requirements (all-of pattern within a list).*
- **`test_artifact_cleanup_not_leaked`**
  - *Tests that artifacts don't leak between workflow runs.*

## `app/tests/integration/test_batch_processor_live.py`

- **`test_batch_sort_parses_all_explicit_files`**
  - *Test that BatchProcessorSpecialist parses ALL explicitly listed files.*
- **`test_batch_sort_summary_matches_file_count`**
  - *Test that batch_sort_summary reports correct file counts.*

## `app/tests/integration/test_circuit_breaker.py`

- **`test_circuit_breaker_route_to_error_handler`**
  - *Test that the circuit breaker catches an invariant violation and triggers*
- **`test_circuit_breaker_halt_action`**
  - *Test that the circuit breaker halts execution when configured to HALT.*

## `app/tests/integration/test_config_validation.py`

- **`test_real_config_loads_successfully`**
  - *Validates that the actual config.yaml can be loaded by GraphBuilder.*
- **`test_critic_specialist_has_required_strategy_config`**
  - *Specific validation for CriticSpecialist configuration.*
- **`test_all_llm_specialists_have_valid_model_bindings`**
  - *Validates that all LLM specialists have valid model bindings.*

## `app/tests/integration/test_convening_integration.py`

- **`test_graph_builder_wires_convening_architecture`**
- **`test_default_architecture_fallback`**

## `app/tests/integration/test_file_sort.py`

- **`test_folder`**
  - *Create a unique test folder, clean up after test.*
- **`test_count_files_in_folder`**
  - *Prompt: "Count the files in folder X"*
- **`test_triage_recommends_chat_for_counting`**
  - *Triage should recommend chat_specialist for counting tasks (reasoning verb).*
- **`test_triage_recommends_project_director_for_listing`**
  - *Triage should recommend project_director for file listing tasks.*

## `app/tests/integration/test_filesystem_mcp.py`

- **`test_folder`**
  - *Create unique test folder, cleanup after.*

## `app/tests/integration/test_flows.py`

- **`test_flow_1_1_simple_question`**
  - *Flow 1.1: Simple Question (Tiered Chat)*
- **`test_flow_1_2_comparative_question`**
  - *Flow 1.2: Comparative Question*
- **`test_flow_1_3_greeting_fast_path`**
  - *Flow 1.3: Greeting (Fast Path)*
- **`test_flow_2_1_read_file`**
  - *Flow 2.1: Read File*
- **`test_flow_2_2_write_file`**
  - *Flow 2.2: Write File*
- **`test_flow_2_3_list_directory`**
  - *Flow 2.3: List Directory*
- **`test_flow_3_1_navigate_to_url`**
  - *Flow 3.1: Navigate to URL*
- **`test_flow_3_2_click_element`**
  - *Flow 3.2: Click Element*
- **`test_flow_3_3_fill_form`**
  - *Flow 3.3: Fill Form*
- **`test_flow_4_1_simple_research`**
  - *Flow 4.1: Simple Research*
- **`test_flow_4_2_comparative_research`**
  - *Flow 4.2: Comparative Research*
- **`test_flow_5_1_html_generation`**
  - *Flow 5.1: HTML Generation*
- **`test_flow_5_2_technical_plan`**
  - *Flow 5.2: Technical Plan*
- **`test_flow_6_1_text_summary`**
  - *Flow 6.1: Text Summary*
- **`test_flow_6_2_data_extraction`**
  - *Flow 6.2: Data Extraction*
- **`test_flow_7_0_simple_image_analysis`**
  - *Flow 7.0: Simple Image Analysis (Exit Interview Pattern)*
- **`test_flow_7_1_ui_mockup_to_html`**
  - *Flow 7.1: UI Mockup to HTML Generation*
- **`test_invariant_triage_entry`**
  - *Invariant 1: Every flow starts at TriageArchitect*
- **`test_invariant_end_exit`**
  - *Invariant 2: Every flow ends at EndSpecialist*
- **`test_invariant_no_silent_failure`**
  - *Invariant 5: Errors route to error handling, not silent failure*
- **`test_router_follows_triage`**
  - *Router should always follow triage (after optional facilitator)*
- **`test_end_is_terminal`**
  - *End specialist should be at or near the end of execution*

## `app/tests/integration/test_gradio_integration.py`


## `app/tests/integration/test_image_specialist_streaming.py`

- **`test_image_base64`**
  - *Loads the standard test image from assets.*
- **`test_image_specialist_appears_in_status_updates`**
  - *CORE TEST: Verify image_specialist appears in SSE status updates.*
- **`test_image_specialist_status_before_default_responder`**
  - *Verify image_specialist status appears BEFORE default_responder.*
- **`test_image_description_artifact_in_final_state`**
  - *Verify image_description artifact is in final state.*
- **`test_no_phantom_router_for_image_workflow`**
  - *Verify router_specialist does NOT appear in image workflow.*
- **`test_image_specialist_node_start_event`**
  - *Verify NODE_START event is emitted for image_specialist.*
- **`test_image_specialist_node_end_event`**
  - *Verify NODE_END event is emitted for image_specialist.*
- **`test_full_event_trace_for_image`**
  - *Captures and reports the full event trace for an image workflow.*
- **`test_compare_stream_and_events_endpoints`**
  - *Compare output from both streaming endpoints to identify discrepancies.*
- **`test_all_executed_specialists_appear_in_stream`**
  - *Verify ALL specialists that execute appear in the stream.*

## `app/tests/integration/test_image_workflow_quality.py`

- **`test_image_base64`**
  - *Loads the standard test image from assets.*
- **`test_image_description_artifact_is_produced`**
  - *BASELINE: Verify image_specialist produces the image_description artifact.*
- **`test_final_response_uses_image_description`**
  - *CRITICAL: Final response should USE the image_description, not ask for the image.*
- **`test_final_response_contains_description_content`**
  - *QUALITY: Final response should contain substantive content from the description.*
- **`test_routing_does_not_go_to_default_responder_after_image`**
  - *After image_specialist produces description, should NOT route to default_responder.*
- **`test_task_completes_after_image_analysis`**
  - *Image analysis workflow should complete (not loop indefinitely).*

## `app/tests/integration/test_inference_service_integration.py`

- **`test_infer_returns_structured_judgment`**
  - *Test that infer() returns judgment, reasoning, and confidence from live LLM.*
- **`test_infer_with_boolean_format`**
  - *Test that boolean format hint produces yes/no judgment.*
- **`test_infer_with_category_format`**
  - *Test that category format hint produces category-based judgment.*
- **`test_infer_handles_ambiguous_context`**
  - *Test that infer() handles ambiguous/unclear context gracefully.*
- **`test_infer_callable_via_mcp_client`**
  - *Test that infer() is callable through MCP client.*
- **`test_mcp_service_exposes_all_functions`**
  - *Test that all InferenceService methods are exposed via MCP.*
- **`test_judge_relevance_via_mcp`**
  - *Test judge_relevance through MCP client.*
- **`test_infer_with_call_time_adapter`**
  - *Test that infer() works when adapter is passed at call time.*
- **`test_judge_relevance_with_call_time_adapter`**
  - *Test judge_relevance with call-time adapter.*
- **`test_infer_with_very_long_context`**
  - *Test that long context is handled (truncated) correctly.*
- **`test_infer_with_technical_content`**
  - *Test inference on technical/code content.*

## `app/tests/integration/test_installer_scripts.py`

- **`test_generates_valid_env_file_gemini_only`**
  - *Verifies installer generates valid .env for Gemini-only setup.*
- **`test_generates_valid_env_file_lmstudio_only`**
  - *Verifies installer generates valid .env for LM Studio-only setup.*
- **`test_generates_valid_env_file_hybrid`**
  - *Verifies installer generates valid .env for hybrid setup.*
- **`test_converts_localhost_to_docker_host`**
  - *Verifies Docker mode converts localhost to host.docker.internal.*
- **`test_generates_valid_user_settings_gemini`**
  - *Verifies installer generates valid user_settings.yaml for Gemini.*
- **`test_generates_valid_user_settings_lmstudio`**
  - *Verifies installer generates valid user_settings.yaml for LM Studio.*
- **`test_generated_user_settings_binds_critical_specialists`**
  - *Verifies all critical specialists get bindings in generated config.*
- **`test_installer_does_not_overwrite_existing_configs`**
  - *Verifies installer logic checks for existing files before writing.*
- **`test_generated_config_is_parseable_by_config_loader`**
  - *Verifies generated user_settings.yaml can be loaded by ConfigLoader.*
- **`test_recommends_docker_when_available`**
  - *Verifies installer recommends Docker when both Docker and Python available.*
- **`test_falls_back_to_python_when_docker_unavailable`**
  - *Verifies installer falls back to Python when Docker not available.*
- **`test_errors_when_neither_available`**
  - *Verifies installer errors when neither Docker nor Python available.*
- **`test_provider_choice_sets_correct_defaults`**
  - *Verifies each provider choice sets correct default and router bindings.*
- **`test_detects_existing_surf_mcp`**
  - *Verifies installer detects existing surf-mcp sibling repo.*
- **`test_detects_missing_surf_mcp`**
  - *Verifies installer detects when surf-mcp is not present.*
- **`test_sibling_path_resolution`**
  - *Verifies surf-mcp path is correctly resolved as sibling.*
- **`test_surf_mcp_optional_not_blocking`**
  - *Verifies missing surf-mcp doesn't block installation.*

## `app/tests/integration/test_invariant_monitor.py`

- **`test_invariant_monitor_called_during_execution`**
  - *Verifies that the InvariantMonitor is invoked during the execution lifecycle.*

## `app/tests/integration/test_live_lmstudio.py`

- **`test_live_lmstudio_adapter_interaction`**
  - *Tests a basic interaction with a live LM Studio model via the AdapterFactory.*

## `app/tests/integration/test_llm_ping.py`

- **`test_config_loads_successfully`**
  - *Verify 3-tier config loads without error.*
- **`test_at_least_one_provider_available`**
  - *Verify at least one provider is available for testing.*
- **`test_ping_all_providers`**
  - *Ping all enabled providers and report results.*
- **`test_ping_gemini_providers`**
  - *Ping all Gemini-type providers.*
- **`test_ping_lmstudio_providers`**
  - *Ping all LMStudio-type providers.*

## `app/tests/integration/test_mcp_tools_integration.py`

- **`test_search_function_registered`**
  - *Verify search function is registered in MCP.*
- **`test_search_returns_results`**
  - *Verify search function returns list of results.*
- **`test_summarize_function_registered`**
  - *Verify summarize function is registered in MCP.*
- **`test_summarize_returns_text`**
  - *Verify summarize function returns summarized text.*
- **`test_describe_function_registered`**
  - *Verify describe function is registered in MCP.*
- **`test_describe_returns_description`**
  - *Verify describe function returns image description.*
- **`test_call_nonexistent_service_raises_error`**
  - *Verify calling non-existent service raises appropriate error.*
- **`test_call_nonexistent_function_raises_error`**
  - *Verify calling non-existent function raises appropriate error.*
- **`test_call_safe_returns_false_on_error`**
  - *Verify call_safe returns (False, error_msg) on failure.*
- **`test_list_services_returns_all_registered`**
  - *Verify list_services returns all registered services.*
- **`test_registry_isolation`**
  - *Verify each registry instance is isolated.*
- **`test_all_mcp_services_registered_in_graph`**
  - *Verify all expected MCP services are registered in full graph.*
- **`test_image_specialist_accessible_from_graph`**
  - *Verify image_specialist MCP functions work from graph context.*

## `app/tests/integration/test_navigator_browser_specialist_integration.py`

- **`test_graceful_message_when_unavailable`**
  - *Test that specialist provides helpful message when navigator unavailable.*
- **`test_detect_navigate_operation`**
  - *Test detecting navigate operation.*
- **`test_detect_click_operation`**
  - *Test detecting click operation.*
- **`test_detect_type_operation`**
  - *Test detecting type operation.*
- **`test_detect_read_operation`**
  - *Test detecting read operation.*
- **`test_detect_snapshot_operation`**
  - *Test detecting snapshot operation.*
- **`test_extract_url_from_request`**
  - *Test extracting URL from request.*
- **`test_extract_url_strips_punctuation`**
  - *Test that URL extraction strips trailing punctuation.*
- **`test_get_existing_session_from_artifacts`**
  - *Test extracting session ID from artifacts.*
- **`test_get_existing_session_returns_none_for_empty`**
  - *Test that None is returned for empty state.*
- **`test_cleanup_session_clears_artifact`**
  - *Test that cleanup clears the session artifact.*
- **`test_session_artifact_key_constant`**
  - *Test that session artifact key is consistent.*

## `app/tests/integration/test_navigator_mcp.py`


## `app/tests/integration/test_parallel_execution.py`


## `app/tests/integration/test_routing_integration.py`

- **`test_triage_advisory_not_restrictive`**
  - *Verifies triage recommendations are advisory (not restrictive).*
- **`test_router_respects_specialist_cannot_proceed`**
  - *Verifies router treats "cannot proceed" messages as blocking, not advisory.*
- **`test_router_removes_declining_specialist_from_routing_decision`**
  - *Integration test verifying the Router's actual _get_llm_choice method*
- **`test_specialist_decline_full_workflow`**
  - *Full end-to-end integration test for the "not me" pattern.*
- **`test_decline_signal_is_consumed_after_routing`**
  - *Verifies the Router consumes (clears) the decline signal after routing.*

## `app/tests/integration/test_specialist_execution.py`

- **`test_systems_architect_produces_system_plan`**
  - *Verify SystemsArchitect creates system_plan artifact.*
- **`test_systems_architect_raises_on_missing_json`**
  - *Verify SystemsArchitect raises error when json_response missing.*
- **`test_web_builder_produces_html_artifact`**
  - *Verify WebBuilder creates HTML artifact.*
- **`test_chat_specialist_produces_response`**
  - *Verify ChatSpecialist produces conversational response.*
- **`test_text_analysis_summarizes_content`**
  - *Verify TextAnalysisSpecialist summarizes text content.*
- **`test_batch_processor_initializes`**
  - *Verify BatchProcessorSpecialist initializes correctly.*
- **`test_summarizer_produces_summary`**
  - *Verify SummarizerSpecialist produces text summary.*
- **`test_prompt_specialist_generates_prompt`**
  - *Verify PromptSpecialist generates improved prompts.*
- **`test_default_responder_handles_greeting`**
  - *Verify DefaultResponder handles simple greetings.*
- **`test_progenitor_alpha_produces_artifact`**
  - *Verify ProgenitorAlpha writes to artifacts, not messages.*
- **`test_progenitor_bravo_produces_artifact`**
  - *Verify ProgenitorBravo writes to artifacts, not messages.*
- **`test_synthesizer_combines_progenitor_responses`**
  - *Verify TieredSynthesizer combines alpha and bravo responses.*
- **`test_triage_architect_creates_context_plan`**
  - *Verify TriageArchitect creates context_plan artifact.*
- **`test_router_produces_routing_decision`**
  - *Verify RouterSpecialist produces routing decision.*
- **`test_archiver_creates_archive_package`**
  - *Verify ArchiverSpecialist creates an Atomic Archival Package.*
- **`test_archiver_includes_manifest`**
  - *Verify archive includes valid manifest.json.*
- **`test_archiver_includes_report`**
  - *Verify archive includes report.md.*
- **`test_end_specialist_synthesizes_response`**
  - *Verify EndSpecialist synthesizes final response.*
- **`test_specialist_loads_successfully`**
  - *Verify specialist class loads without errors.*

## `app/tests/integration/test_specialist_routing_matrix.py`

- **`test_router_routes_to_expected_specialist`**
  - *Verify router routes to expected specialist(s) for given prompt.*
- **`test_triage_architect_is_entry_point`**
  - *Verify triage_architect is the entry point for requests.*
- **`test_tiered_chat_pattern_triggers_progenitors`**
  - *Verify chat_specialist triggers the tiered chat pattern with progenitors.*
- **`test_workflow_completes_at_end_specialist`**
  - *Verify all workflows terminate at end_specialist.*
- **`test_no_routing_to_internal_specialists`**
  - *Verify router does not directly route to internal specialists.*
- **`test_loop_detection_prevents_infinite_loops`**
  - *Verify loop detection prevents pathological routing patterns.*
- **`test_all_config_specialists_loadable`**
  - *Verify all specialists defined in config.yaml loaded successfully.*

## `app/tests/integration/test_startup_validation.py`

- **`test_startup_validation_critical_specialist_present`**
  - *Tests that critical specialists are detected correctly.*
- **`test_startup_validation_graph_builds_successfully`**
  - *Tests that GraphBuilder can successfully build a graph with real config.*
- **`test_startup_validation_invalid_entry_point_defaults_to_router`**
  - *Tests that invalid entry_point in config defaults to router_specialist.*
- **`test_startup_validation_disabled_specialist_not_loaded`**
  - *Tests that specialists with is_enabled=False are not loaded into the graph.*
- **`test_startup_validation_provider_dependency_check`**
  - *Tests that provider dependency validation detects missing dependencies.*
- **`test_startup_validation_allowed_destinations_set`**
  - *Tests that GraphBuilder populates allowed_destinations for route validation.*
- **`test_startup_validation_specialist_pre_flight_checks`**
  - *Tests that specialists with failed pre-flight checks are not added to graph.*
- **`test_startup_validation_router_specialist_map_populated`**
  - *Tests that RouterSpecialist.specialist_map is populated correctly.*
- **`test_startup_validation_graph_has_required_nodes`**
  - *Tests that the compiled graph has all required nodes.*

## `app/tests/integration/test_tiered_chat_end_to_end.py`

- **`test_tiered_chat_full_mode_end_to_end`**
  - *End-to-end test: User question → Router → Fanout → Both progenitors → Synthesizer*
- **`test_tiered_chat_graceful_degradation_alpha_only`**
  - *Tests graceful degradation when Bravo progenitor fails.*
- **`test_tiered_chat_graceful_degradation_bravo_only`**
  - *Tests graceful degradation when Alpha progenitor fails.*
- **`test_tiered_chat_virtual_coordinator_pattern`**
  - *Tests that the virtual coordinator pattern works correctly.*
- **`test_tiered_chat_state_management_pattern`**
  - *Tests that the state management pattern is followed correctly.*
- **`test_tiered_chat_simple_mode_bypass`**
  - *Tests that use_simple_chat flag bypasses tiered subgraph.*

## `app/tests/integration/test_triage_routing_flow.py`

- **`test_web_search_request_routes_to_researcher`**
  - *Regression test for routing issue: web search should route to researcher_specialist.*
- **`test_greeting_bypasses_context_gathering`**
  - *Test simple greeting flow: direct to chat_specialist without context gathering.*

## `app/tests/scripts/test_add_mcp_service.py`

- **`test_list_available_servers`**
  - *Test listing all available MCP servers from registry.*
- **`test_get_server_info_existing`**
  - *Test retrieving service info for existing service.*
- **`test_get_server_info_nonexistent`**
  - *Test retrieving service info for non-existent service.*
- **`test_validate_prerequisites_success`**
  - *Test prerequisite validation when all checks pass.*
- **`test_validate_prerequisites_docker_not_running`**
  - *Test prerequisite validation when Docker is not running.*
- **`test_validate_prerequisites_missing_template`**
  - *Test prerequisite validation when template doesn't exist.*
- **`test_build_docker_image_success`**
  - *Test successful Docker image build.*
- **`test_build_docker_image_failure`**
  - *Test Docker image build failure.*
- **`test_update_config_yaml_new_service`**
  - *Test adding new MCP service to config.yaml.*
- **`test_update_config_yaml_with_env_vars`**
  - *Test config.yaml update includes environment variables.*
- **`test_update_config_yaml_with_volumes`**
  - *Test config.yaml update includes volume mounts.*
- **`test_update_config_yaml_required_flag`**
  - *Test config.yaml update respects required flag.*
- **`test_update_config_yaml_atomic_write`**
  - *Test config.yaml update uses atomic temp file + rename pattern.*
- **`test_update_env_example_new_vars`**
  - *Test adding environment variables to .env.example.*
- **`test_update_env_example_no_vars`**
  - *Test .env.example update with no environment variables.*
- **`test_update_env_example_creates_section`**
  - *Test .env.example update creates MCP section if missing.*
- **`test_install_service_success`**
  - *Test full service installation workflow.*
- **`test_install_service_nonexistent`**
  - *Test installation fails for non-existent service.*
- **`test_install_service_prerequisite_failure`**
  - *Test installation fails when prerequisites not met.*
- **`test_install_service_with_auto_restart`**
  - *Test installation with auto-restart option.*
- **`test_restart_application`**
  - *Test Docker Compose application restart.*
- **`test_restart_application_failure`**
  - *Test application restart handles failures gracefully.*

## `app/tests/resilience/test_menu_filter_pattern.py`

- **`test_immediate_repetition_loop_activates_menu_filter`**
  - *REQUIREMENT: Immediate repetition (A→A→A) triggers menu filter.*
- **`test_two_step_cycle_loop_forbids_both_specialists`**
  - *REQUIREMENT: 2-step cycle (A→B→A→B) triggers menu filter and forbids BOTH specialists.*
- **`test_below_threshold_does_not_trigger_menu_filter`**
  - *REQUIREMENT: Below threshold repetitions should not trigger menu filter.*
- **`test_no_loop_returns_none`**
  - *REQUIREMENT: No loop detected should return None.*
- **`test_disabled_menu_filter_triggers_immediate_circuit_breaker`**
  - *REQUIREMENT: When menu filter disabled, loop detection raises CircuitBreakerTriggered immediately.*
- **`test_menu_filter_already_active_escalates_to_tier3`**
  - *REQUIREMENT: If loop detected while forbidden_specialists already populated, escalate to Tier 3.*
- **`test_extract_from_immediate_loop_error`**
  - *REQUIREMENT: Extract specialist name from immediate repetition error message.*
- **`test_extract_from_two_step_cycle_error`**
  - *REQUIREMENT: Extract BOTH specialist names from 2-step cycle error message.*
- **`test_invalid_error_format_returns_empty_list`**
  - *REQUIREMENT: If error message format is invalid, return empty list.*
- **`test_extraction_failure_triggers_circuit_breaker`**
  - *REQUIREMENT: If specialist extraction fails (empty list), fall through to circuit breaker.*
- **`test_no_forbidden_list_returns_full_menu`**
  - *REQUIREMENT: When no forbidden_specialists in scratchpad, return full specialist map.*
- **`test_forbidden_list_filters_specialists`**
  - *REQUIREMENT: When forbidden_specialists populated, remove them from returned menu.*
- **`test_multiple_forbidden_specialists_all_removed`**
  - *REQUIREMENT: When multiple specialists forbidden, remove ALL of them.*
- **`test_all_specialists_forbidden_returns_end_specialist_fallback`**
  - *REQUIREMENT: If ALL specialists forbidden, return only end_specialist as fallback.*
- **`test_forbidden_list_cleared_after_non_router_execution`**
  - *REQUIREMENT: Forbidden list cleared after ANY successful specialist execution (non-router).*
- **`test_router_execution_does_not_clear_forbidden_list`**
  - *REQUIREMENT: Router specialist execution does NOT clear forbidden list.*
- **`test_full_loop_recovery_flow`**
  - *REQUIREMENT: Full flow - Loop detected → Menu filter activates → Alternative selected → Clearance.*
- **`test_oscillation_recovery_web_builder_critic`**
  - *REQUIREMENT: 2-step oscillation between web_builder and critic_specialist.*
- **`test_exactly_threshold_repetitions`**
  - *REQUIREMENT: Exactly threshold repetitions (not exceeding) should NOT trigger.*
- **`test_threshold_plus_one_triggers`**
  - *REQUIREMENT: Threshold + 1 repetitions SHOULD trigger menu filter.*
- **`test_max_turn_count_exceeded_triggers_immediate_halt`**
  - *REQUIREMENT: Max turn count violation should trigger circuit breaker immediately (no menu filter).*
- **`test_structural_integrity_violation_triggers_immediate_halt`**
  - *REQUIREMENT: Structural integrity violations should trigger circuit breaker immediately.*
- **`test_forbidden_specialists_in_scratchpad_not_root`**
  - *REQUIREMENT: forbidden_specialists must be in scratchpad, NOT root state (ADR-CORE-004).*
- **`test_scratchpad_merge_semantics`**
  - *REQUIREMENT: Scratchpad uses operator.ior reducer (merge semantics).*
- **`test_menu_filter_activation_logged_at_warning_level`**
  - *REQUIREMENT: Menu filter activation should be logged at WARNING level.*
- **`test_tier3_escalation_logged_at_error_level`**
  - *REQUIREMENT: Tier 3 escalation should be logged at ERROR level.*

## `app/tests/resilience/test_strategy_pattern.py`

- **`test_context_action_supports_strategy`**
  - *Verify that ContextAction accepts a strategy field.*
- **`test_context_action_strategy_defaults_to_none`**
  - *Verify that strategy is optional.*

## `app/tests/specialists/test_batch_processor_specialist.py`

- **`test_successful_batch_operations`**
  - *Test successful batch file operations.*
- **`test_partial_failure`**
  - *Test handling of partial failures in batch operation.*
- **`test_missing_external_mcp_client`**
  - *Test error handling when external MCP client is not available.*
- **`test_empty_messages`**
  - *Test error handling when no messages provided.*
- **`test_llm_returns_no_operations`**
  - *Test error handling when LLM returns empty operation list.*
- **`test_move_operation`**
  - *Test move file operation.*
- **`test_mcp_error_during_execution`**
  - *Test graceful handling of errors during file operations.*
- **`test_dispatcher_exception_handled`**
  - *Test that dispatcher exceptions are caught and reported.*

## `app/tests/specialists/test_image_specialist.py`

- **`test_init`**
  - *Test ImageSpecialist initializes correctly.*
- **`test_mcp_service_registration`**
  - *Test that ImageSpecialist registers describe service via MCP.*
- **`test_describe_image_basic`**
  - *Test basic image description via MCP.*
- **`test_describe_image_custom_prompt`**
  - *Test image description with custom prompt.*
- **`test_describe_image_no_llm_adapter`**
  - *Test that describe raises error if LLM adapter not attached.*
- **`test_describe_image_empty_response`**
  - *Test handling of empty LLM response.*
- **`test_describe_image_llm_error`**
  - *Test error handling when LLM invocation fails.*
- **`test_execute_logic_with_uploaded_image`**
  - *Test graph execution mode with uploaded image in artifacts.*
- **`test_execute_logic_with_image_to_process`**
  - *Test graph execution mode with image_to_process artifact.*
- **`test_execute_logic_with_custom_prompt_artifact`**
  - *Test graph execution with custom analysis prompt in artifacts.*
- **`test_execute_logic_no_image`**
  - *Test graph execution returns error when no image in artifacts.*
- **`test_execute_logic_no_llm_adapter`**
  - *Test graph execution raises error if no LLM adapter.*
- **`test_execute_logic_describe_error`**
  - *Test graph execution handles describe errors gracefully.*
- **`test_execute_logic_success_sets_forbidden_specialists`**
  - *Test that successful execution also sets forbidden_specialists (not me pattern).*

## `app/tests/specialists/test_router_specialist.py`

- **`test_get_available_specialists_without_gathered_context`**
  - *Test that all specialists are available when no gathered_context exists.*
- **`test_get_available_specialists_with_gathered_context`**
  - *Test that planning specialists are excluded when gathered_context exists.*
- **`test_get_available_specialists_with_menu_filter`**
  - *Test Menu Filter Pattern (ADR-CORE-016) - forbidden_specialists in scratchpad.*
- **`test_get_available_specialists_combined_filters`**
  - *Test that gathered_context and menu filter work together.*
- **`test_get_available_specialists_empty_gathered_context`**
  - *Test that empty gathered_context dict does NOT trigger exclusion.*
- **`test_get_available_specialists_no_scratchpad`**
  - *Test that missing scratchpad key doesn't cause errors.*
- **`test_get_available_specialists_logging`**
  - *Test that context-aware exclusion logs informative message.*
- **`test_recommendation_filtering_with_gathered_context`**
  - *Test that recommendations are filtered when specialists are excluded from menu.*
- **`test_all_recommendations_filtered_out`**
  - *Test behavior when all recommendations are filtered out.*
- **`test_context_gathering_complete_note_in_prompt`**
  - *Test that explicit guidance is added when context gathering is complete.*
- **`test_triage_recommendations_included_in_router_prompt`**
  - *Test that triage recommendations are properly included in router prompt.*
- **`test_researcher_specialist_recommended_for_web_search`**
  - *Test the specific case from user's trace: web search should route to researcher.*

## `app/tests/interface/test_context_schema.py`

- **`test_context_plan_with_recommended_specialists`**
  - *Test ContextPlan with recommended_specialists field populated.*
- **`test_context_plan_default_empty_recommendations`**
  - *Test ContextPlan defaults to empty list for recommended_specialists.*
- **`test_context_plan_validates_required_fields`**
  - *Test ContextPlan requires reasoning field.*
- **`test_context_plan_single_recommendation`**
  - *Test ContextPlan with single specialist recommendation.*
- **`test_context_plan_serialization`**
  - *Test ContextPlan serializes to dict correctly (for state artifacts).*
- **`test_context_plan_empty_actions_with_recommendations`**
  - *Test ContextPlan with no actions but with recommendations.*
- **`test_context_plan_multiple_actions_with_recommendations`**
  - *Test ContextPlan with multiple actions and recommendations.*

## `app/tests/unit/test_adapter_contracts.py`

- **`test_adapter_robust_parsing_contract`**
  - *This contract test verifies that an adapter can robustly parse JSON*

## `app/tests/unit/test_ag_ui_translator.py`


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

- **`test_create_atomic_package_structure`**
  - *Tests that _create_atomic_package creates the correct file structure and zip.*
- **`test_execute_logic_creates_package_and_updates_state`**
  - *Tests the main logic flow: package creation and state update.*
- **`test_prune_archive_removes_oldest_files`**
  - *Tests that _prune_archive correctly removes the oldest files.*
- **`test_cleanup_orphaned_directories`**
  - *Tests that _cleanup_orphaned_directories removes orphaned dirs at startup.*
- **`test_execute_logic_handles_missing_final_response`**
  - *Tests edge case where final_user_response.md is missing.*
- **`test_archiver_summarize_conversation_with_objects`**
  - *Reproduces the 'AttributeError: 'HumanMessage' object has no attribute 'get''*
- **`test_archiver_execute_logic_integration`**
  - *Integration-like test for _execute_logic with real message objects in state.*
- **`test_archiver_includes_html_artifact_in_safe_artifacts`**
  - *Verifies that HTML artifacts are included in the returned safe_artifacts.*

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

## `app/tests/unit/test_base_specialist.py`

- **`test_task_is_complete_at_root_level_passes_validation`**
  - *When task_is_complete is correctly at root level, validation passes.*
- **`test_task_is_complete_in_scratchpad_raises_error`**
  - *FAIL-FAST: When task_is_complete is mistakenly in scratchpad,*
- **`test_no_task_is_complete_passes_validation`**
  - *When no task_is_complete signal exists, validation passes.*

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

## `app/tests/unit/test_circuit_breaker.py`

- **`test_stabilization_action_halt`**
  - *Verifies that the monitor raises CircuitBreakerTriggered when action is HALT.*
- **`test_stabilization_action_default_halt`**
  - *Verifies that the monitor defaults to HALT if action is not configured.*
- **`test_violation_type_detection_structure`**
  - *Verifies that structural violations are correctly identified.*
- **`test_violation_type_detection_loop`**
  - *Verifies that loop violations are correctly identified.*

## `app/tests/unit/test_clarification_workflow.py`

- **`test_check_triage_outcome_routes_to_facilitator_on_ask_user`**
  - *ADR-CORE-018: Tests that check_triage_outcome routes to Facilitator chain*
- **`test_check_triage_outcome_routes_to_facilitator_on_normal_actions`**
  - *Tests that check_triage_outcome routes to Facilitator for normal actions.*
- **`test_end_specialist_generates_clarification_response`**
  - *Tests that EndSpecialist generates a clarification response instead of*

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
- **`test_env_var_substitution_with_default`**
  - *Tests that env vars are substituted with default value when not set.*
- **`test_env_var_substitution_with_env_value`**
  - *Tests that env vars are substituted with actual env value when set.*
- **`test_env_var_substitution_required_missing`**
  - *Tests that missing required env var (no default) raises ConfigError.*
- **`test_lmstudio_servers_parsing`**
  - *Tests that LMSTUDIO_SERVERS env var is parsed correctly.*
- **`test_lmstudio_servers_missing_server_name`**
  - *Tests warning when server name not found in LMSTUDIO_SERVERS.*
- **`test_lmstudio_servers_empty`**
  - *Tests fallback to LMSTUDIO_BASE_URL when LMSTUDIO_SERVERS is empty.*
- **`test_lmstudio_servers_with_spaces`**
  - *Tests that LMSTUDIO_SERVERS handles whitespace gracefully.*

## `app/tests/unit/test_context_engineering_graph.py`

- **`test_context_engineering_graph_wiring`**
  - *Tests that the Context Engineering subgraph is correctly wired:*

## `app/tests/unit/test_convening_wiring.py`

- **`test_agent_router_defaults`**
- **`test_semantic_firewall_slop`**
- **`test_semantic_firewall_truncation`**
- **`test_tribe_conductor_init`**
- **`test_tribe_conductor_routing`**

## `app/tests/unit/test_critic_specialist.py`

- **`test_critic_specialist_accepts_and_completes_task`**
  - *Tests that the specialist accepts the work and signals task completion.*
- **`test_critic_specialist_revises_and_recommends_target`**
  - *Tests that the specialist recommends revision and a target specialist.*
- **`test_critic_specialist_handles_strategy_failure`**
  - *Tests that the specialist handles unrecoverable failure from its strategy.*

## `app/tests/unit/test_cycle_detection.py`

- **`test_single_item_repeated`**
  - *Period-1 cycle: A-A-A-A.*
- **`test_two_step_cycle`**
  - *Period-2 cycle: A-B-A-B-A-B.*
- **`test_four_step_cycle`**
  - *Period-4 cycle: A-B-C-D-A-B-C-D (batch of 4 files).*
- **`test_four_step_cycle_with_more_repetitions`**
  - *Period-4 cycle repeated 3 times.*
- **`test_no_cycle_short_history`**
  - *Not enough items to detect cycle.*
- **`test_no_cycle_different_items`**
  - *No repeating pattern.*
- **`test_cycle_at_end_only`**
  - *Cycle detection should focus on the end of history.*
- **`test_shortest_cycle_found_first`**
  - *When multiple cycles match, shortest period wins.*
- **`test_max_period_limit`**
  - *Respect max_period parameter.*
- **`test_tool_call_signatures`**
  - *Real-world tool call signature cycle (Issue #78 scenario).*
- **`test_empty_history`**
  - *Empty history returns None.*
- **`test_returns_pattern`**
  - *Should return both period and pattern.*
- **`test_four_item_pattern`**
  - *Four-item pattern from batch operation.*
- **`test_no_cycle_returns_none`**
  - *No cycle returns (None, None).*
- **`test_single_item_pattern`**
  - *Period-1 cycle has single-item pattern.*
- **`test_min_repetitions_1_not_useful`**
  - *min_repetitions=1 would match everything, so not typically used.*
- **`test_high_min_repetitions`**
  - *Need enough history for high min_repetitions.*

## `app/tests/unit/test_data_extractor_specialist.py`

- **`test_data_extractor_success`**
  - *Tests successful data extraction and state update.*
- **`test_data_extractor_fallback_to_message_content`**
  - *Tests that the specialist uses message content when artifact is missing.*
- **`test_data_extractor_no_text_anywhere`**
  - *Tests that the specialist handles truly empty input gracefully when both*
- **`test_data_extractor_llm_fails`**
  - *Tests that the specialist raises an error if the LLM returns no valid JSON payload.*
- **`test_data_extractor_handles_llm_invocation_error`**
  - *Tests that the specialist propagates LLM invocation errors.*
- **`test_data_extractor_no_text_to_process_on_empty_string`**
  - *Tests that the specialist returns an error message when input text is empty or whitespace.*

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

## `app/tests/unit/test_exit_interview_specialist.py`

- **`test_llm_evaluates_completion`**
  - *Exit Interview should always call LLM for semantic evaluation.*
- **`test_llm_returns_incomplete`**
  - *When LLM determines task is incomplete, result reflects that.*
- **`test_exit_interview_has_no_check_heuristics_method`**
  - *ADR-CORE-061: _check_heuristics() belongs in Interrupt Classifier.*
- **`test_exit_interview_has_no_evaluate_trace_heuristics_method`**
  - *ADR-CORE-061: _evaluate_trace_heuristics() belongs in Interrupt Classifier.*
- **`test_exit_interview_has_no_stutter_detection`**
  - *ADR-CORE-061: Stutter detection belongs in Interrupt Classifier.*
- **`test_exit_interview_only_evaluates_completion`**
  - *ADR-CORE-061: Exit Interview should ONLY have _evaluate_completion.*
- **`test_calls_sa_when_exit_plan_missing`**
  - *When exit_plan is not in artifacts, EI should call SA via MCP.*
- **`test_skips_sa_call_when_exit_plan_exists`**
  - *When exit_plan already exists, EI should NOT call SA.*
- **`test_handles_sa_mcp_call_failure_gracefully`**
  - *If SA MCP call fails, EI should proceed without exit_plan.*
- **`test_persists_exit_plan_on_incomplete`**
  - *When task is incomplete, exit_plan should still be persisted for next iteration.*
- **`test_ei_does_not_clear_max_iterations_on_complete`**
  - *When EI says COMPLETE, it should NOT include max_iterations_exceeded in artifacts.*
- **`test_ei_does_not_clear_max_iterations_on_incomplete`**
  - *When EI says INCOMPLETE, it should NOT include max_iterations_exceeded in artifacts.*

## `app/tests/unit/test_external_mcp_config.py`


## `app/tests/unit/test_facilitator.py`

- **`test_facilitator_executes_research_action`**
- **`test_facilitator_executes_read_file_action`**
- **`test_facilitator_handles_missing_plan`**
- **`test_facilitator_handles_mcp_error`**
- **`test_facilitator_reads_artifact_instead_of_file_for_uploaded_image`**
  - *Test that Facilitator retrieves in-memory artifacts instead of trying to read from filesystem.*
- **`test_facilitator_reads_artifact_for_uploaded_image_png_key`**
  - *Test artifact retrieval with 'uploaded_image.png' key.*
- **`test_facilitator_reads_file_via_external_mcp_when_artifact_not_in_state`**
  - *Test that Facilitator reads files via external filesystem MCP when not in artifacts.*
- **`test_facilitator_directory_listing_includes_full_paths`**
  - *Regression test for Bug #49: Directory listing must include full paths.*
- **`test_facilitator_directory_listing_handles_subdirs`**
  - *Test that [DIR] markers are properly formatted with full paths.*
- **`test_facilitator_executes_summarize_action`**
  - *Per FACILITATOR.md: SUMMARIZE action calls summarizer_specialist.summarize.*
- **`test_facilitator_summarize_with_file_path_reads_file_first`**
  - *Per FACILITATOR.md: If SUMMARIZE target looks like a file path (starts with / or ./),*
- **`test_facilitator_handles_ask_user_action_via_interrupt`**
  - *ADR-CORE-059: Facilitator handles ASK_USER inline via LangGraph interrupt().*
- **`test_facilitator_executes_multiple_actions`**
  - *Per FACILITATOR.md: Facilitator processes all actions in the plan sequentially,*
- **`test_facilitator_sets_completion_flag`**
  - *Per FACILITATOR.md: Facilitator sets scratchpad["facilitator_complete"] = True*
- **`test_facilitator_filesystem_unavailable_graceful_degradation`**
  - *Per FACILITATOR.md: If filesystem MCP is unavailable, Facilitator includes*
- **`test_facilitator_directory_listing_filesystem_unavailable`**
  - *Per FACILITATOR.md: LIST_DIRECTORY also gracefully handles filesystem unavailability.*
- **`test_facilitator_handles_invalid_context_plan`**
  - *Per FACILITATOR.md: Invalid ContextPlan data returns an error.*
- **`test_facilitator_continues_after_action_error`**
  - *Per FACILITATOR.md: Individual action failures don't halt the entire plan.*
- **`test_facilitator_accumulates_existing_context_on_retry`**
  - *Issue #96: Facilitator should ACCUMULATE context, not OVERWRITE.*
- **`test_facilitator_fresh_context_when_no_existing`**
  - *Issue #96: First pass (no existing gathered_context) should work normally.*
- **`test_facilitator_assembles_resume_trace_for_prior_work`**
  - *ADR-CORE-059: Facilitator assembles resume_trace from prior research traces.*
- **`test_facilitator_surfaces_exit_interview_feedback`**
  - *Issue #121: EI feedback (reasoning, missing_elements) is NOT surfaced in gathered_context.*
- **`test_facilitator_skips_exit_interview_feedback_when_complete`**
  - *Issue #100: Facilitator should NOT add feedback when task was marked complete.*
- **`test_facilitator_passes_trace_on_benign_interrupt`**
  - *Issue #114 supersedes Issue #108: BENIGN interrupt passes trace, not WIP summary.*
- **`test_facilitator_no_wip_summary_without_max_iterations`**
  - *Issue #108: No work-in-progress summary for normal flow (no BENIGN interrupt).*
- **`test_facilitator_benign_continuation_with_ei_incomplete`**
  - *Issue #114: BENIGN continuation when EI says INCOMPLETE but max_iterations caused it.*
- **`test_facilitator_no_wip_summary_without_trace`**
  - *Issue #108: No work-in-progress summary if no research trace exists.*
- **`test_facilitator_benign_passes_full_trace`**
  - *Issue #114: BENIGN continuation passes full trace, not a summary.*
- **`test_facilitator_benign_resume_passes_trace_without_context_accumulation`**
  - *Issue #114: BENIGN resume should pass trace through without context pollution.*
- **`test_facilitator_benign_resume_no_early_return_without_trace`**
  - *Issue #114: Without prior trace, BENIGN path should NOT early return.*
- **`test_facilitator_no_early_return_when_exit_interview_result_present`**
  - *Issue #114: When exit_interview_result is present, NO early return.*
- **`test_facilitator_benign_continuation_after_ei_incomplete`**
  - *Issue #114: BENIGN continuation when EI says INCOMPLETE but max_iterations was the cause.*

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

## `app/tests/unit/test_gemini_adapter.py`

- **`test_invoke_raises_proxy_error_on_connection_issues`**
  - *Tests that the Gemini adapter correctly catches various connection-related*
- **`test_structured_output_raises_on_invalid_json`**
  - *Issue #123: When output_model_class is set, adapter should raise error*
- **`test_text_response_extracts_json_when_present`**
  - *Issue #123: When NO output_model_class is set (text mode), adapter should*
- **`test_text_response_no_json_returns_text_only`**
  - *Issue #123: When NO output_model_class is set and response has no JSON,*

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
- **`test_wire_hub_and_spoke_edges_uses_safe_wrapper_for_router`**
  - *Test that the router edge uses the safe wrapper method.*
- **`test_wire_hub_and_spoke_edges_uses_safe_wrapper_for_critic`**
  - *Test that the critic edge uses the safe wrapper method.*
- **`test_wire_hub_and_spoke_edges_uses_safe_wrapper_for_task_completion`**
  - *Test that task completion edges use the safe wrapper method.*

## `app/tests/unit/test_graph_orchestrator.py`

- **`test_route_to_next_specialist_normal_route`**
  - *Tests that the function returns the correct specialist name from the state.*
- **`test_route_to_next_specialist_detects_loop`**
  - *Tests that the function routes to exit_interview when a repeating loop is detected.*
- **`test_route_to_next_specialist_loop_not_long_enough`**
  - *Tests that a repeating pattern shorter than min_loop_len is not flagged as a loop.*
- **`test_route_to_next_specialist_allows_non_loop`**
  - *Tests that the function does not halt for a non-looping history.*
- **`test_route_to_next_specialist_handles_no_route`**
  - *Tests that the function routes to exit_interview if the router fails to provide a next step.*
- **`test_route_validation_blocks_invalid_destination`**
  - *Tests that route_to_next_specialist raises WorkflowError when router*
- **`test_route_validation_allows_valid_destination`**
  - *Tests that route_to_next_specialist allows routing to valid destinations*
- **`test_route_validation_allows_chat_specialist_fanout`**
  - *Tests that route_to_next_specialist allows routing to chat_specialist*
- **`test_route_validation_blocks_invalid_fanout_destination`**
  - *Tests that fanout validation catches when hardcoded fanout destinations*
- **`test_route_validation_disabled_when_no_allowed_destinations`**
  - *Tests that route validation is gracefully disabled when allowed_destinations*
- **`test_loop_detector_sets_loop_detected_not_termination_reason`**
  - *Loop detector should set loop_detected (informational) instead of*
- **`test_after_exit_interview_complete_clears_loop_detected`**
  - *When Exit Interview says COMPLETE despite loop pattern, we should*
- **`test_after_exit_interview_incomplete_with_loop_sets_termination_reason`**
  - *When Exit Interview says INCOMPLETE after loop detection, NOW we*
- **`test_after_exit_interview_incomplete_without_loop_routes_to_facilitator`**
  - *Normal INCOMPLETE (no loop) should route to Facilitator for retry,*
- **`test_after_exit_interview_complete_without_loop_normal_end`**
  - *Normal COMPLETE (no loop) should route to END without any special handling.*

## `app/tests/unit/test_heap_invariants.py`

- **`test_branch_pointer_forbids_extra_fields`**
  - *BranchPointer must reject unknown fields.*
- **`test_project_manifest_forbids_extra_fields`**
  - *ProjectManifest must reject unknown fields.*
- **`test_contribution_entry_forbids_extra_fields`**
  - *ContributionEntry must reject unknown fields.*
- **`test_valid_namespaced_keys_accepted`**
  - *Properly namespaced keys should be accepted.*
- **`test_reserved_keys_accepted_without_namespace`**
  - *Reserved keys (priority, source, tags) don't need namespacing.*
- **`test_naked_key_rejected`**
  - *Keys without namespace (and not reserved) must be rejected.*
- **`test_empty_namespace_rejected`**
  - *Keys with empty namespace (.key) must be rejected.*
- **`test_mixed_valid_and_reserved_keys`**
  - *Mix of namespaced and reserved keys should work.*
- **`test_branch_status_values`**
  - *BranchStatus must have all ADR-specified values.*
- **`test_branch_phase_values`**
  - *BranchPhase must have all ADR-specified values.*
- **`test_agent_affinity_values`**
  - *AgentAffinity must have all ADR-specified values.*
- **`test_atomic_write_survives_replace_failure`**
  - *If os.replace() fails after temp file is written,*
- **`test_temp_file_cleaned_on_failure`**
  - *If os.replace() fails, the temp file should be cleaned up.*
- **`test_relative_traversal_rejected`**
  - *Classic ../ traversal must be rejected.*
- **`test_absolute_path_outside_root_rejected`**
  - *Absolute paths outside project root must be rejected.*
- **`test_encoded_traversal_rejected`**
  - *URL-encoded or tricky traversal attempts must be rejected.*
- **`test_hash_chain_integrity`**
  - *Verify that each entry correctly hashes the previous entry.*
- **`test_content_hash_computation`**
  - *Verify that content_hash is computed correctly from the content string.*
- **`test_detects_content_tampering`**
  - *If content_hash doesn't match content, flag it.*
- **`test_get_branches_by_status`**
  - *Should filter branches by status.*
- **`test_get_branches_by_affinity`**
  - *Should filter branches by affinity.*
- **`test_check_dependencies_satisfied`**
  - *Should correctly identify if dependencies are complete.*

## `app/tests/unit/test_hello_world_specialist.py`

- **`test_hello_world_specialist_greets_user`**
  - *Tests that the specialist generates a greeting based on the last message.*
- **`test_hello_world_specialist_handles_empty_messages`**
  - *Tests that the specialist provides a default response if state has no messages.*

## `app/tests/unit/test_image_injection.py`

- **`test_lmstudio_adapter_injects_image`**
- **`test_lmstudio_adapter_no_image`**

## `app/tests/unit/test_imports.py`

- **`test_import_all_modules`**
  - *A smoke test to ensure all critical modules and specialist modules*

## `app/tests/unit/test_inference_service.py`

- **`test_service_initializes_with_adapter`**
  - *Test that service stores adapter reference when provided.*
- **`test_service_initializes_without_adapter`**
  - *Test that service can be initialized without adapter (ADR-CORE-020).*
- **`test_get_mcp_functions_returns_all_methods`**
  - *Test that get_mcp_functions exposes all service methods.*
- **`test_infer_returns_json_response`**
  - *Test that infer() returns judgment, reasoning, and confidence.*
- **`test_infer_passes_context_to_llm`**
  - *Test that context is included in the LLM request.*
- **`test_infer_truncates_long_context`**
  - *Test that context over 4000 chars is truncated.*
- **`test_infer_uses_inference_response_schema`**
  - *Test that infer() uses InferenceResponse as output model.*
- **`test_infer_boolean_format_hint`**
  - *Test that boolean format adds yes/no instruction.*
- **`test_infer_category_format_hint`**
  - *Test that category format adds category instruction.*
- **`test_infer_json_format_hint`**
  - *Test that json format adds JSON instruction.*
- **`test_infer_no_format_hint_when_none`**
  - *Test that no format hint is added when output_format is None.*
- **`test_inference_response_validates_required_fields`**
  - *Test that InferenceResponse requires all fields.*
- **`test_inference_response_confidence_is_float`**
  - *Test that confidence is stored as float.*
- **`test_judge_relevance_calls_adapter`**
  - *Test that judge_relevance invokes LLM adapter.*
- **`test_detect_contradiction_calls_adapter`**
  - *Test that detect_contradiction invokes LLM adapter.*
- **`test_assess_source_quality_calls_adapter`**
  - *Test that assess_source_quality invokes LLM adapter.*
- **`test_infer_handles_empty_json_response`**
  - *Test that infer() handles missing json_response gracefully.*
- **`test_infer_handles_empty_context`**
  - *Test that infer() handles empty context.*
- **`test_infer_handles_unknown_format`**
  - *Test that unknown output_format is ignored (no hint added).*
- **`test_infer_uses_call_time_adapter`**
  - *Test that infer() uses adapter passed at call time.*
- **`test_infer_call_time_adapter_overrides_instance`**
  - *Test that call-time adapter takes precedence over instance adapter.*
- **`test_infer_raises_without_any_adapter`**
  - *Test that infer() raises ValueError when no adapter available.*
- **`test_judge_relevance_uses_call_time_adapter`**
  - *Test that judge_relevance() accepts call-time adapter.*
- **`test_judge_relevance_raises_without_adapter`**
  - *Test that judge_relevance() raises ValueError when no adapter.*
- **`test_detect_contradiction_uses_call_time_adapter`**
  - *Test that detect_contradiction() accepts call-time adapter.*
- **`test_detect_contradiction_raises_without_adapter`**
  - *Test that detect_contradiction() raises ValueError when no adapter.*
- **`test_assess_source_quality_uses_call_time_adapter`**
  - *Test that assess_source_quality() accepts call-time adapter.*
- **`test_assess_source_quality_raises_without_adapter`**
  - *Test that assess_source_quality() raises ValueError when no adapter.*

## `app/tests/unit/test_install.py`

- **`test_install_script_creates_venv_and_installs_pytest`**
  - *Test that install.sh creates a virtual environment and installs pytest.*

## `app/tests/unit/test_interrupt_classifier.py`

- **`test_max_iterations_exceeded_in_scratchpad_routes_to_exit_interview`**
  - *BENIGN: max_iterations_exceeded flag → Exit Interview for feedback.*
- **`test_max_iterations_exceeded_in_artifacts_routes_to_exit_interview`**
  - *BENIGN: max_iterations_exceeded in artifacts → Exit Interview.*
- **`test_context_overflow_routes_to_facilitator`**
  - *BENIGN: context_overflow → Facilitator (compress and continue).*
- **`test_user_abort_routes_to_end`**
  - *TERMINAL: user_abort → End (immediate termination).*
- **`test_stagnation_detected_flag_routes_to_interrupt_evaluator`**
  - *PATHOLOGICAL: stagnation_detected flag → Interrupt Evaluator.*
- **`test_tool_error_routes_to_interrupt_evaluator`**
  - *PATHOLOGICAL: tool_error flag → Interrupt Evaluator.*
- **`test_trace_stutter_detected_routes_to_interrupt_evaluator`**
  - *PATHOLOGICAL: trace stutter (via semantic-chunker drift) → Interrupt Evaluator.*
- **`test_unrecovered_failure_routes_to_interrupt_evaluator`**
  - *PATHOLOGICAL: unrecovered tool failure in trace → Interrupt Evaluator.*
- **`test_artifacts_present_routes_to_exit_interview`**
  - *NORMAL: artifacts present → Exit Interview for semantic completion.*
- **`test_no_artifacts_no_flags_routes_to_router`**
  - *NORMAL: no artifacts, no flags → Router (continue workflow).*
- **`test_terminal_takes_priority_over_benign`**
  - *TERMINAL should take priority over BENIGN flags.*
- **`test_benign_takes_priority_over_pathological`**
  - *BENIGN (max_iterations) should take priority over PATHOLOGICAL detection.*
- **`test_benign_takes_priority_over_artifacts`**
  - *BENIGN interrupt (max_iterations) should route to EI even if artifacts present.*

## `app/tests/unit/test_invariants.py`

- **`test_check_state_structure_valid`**
- **`test_check_state_structure_missing_key`**
- **`test_check_state_structure_invalid_type`**
- **`test_check_max_turn_count_valid`**
- **`test_check_max_turn_count_exceeded`**
- **`test_check_loop_detection_no_loop`**
- **`test_check_loop_detection_immediate_loop`**
- **`test_check_loop_detection_immediate_loop_below_threshold`**
- **`test_check_loop_detection_2step_cycle`**
- **`test_check_loop_detection_2step_cycle_below_threshold`**
- **`test_progressive_loop_detection_productive_iteration_allowed`**
  - *PRODUCTIVE ITERATION: Specialist repeats but produces different outputs (making progress).*
- **`test_progressive_loop_detection_stagnation_detected_kills_fast`**
  - *STAGNATION: Specialist repeats with SAME output (stuck loop).*
- **`test_progressive_loop_detection_max_iterations_exceeded`**
  - *MAX ITERATIONS: Specialist exceeds max_iterations cap despite making progress.*
- **`test_progressive_loop_detection_stagnation_check_disabled`**
  - *STAGNATION CHECK DISABLED: Specialist repeats with same output but detect_stagnation=False.*
- **`test_progressive_loop_detection_non_iterative_specialist_standard_check`**
  - *NON-ITERATIVE SPECIALIST: No iteration config, standard loop detection applies.*
- **`test_progressive_loop_detection_insufficient_hash_history`**
  - *INSUFFICIENT HISTORY: Not enough hashes for stagnation comparison (< 2 hashes).*
- **`test_progressive_loop_detection_no_config_fallback_to_standard`**
  - *NO CONFIG PROVIDED: Falls back to standard loop detection.*
- **`test_progressive_loop_detection_mixed_specialists_with_iteration`**
  - *MIXED ROUTING: Non-iterative specialist A interspersed with iterative specialist B.*

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
- **`test_validate_dependencies_detects_missing_playwright`**
  - *Tests that validation detects missing Playwright for gemini_webui provider.*
- **`test_validate_dependencies_passes_when_playwright_available`**
  - *Tests that validation passes when Playwright is available.*
- **`test_validate_dependencies_ignores_unbound_providers`**
  - *Tests that validation only checks providers that are actually bound to specialists.*
- **`test_ping_provider_unknown_type`**
  - *Tests that ping_provider handles unknown provider types gracefully.*
- **`test_ping_provider_success`**
  - *Tests successful ping returns correct result structure.*
- **`test_ping_provider_connection_error`**
  - *Tests that ping_provider handles connection errors gracefully.*
- **`test_ping_provider_invoke_error`**
  - *Tests that ping_provider handles invocation errors gracefully.*

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
- **`test_image_injection_skips_empty_data`**
  - *Tests that empty string image_data is treated as 'no image' (skips injection).*
- **`test_image_injection_rejects_whitespace_only_data`**
  - *Tests that whitespace-only image data raises ValueError.*
- **`test_image_injection_rejects_oversized_image`**
  - *Tests that oversized image data raises ValueError with helpful message.*
- **`test_image_injection_accepts_valid_sized_image`**
  - *Tests that valid-sized image data passes size check and proceeds to injection.*
- **`test_image_injection_rejects_empty_message_content`**
  - *Tests that empty message content raises ValueError when injecting image.*
- **`test_structured_output_raises_on_invalid_json`**
  - *Issue #123: When output_model_class is set, adapter should raise error*
- **`test_text_response_extracts_json_when_present`**
  - *Issue #123: When NO output_model_class is set (text mode), adapter should*
- **`test_text_response_no_json_returns_text_only`**
  - *Issue #123: When NO output_model_class is set and response has no JSON,*
- **`test_no_refs_unchanged`**
  - *Schema without $ref passes through unchanged.*
- **`test_direct_ref_resolved`**
  - *A bare $ref node is replaced with the definition.*
- **`test_ref_in_items_resolved`**
  - *$ref inside array items is resolved (the ParallelCall pattern).*
- **`test_nested_refs_resolved_recursively`**
  - *Refs within refs are resolved recursively.*
- **`test_list_elements_resolved`**
  - *$ref inside a list (e.g., anyOf) is resolved.*
- **`test_missing_def_left_as_is`**
  - *$ref pointing to a missing definition is left unchanged.*
- **`test_nested_model_schema_has_no_refs`**
  - *_build_tool_call_schema must produce $ref/$defs-free output for nested Pydantic models.*

## `app/tests/unit/test_mcp_client.py`

- **`test_client_initializes_with_registry`**
  - *Test that client requires and stores registry reference.*
- **`test_client_can_access_registry_methods`**
  - *Test that client can access registry services.*
- **`test_call_success_returns_data`**
  - *Test that successful call returns deserialized data.*
- **`test_call_with_no_parameters`**
  - *Test call with function that takes no parameters.*
- **`test_call_with_complex_return_value`**
  - *Test call that returns nested data structures.*
- **`test_call_raises_on_service_not_found`**
  - *Test that call raises ValueError for nonexistent service.*
- **`test_call_raises_on_function_not_found`**
  - *Test that call raises ValueError for nonexistent function.*
- **`test_call_raises_on_function_execution_error`**
  - *Test that call raises ValueError when function fails.*
- **`test_call_constructs_request_correctly`**
  - *Test that call builds McpRequest with correct parameters.*
- **`test_call_returns_none_when_function_returns_none`**
  - *Test that call correctly returns None values.*
- **`test_call_safe_success_returns_tuple`**
  - *Test that call_safe returns (True, result) on success.*
- **`test_call_safe_error_returns_tuple`**
  - *Test that call_safe returns (False, error_msg) on error.*
- **`test_call_safe_service_not_found`**
  - *Test call_safe error handling for nonexistent service.*
- **`test_call_safe_function_not_found`**
  - *Test call_safe error handling for nonexistent function.*
- **`test_call_safe_strips_error_prefix`**
  - *Test that call_safe strips 'MCP call failed:' prefix from errors.*
- **`test_call_safe_handles_unexpected_exceptions`**
  - *Test that call_safe catches unexpected exceptions.*
- **`test_call_safe_with_none_return_value`**
  - *Test that call_safe correctly handles None return values.*
- **`test_call_safe_no_exception_for_errors`**
  - *Test that call_safe never raises exceptions.*
- **`test_list_services_returns_all_registered`**
  - *Test that list_services returns all services from registry.*
- **`test_list_services_empty_registry`**
  - *Test list_services returns empty dict for new registry.*
- **`test_client_workflow_with_multiple_calls`**
  - *Test realistic workflow with multiple service calls.*
- **`test_client_error_recovery_with_call_safe`**
  - *Test error recovery pattern using call_safe.*
- **`test_client_chained_service_calls`**
  - *Test chaining multiple service calls together.*
- **`test_client_preserves_request_id_for_tracing`**
  - *Test that request_id flows through for distributed tracing.*

## `app/tests/unit/test_mcp_registry.py`

- **`test_registry_initializes_with_config`**
  - *Test that registry extracts MCP config section correctly.*
- **`test_registry_initializes_with_defaults`**
  - *Test that registry uses defaults when MCP config missing.*
- **`test_registry_starts_with_no_services`**
  - *Test that registry starts with empty service map.*
- **`test_register_service_success`**
  - *Test that service registration works correctly.*
- **`test_register_service_with_multiple_functions`**
  - *Test registering a service with multiple functions.*
- **`test_register_service_overwrites_existing`**
  - *Test that registering same service name overwrites previous.*
- **`test_register_service_raises_on_empty_functions`**
  - *Test that registering service with empty functions fails.*
- **`test_get_service_success`**
  - *Test that get_service returns registered functions.*
- **`test_get_service_not_found_raises_error`**
  - *Test that get_service raises McpServiceNotFoundError.*
- **`test_list_services_returns_all_registered`**
  - *Test that list_services returns all registered services.*
- **`test_dispatch_success`**
  - *Test successful function dispatch and response.*
- **`test_dispatch_with_no_parameters`**
  - *Test dispatch for function with no parameters.*
- **`test_dispatch_with_complex_return_value`**
  - *Test dispatch with complex nested data structures.*
- **`test_dispatch_service_not_found`**
  - *Test dispatch returns error response for nonexistent service.*
- **`test_dispatch_function_not_found`**
  - *Test dispatch returns error response for nonexistent function.*
- **`test_dispatch_function_execution_error`**
  - *Test dispatch returns error response when function raises exception.*
- **`test_dispatch_with_timeout_success`**
  - *Test that fast functions complete within timeout.*
- **`test_dispatch_timeout_error`**
  - *Test that slow functions trigger timeout error.*
- **`test_tracing_enabled_wraps_function`**
  - *Test that tracing wraps function when enabled.*
- **`test_tracing_disabled_does_not_wrap`**
  - *Test that tracing is skipped when disabled.*
- **`test_tracing_gracefully_handles_missing_langsmith`**
  - *Test that registry works when LangSmith is not installed.*
- **`test_multi_service_registration_and_dispatch`**
  - *Test multiple services working together.*
- **`test_error_handling_preserves_request_id`**
  - *Test that error responses preserve request_id for tracing.*
- **`test_registry_handles_none_return_value`**
  - *Test that functions returning None are handled correctly.*
- **`test_function`**
- **`test_function`**
- **`test_function`**

## `app/tests/unit/test_mcp_schemas.py`

- **`test_valid_request_with_all_fields`**
  - *Test that a fully specified request is valid.*
- **`test_valid_request_minimal_fields`**
  - *Test that request is valid with only required fields.*
- **`test_request_auto_generates_uuid`**
  - *Test that request_id is auto-generated when not provided.*
- **`test_request_with_nested_parameters`**
  - *Test that parameters can contain nested structures.*
- **`test_request_missing_service_name_fails`**
  - *Test that request without service_name raises ValidationError.*
- **`test_request_missing_function_name_fails`**
  - *Test that request without function_name raises ValidationError.*
- **`test_request_empty_strings_are_valid`**
  - *Test that empty strings are technically valid (registry will reject).*
- **`test_valid_success_response`**
  - *Test that a success response with data is valid.*
- **`test_valid_error_response`**
  - *Test that an error response with error_message is valid.*
- **`test_response_minimal_fields`**
  - *Test that response is valid with only status field.*
- **`test_response_data_can_be_any_type`**
  - *Test that data field accepts various data types.*
- **`test_response_invalid_status_fails`**
  - *Test that invalid status value raises ValidationError.*
- **`test_response_missing_status_fails`**
  - *Test that response without status raises ValidationError.*
- **`test_raise_for_error_with_success_status`**
  - *Test that raise_for_error does nothing for success responses.*
- **`test_raise_for_error_with_error_status`**
  - *Test that raise_for_error raises ValueError for error responses.*
- **`test_response_can_have_both_data_and_error`**
  - *Test that response can technically have both (though semantically odd).*
- **`test_request_response_id_correlation`**
  - *Test that request_id can be echoed in response for tracing.*
- **`test_empty_parameters_dict_is_valid`**
  - *Test that empty parameters dict works (for parameterless functions).*

## `app/tests/unit/test_navigator_browser_specialist.py`

- **`test_init_sets_name_and_config`**
  - *Test that init properly sets name and config.*
- **`test_preflight_passes_without_client_for_loading`**
  - *Test pre-flight passes when client not injected (allows loading).*
- **`test_preflight_fails_when_not_connected`**
  - *Test pre-flight check fails when navigator not connected.*
- **`test_preflight_succeeds_when_connected`**
  - *Test pre-flight check passes when navigator connected.*
- **`test_create_browser_session_extracts_session_id`**
  - *Test browser session creation extracts session_id.*
- **`test_create_browser_session_passes_headless_option`**
  - *Test browser session creation passes headless option.*
- **`test_create_browser_session_returns_none_on_failure`**
  - *Test browser session creation returns None on failure.*
- **`test_destroy_session_calls_navigator`**
  - *Test session destruction calls navigator.*
- **`test_detect_navigate_with_url`**
  - *Test detecting navigation request with URL.*
- **`test_detect_navigate_with_url_only`**
  - *Test detecting navigation when URL is present.*
- **`test_detect_click_request`**
  - *Test detecting click requests.*
- **`test_detect_type_request`**
  - *Test detecting type requests.*
- **`test_detect_read_request`**
  - *Test detecting read requests.*
- **`test_detect_snapshot_request`**
  - *Test detecting screenshot requests.*
- **`test_detect_unknown_request`**
  - *Test detecting unknown requests.*
- **`test_extract_https_url`**
  - *Test extracting HTTPS URL.*
- **`test_extract_http_url`**
  - *Test extracting HTTP URL.*
- **`test_extract_url_with_path`**
  - *Test extracting URL with path.*
- **`test_extract_url_strips_punctuation`**
  - *Test that trailing punctuation is stripped.*
- **`test_extract_url_returns_none_when_missing`**
  - *Test that None is returned when no URL present.*
- **`test_extract_quoted_element`**
  - *Test extracting quoted element description.*
- **`test_extract_element_from_click_pattern`**
  - *Test extracting element from click pattern.*
- **`test_extract_element_returns_none_for_unclear`**
  - *Test element extraction returns None for unclear requests.*
- **`test_extract_quoted_text`**
  - *Test extracting quoted text.*
- **`test_extract_double_quoted_text`**
  - *Test extracting double-quoted text.*
- **`test_extract_text_returns_none_for_unclear`**
  - *Test text extraction returns None for unclear requests.*
- **`test_navigate_to_calls_navigator`**
  - *Test navigate_to calls navigator goto.*
- **`test_click_element_calls_navigator`**
  - *Test click_element calls navigator click.*
- **`test_type_text_calls_navigator`**
  - *Test type_text calls navigator type.*
- **`test_read_content_calls_navigator`**
  - *Test read_content calls navigator read.*
- **`test_take_snapshot_calls_navigator`**
  - *Test take_snapshot calls navigator snapshot.*
- **`test_handle_browser_unavailable`**
  - *Test graceful message when browser unavailable.*
- **`test_handle_navigate_success`**
  - *Test successful navigation.*
- **`test_handle_navigate_no_url`**
  - *Test navigation without URL.*
- **`test_handle_click_success`**
  - *Test successful click.*
- **`test_handle_click_error`**
  - *Test click with error.*
- **`test_handle_type_success`**
  - *Test successful type.*
- **`test_handle_read_success`**
  - *Test successful read.*
- **`test_handle_snapshot_success`**
  - *Test successful snapshot.*
- **`test_execute_without_client`**
  - *Test execution without client returns unavailable message.*
- **`test_execute_creates_session_and_persists_by_default`**
  - *Test execution creates session and persists it by default (Phase 4).*
- **`test_register_mcp_services`**
  - *Test that MCP services are registered correctly.*
- **`test_mcp_is_available`**
  - *Test is_available MCP service.*
- **`test_mcp_is_available_when_not_connected`**
  - *Test is_available returns False when client injected but not connected.*
- **`test_mcp_is_available_when_client_not_injected`**
  - *Test is_available returns True when client not yet injected (allows loading).*
- **`test_parse_json_result`**
  - *Test parsing JSON result.*
- **`test_parse_non_json_result`**
  - *Test parsing non-JSON result falls back to string conversion.*
- **`test_parse_none_result`**
  - *Test parsing None result.*
- **`test_get_existing_session_from_artifacts`**
  - *Test extracting existing session from state artifacts.*
- **`test_get_existing_session_returns_none_when_missing`**
  - *Test that None is returned when no session artifact exists.*
- **`test_get_existing_session_returns_none_for_empty_state`**
  - *Test that None is returned for empty state.*
- **`test_validate_session_returns_true_for_valid_session`**
  - *Test session validation succeeds for valid session.*
- **`test_validate_session_returns_false_for_error`**
  - *Test session validation fails when navigator returns error.*
- **`test_validate_session_returns_false_on_exception`**
  - *Test session validation fails on exception.*
- **`test_get_or_create_session_reuses_valid_session`**
  - *Test that valid existing session is reused.*
- **`test_get_or_create_session_creates_new_when_invalid`**
  - *Test that new session is created when existing is invalid.*
- **`test_get_or_create_session_creates_new_when_not_persisting`**
  - *Test that new session is always created when persist=False.*
- **`test_merge_result_with_session_adds_artifact`**
  - *Test that session info is merged into result artifacts.*
- **`test_merge_result_with_session_skips_when_not_persisting`**
  - *Test that merge is skipped when persist=False.*
- **`test_cleanup_session_destroys_existing_session`**
  - *Test that cleanup destroys the existing session.*
- **`test_cleanup_session_handles_no_existing_session`**
  - *Test that cleanup handles missing session gracefully.*
- **`test_execute_logic_persists_session_by_default`**
  - *Test that execute_logic persists session by default.*
- **`test_execute_logic_destroys_session_when_not_persisting`**
  - *Test that execute_logic destroys session when persist_session=False.*

## `app/tests/unit/test_node_executor.py`

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
- **`test_safe_executor_clears_tracing_context_on_success`**
  - *Tests that the tracing context is properly cleared after successful execution.*
- **`test_safe_executor_emits_trace_for_procedural_specialist`**
  - *Tests that procedural specialists emit trace entries even without LLM calls.*
- **`test_safe_executor_does_not_emit_trace_for_unknown_type_without_adapter_traces`**
  - *Tests that specialists with unknown type and no adapter traces don't emit traces.*

## `app/tests/unit/test_parallel_reducer.py`

- **`test_initialization`**
  - *Test initializing the list with a list update.*
- **`test_removal`**
  - *Test removing an item with a string update.*
- **`test_removal_last_item`**
  - *Test removing the last item results in empty list.*
- **`test_removal_non_existent`**
  - *Test removing an item that doesn't exist (idempotency).*
- **`test_reinitialization`**
  - *Test overwriting existing list with new list.*

## `app/tests/unit/test_parallel_state_logic.py`

- **`test_reduce_parallel_tasks_initialization`**
  - *Test that passing a list REPLACES the current state (Scatter).*
- **`test_reduce_parallel_tasks_completion`**
  - *Test that passing a string REMOVES it from the list (Gather).*
- **`test_reduce_parallel_tasks_completion_last_item`**
  - *Test that removing the last item results in an empty list.*
- **`test_reduce_parallel_tasks_idempotent`**
  - *Test that removing a non-existent item does nothing.*
- **`test_check_task_completion_barrier_active`**
  - *Test that workflow terminates (END) if parallel tasks are still pending.*
- **`test_check_task_completion_barrier_cleared`**
  - *Test that workflow proceeds to ROUTER if parallel tasks are empty.*
- **`test_check_task_completion_explicit_complete_routes_to_exit_interview`**
  - *Test that task_is_complete routes to exit_interview for validation (ADR-ROADMAP-001).*
- **`test_check_task_completion_validated_by_exit_interview`**
  - *Test that task_is_complete goes to END after exit_interview validation.*

## `app/tests/unit/test_pooled_adapter.py`

- **`test_inherits_from_lmstudio_adapter`**
  - *PooledLMStudioAdapter inherits all formatting/schema methods from LMStudioAdapter.*
- **`test_from_config_raises`**
  - *from_config() is not the construction path — raises NotImplementedError.*
- **`test_client_is_none`**
  - *Parent's self.client is set to None — we create per-request clients.*
- **`test_model_name_preserved`**
  - *Model name from config is preserved for pool routing.*
- **`test_acquires_and_releases_server`**
  - *invoke() acquires a server slot and releases it in finally.*
- **`test_releases_server_on_error`**
  - *Server slot is released even when the HTTP call fails.*
- **`test_creates_client_with_acquired_url`**
  - *OpenAI client is created with the URL returned by the pool.*
- **`test_timeout_waiting_for_slot`**
  - *LLMInvocationError raised when pool can't provide a slot in time.*
- **`test_uses_request_model_id_when_provided`**
  - *model_id from request is passed to dispatcher.submit().*
- **`test_falls_back_to_model_name_when_no_model_id`**
  - *Falls back to adapter's model_name when request.model_id is None.*
- **`test_factory_creates_pool_for_lmstudio_pool_providers`**
  - *AdapterFactory initializes pool when lmstudio_pool providers exist.*
- **`test_factory_no_pool_for_lmstudio_only_providers`**
  - *AdapterFactory does NOT create pool when only 'lmstudio' providers exist.*
- **`test_factory_strips_v1_from_urls`**
  - *Pool server URLs have /v1 stripped (pool manages base URLs).*

## `app/tests/unit/test_progenitor_alpha_specialist.py`

- **`test_progenitor_alpha_initialization`**
  - *Verifies that ProgenitorAlphaSpecialist initializes correctly.*
- **`test_progenitor_alpha_generates_analytical_response`**
  - *Tests that ProgenitorAlpha generates an analytical perspective response.*
- **`test_progenitor_alpha_stores_response_in_artifacts`**
  - *Tests that ProgenitorAlpha stores response in artifacts.alpha_response.md.*
- **`test_progenitor_alpha_does_not_set_task_complete`**
  - *Tests that ProgenitorAlpha does NOT set task_is_complete (TieredSynthesizer does).*
- **`test_progenitor_alpha_maintains_conversation_context`**
  - *Tests that ProgenitorAlpha sends full conversation history to LLM.*
- **`test_progenitor_alpha_handles_llm_failure_gracefully`**
  - *Tests that ProgenitorAlpha provides fallback message when LLM fails.*
- **`test_progenitor_alpha_stores_content_in_artifacts`**
  - *Tests that ProgenitorAlpha stores response content in artifacts (state management).*
- **`test_progenitor_alpha_handles_empty_message_history`**
  - *Tests that ProgenitorAlpha handles edge case of empty message history.*
- **`test_progenitor_alpha_artifact_key_has_md_extension`**
  - *Verifies that ProgenitorAlpha saves with .md extension for proper archival.*

## `app/tests/unit/test_progenitor_bravo_specialist.py`

- **`test_progenitor_bravo_initialization`**
  - *Verifies that ProgenitorBravoSpecialist initializes correctly.*
- **`test_progenitor_bravo_generates_contextual_response`**
  - *Tests that ProgenitorBravo generates a contextual perspective response.*
- **`test_progenitor_bravo_stores_response_in_artifacts`**
  - *Tests that ProgenitorBravo stores response in artifacts.bravo_response.md.*
- **`test_progenitor_bravo_does_not_set_task_complete`**
  - *Tests that ProgenitorBravo does NOT set task_is_complete (TieredSynthesizer does).*
- **`test_progenitor_bravo_maintains_conversation_context`**
  - *Tests that ProgenitorBravo sends full conversation history to LLM.*
- **`test_progenitor_bravo_handles_llm_failure_gracefully`**
  - *Tests that ProgenitorBravo provides fallback message when LLM fails.*
- **`test_progenitor_bravo_stores_content_in_artifacts`**
  - *Tests that ProgenitorBravo stores response content in artifacts (state management).*
- **`test_progenitor_bravo_handles_empty_message_history`**
  - *Tests that ProgenitorBravo handles edge case of empty message history.*
- **`test_progenitor_bravo_artifact_key_has_md_extension`**
  - *Verifies that ProgenitorBravo saves with .md extension for proper archival.*

## `app/tests/unit/test_project_director.py`

- **`test_project_director_no_longer_inherits_react_mixin`**
  - *ADR-CORE-051: Verify ProjectDirector uses config-driven ReAct, not mixin.*
- **`test_project_director_defines_tools`**
  - *Test that ProjectDirector defines search and browse tools.*
- **`test_project_context_initialization`**
  - *Test that ProjectContext is initialized from user_request artifact.*
- **`test_project_context_restoration`**
  - *Test that existing ProjectContext is restored from artifacts.*
- **`test_research_prompt_building`**
  - *Test that research prompt includes context information.*
- **`test_max_iterations_from_config`**
  - *Test that max_iterations is read from config.*
- **`test_max_iterations_default`**
  - *Test default max_iterations when not in config.*
- **`test_max_iterations_from_react_config`**
  - *ADR-CORE-051: Test that _react_config (injected by ReactEnabledSpecialist)*
- **`test_tool_result_serialization`**
  - *Test that tool results are serialized correctly for artifacts.*
- **`test_partial_synthesis_on_max_iterations`**
  - *Test graceful degradation when max iterations exceeded.*
- **`test_subgraph_returns_empty_exclusions`**
  - *Test that Phase 2 subgraph doesn't exclude specialists from hub-and-spoke.*
- **`test_subgraph_build_no_custom_edges`**
  - *Test that Phase 2 subgraph doesn't add custom edges.*

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

## `app/tests/unit/test_react_mixin.py`

- **`test_full_name_property`**
  - *Test that full_name returns 'service.function' format.*
- **`test_optional_description`**
  - *Test that description is optional.*
- **`test_basic_creation`**
  - *Test basic ToolCall creation.*
- **`test_empty_args`**
  - *Test ToolCall with no arguments.*
- **`test_success_result`**
  - *Test successful tool result.*
- **`test_error_result`**
  - *Test error tool result.*
- **`test_successful_iteration`**
  - *Test creating a successful iteration record.*
- **`test_failed_iteration`**
  - *Test creating a failed iteration record.*
- **`test_immediate_final_response_no_tools`**
  - *Test that LLM returning text (no tools) completes immediately.*
- **`test_single_tool_call_then_final_response`**
  - *Test: LLM calls tool → sees result → returns final response.*
- **`test_multiple_tool_calls_in_sequence`**
  - *Test: LLM makes multiple sequential tool calls.*
- **`test_max_iterations_exceeded`**
  - *Test that MaxIterationsExceeded is raised when limit hit.*
- **`test_unknown_tool_returns_error_to_llm`**
  - *Test that unknown tool name is reported as error to LLM.*
- **`test_tool_execution_error_reported_to_llm`**
  - *Test that MCP errors are reported to LLM when stop_on_error=False.*
- **`test_tool_execution_error_raises_when_stop_on_error`**
  - *Test that MCP errors raise when stop_on_error=True.*
- **`test_missing_llm_adapter_raises`**
  - *Test that missing llm_adapter raises ValueError.*
- **`test_missing_mcp_client_returns_error`**
  - *Test that missing mcp_client returns error result.*
- **`test_ai_message_with_tool_calls_included_in_chain`**
  - *ADR-CORE-055: Verify AIMessage with tool_calls is included in message chain.*
- **`test_message_chain_order_preserved`**
  - *ADR-CORE-055: Verify message chain maintains correct order:*
- **`test_error_result_formatted_correctly`**
  - *Test that error results are formatted with 'Error:' prefix.*
- **`test_empty_trace_produces_human_message_only`**
  - *Empty trace should produce just the goal as HumanMessage.*
- **`test_single_iteration_produces_three_messages`**
  - *One iteration should produce: Human, AI, Tool.*
- **`test_multiple_iterations_preserve_order`**
  - *Multiple iterations maintain: Human, [AI, Tool]* pattern.*
- **`test_single_tool_call_dispatched_sequentially`**
  - *Single tool call should not use ThreadPoolExecutor.*
- **`test_multiple_tool_calls_dispatched_concurrently`**
  - *Multiple tool calls in one response should dispatch concurrently.*
- **`test_concurrent_dispatch_preserves_all_results`**
  - *All results from concurrent batch should appear in trace.*
- **`test_concurrent_dispatch_partial_failure`**
  - *Partial failures in concurrent batch are reported, not raised.*
- **`test_concurrent_batch_shares_thought`**
  - *All trace entries in a concurrent batch share the same thought.*
- **`test_concurrent_then_sequential_iterations`**
  - *Mix of concurrent and sequential calls across iterations.*

## `app/tests/unit/test_research_flow.py`

- **`test_router_llm_prompt_includes_gathered_context_content`**
  - *BUG-RESEARCH-001: Router should include gathered_context CONTENT in LLM prompt.*
- **`test_router_logs_gathered_context_for_debugging`**
  - *BUG-RESEARCH-004: Router should log what context it sees for debugging.*
- **`test_router_prompt_contains_failure_indicator_for_llm_decision`**
  - *BUG-RESEARCH-002: Verify Router provides failure information to LLM.*
- **`test_duckduckgo_no_results_returns_distinct_failure_marker`**
  - *Verify DuckDuckGoSearchStrategy returns a recognizable failure pattern.*
- **`test_duckduckgo_rate_limit_retries_with_backoff`**
  - *Verify DuckDuckGoSearchStrategy retries on rate limit with exponential backoff.*
- **`test_duckduckgo_rate_limit_succeeds_on_retry`**
  - *Verify DuckDuckGoSearchStrategy succeeds if retry works.*
- **`test_web_specialist_graph_node_requires_web_task`**
  - *BUG-RESEARCH-003: When Router routes to web_specialist, scratchpad.web_task*
- **`test_web_specialist_mcp_path_vs_graph_path`**
  - *Document the two invocation paths for WebSpecialist.*

## `app/tests/unit/test_router_observability.py`

- **`test_router_appears_in_routing_history`**
  - *Router should add itself to routing_history.*
- **`test_router_returns_llm_traces_field`**
  - *Router should return llm_traces field (empty in unit tests due to mock).*
- **`test_router_deterministic_end_path_has_routing_history`**
  - *Deterministic END path (archive exists) should still add Router to routing_history.*
- **`test_router_deterministic_dependency_path_has_routing_history`**
  - *Deterministic dependency routing should still add Router to routing_history.*
- **`test_router_observability_fields_with_parallel_routing`**
  - *Router observability works correctly with parallel specialist routing.*
- **`test_router_routing_history_is_additive_list`**
  - *Router returns routing_history as list for operator.add reducer.*
- **`test_tracing_context_is_set_and_cleared`**
  - *Verify set_current_specialist and clear_current_specialist are called.*
- **`test_turn_trace_built_when_adapter_traces_exist`**
  - *Verify build_specialist_turn_trace is called when adapter captures traces.*

## `app/tests/unit/test_router_parallel.py`

- **`test_validate_llm_choice_single`**
  - *Test validation of a single specialist choice returns (choice, True).*
- **`test_validate_llm_choice_list`**
  - *Test validation of a list of specialist choices returns (list, True).*
- **`test_validate_llm_choice_list_partial_invalid`**
  - *Test validation rejects entire list when any entry is invalid.*
- **`test_validate_llm_choice_list_all_invalid`**
  - *Test rejection when all choices in list are invalid.*
- **`test_route_to_next_specialist_list`**
  - *Test routing to a list of specialists.*
- **`test_route_to_next_specialist_list_invalid`**
  - *Test routing raises error if any specialist in list is invalid.*

## `app/tests/unit/test_router_specialist.py`

- **`test_get_available_specialists_no_recommendations`**
  - *Tests that all specialists are returned when no recommendations are present.*
- **`test_get_available_specialists_with_recommendations`**
  - *Tests that the specialist list is NOT filtered by recommendations (advisory mode).*
- **`test_handle_llm_failure_fallback_priority`**
  - *Tests the fallback logic when the LLM fails to make a decision.*
- **`test_validate_llm_choice_accept`**
  - *Valid string choice returns (choice, True).*
- **`test_validate_llm_choice_reject_string`**
  - *Invalid string choice returns (None, False) — no silent fallback.*
- **`test_validate_llm_choice_list_all_valid`**
  - *All-valid list passes through unchanged (no unwrapping).*
- **`test_validate_llm_choice_list_preserves_single_item`**
  - *Single-item list is preserved as a list — no unwrapping to string.*
- **`test_validate_llm_choice_list_rejects_entirely_on_any_invalid`**
  - *Mixed valid/invalid list is rejected entirely — no partial filtering.*
- **`test_validate_llm_choice_list_all_invalid`**
  - *All-invalid list returns (None, False).*
- **`test_router_stage_3_termination_logic`**
  - *Tests Stage 3 of termination: when an archive report is present, the router*
- **`test_router_normal_llm_routing`**
  - *Tests the primary path where the router uses the LLM to decide the next specialist.*
- **`test_router_handles_llm_invocation_error`**
  - *Tests that the router propagates an LLMInvocationError if the adapter fails.*
- **`test_router_handles_invalid_llm_response_with_retry`**
  - *Router retries once on invalid choice, then falls back to default_responder.*
- **`test_get_available_specialists_context_aware_filtering_with_tags`**
  - *Tests that context_engineering specialists are filtered out after context gathering.*
- **`test_get_llm_choice_vision_logic_with_tags`**
  - *Tests that vision-capable specialists are identified via tags when an image is present.*
- **`test_get_llm_choice_dependency_logic_with_tags`**
  - *Tests that dependency logic correctly excludes planning specialists based on tags.*
- **`test_build_route_response_model_produces_enum_schema`**
  - *Dynamic RouteResponse schema includes an enum array of valid specialist names.*
- **`test_build_route_response_model_rejects_invalid_on_parse`**
  - *Dynamic RouteResponse rejects names not in the enum during Pydantic validation.*
- **`test_build_route_response_model_single_name`**
  - *Works correctly with a single specialist (edge case).*
- **`test_retry_fires_on_invalid_then_succeeds`**
  - *Adapter is called twice: invalid first, valid on retry.*
- **`test_retry_disabled_when_max_retries_zero`**
  - *With max_routing_retries=0, invalid choice immediately falls through.*
- **`test_max_routing_retries_read_from_config`**
  - *max_routing_retries is read from specialist_config, defaulting to 1.*

## `app/tests/unit/test_router_specialist_discovery.py`

- **`test_router_discovers_specialists_from_config`**
  - *Verifies that RouterSpecialist can discover and route to any specialist*
- **`test_router_handles_empty_specialist_map_gracefully`**
  - *Verifies that RouterSpecialist handles edge case of no available specialists*
- **`test_router_ignores_specialists_without_descriptions`**
  - *Verifies that specialists without descriptions are still included in the*
- **`test_router_removes_declining_specialist_from_recommendations`**
  - *When a specialist declines with decline_task=True, it should be*
- **`test_router_clears_recommendations_when_all_decline`**
  - *When all recommended specialists have declined, recommendations*
- **`test_decline_does_not_affect_recommendations_if_not_in_list`**
  - *If a declining specialist isn't in the recommendations list,*
- **`test_decline_without_recommendations_has_no_effect`**
  - *Decline with no recommendations should not cause errors.*
- **`test_router_scratchpad_clears_all_decline_signals`**
  - *REGRESSION GUARD: Router MUST clear all decline-related signals in its return.*

## `app/tests/unit/test_search_strategies.py`

- **`test_requires_api_key`**
  - *Strategy returns error when no API key configured.*
- **`test_api_key_from_extra_params`**
  - *API key can be passed via extra_params.*
- **`test_successful_search`**
  - *Successful search returns formatted results.*
- **`test_rate_limited_response`**
  - *Returns Rate Limited marker on 429 status.*
- **`test_auth_error_response`**
  - *Returns Auth Error on 401 status.*
- **`test_quota_exceeded_response`**
  - *Returns Quota Exceeded on 422 status.*
- **`test_empty_results`**
  - *Returns No Results marker when search finds nothing.*
- **`test_timeout_handling`**
  - *Returns Timeout Error on request timeout.*
- **`test_requires_at_least_one_strategy`**
  - *Raises error if no strategies provided.*
- **`test_first_strategy_success`**
  - *Returns results from first strategy if successful.*
- **`test_fallback_on_rate_limit`**
  - *Falls back to second strategy on rate limit.*
- **`test_fallback_on_exception`**
  - *Falls back to second strategy on exception.*
- **`test_all_strategies_fail`**
  - *Returns last error when all strategies fail.*
- **`test_no_results_is_not_retryable`**
  - *'No Results' is not considered a retryable error.*
- **`test_multiple_results_not_retryable`**
  - *Multiple results are never considered retryable errors.*
- **`test_add_strategy_append`**
  - *add_strategy appends by default.*
- **`test_add_strategy_with_priority`**
  - *add_strategy can insert at specific index.*
- **`test_duckduckgo_to_brave_fallback`**
  - *DuckDuckGo rate limit triggers Brave fallback.*

## `app/tests/unit/test_smoke.py`

- **`test_config_loads`**
  - *Config loads without error using real ConfigLoader.*
- **`test_graph_builder_initializes`**
  - *GraphBuilder initializes with real config.*
- **`test_workflow_runner_initializes`**
  - *WorkflowRunner initializes (depends on GraphBuilder).*
- **`test_api_imports`**
  - *FastAPI app can be imported (triggers lifespan setup).*

## `app/tests/unit/test_specialist_helpers.py`

- **`test_decline_response_basic`**
  - *Test basic decline response structure.*
- **`test_decline_response_with_recommendations`**
  - *Test decline response with alternative specialist recommendations.*
- **`test_decline_response_message_format`**
  - *Test that decline message follows expected format for UI display.*
- **`test_error_message_basic`**
  - *Test basic error message structure.*
- **`test_error_message_with_recommendations`**
  - *Test error message with specialist recommendations.*
- **`test_llm_message_with_adapter`**
  - *Test message creation with adapter.*
- **`test_llm_message_without_adapter`**
  - *Test message creation without adapter defaults to unknown_model.*

## `app/tests/unit/test_specialist_loader.py`

- **`test_get_specialist_class_success`**
  - *Tests that the loader can successfully import and return a class*
- **`test_get_specialist_class_import_error`**
  - *Tests that the loader propagates an ImportError if the specialist*
- **`test_get_specialist_class_attribute_error`**
  - *Tests that an AttributeError is raised if the module is found*
- **`test_get_specialist_class_syntax_error`**
  - *Tests that the loader propagates a SyntaxError if the specialist*

## `app/tests/unit/test_state_pruner.py`

- **`test_generate_success_report_renders_images`**
- **`test_generate_success_report_detects_base64_string`**

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

## `app/tests/unit/test_summarizer.py`

- **`test_summarizer_summarizes_text`**
- **`test_summarizer_registers_mcp`**
- **`test_summarizer_handles_missing_artifact`**

## `app/tests/unit/test_systems_architect_specialist.py`

- **`test_systems_architect_creates_system_plan`**
  - *Tests that the specialist successfully creates a system plan.*
- **`test_systems_architect_handles_no_json_response`**
  - *Tests that the specialist raises an error if LLM returns no JSON response.*
- **`test_systems_architect_handles_malformed_json_response`**
  - *Tests that the specialist raises an error if LLM returns malformed JSON.*
- **`test_create_plan_returns_artifact_with_specified_key`**
  - *create_plan() should return artifacts with the caller-specified key.*
- **`test_create_plan_uses_context_as_human_message`**
  - *create_plan() should pass context as a HumanMessage to the LLM.*
- **`test_create_plan_raises_on_no_json_response`**
  - *create_plan() should raise ValueError if LLM returns no JSON response.*
- **`test_register_mcp_services_exposes_create_plan`**
  - *register_mcp_services() should register create_plan with the MCP registry.*

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
- **`test_text_analysis_sets_task_is_complete`**
  - *Test that successful analysis sets task_is_complete at root level.*
- **`test_text_analysis_no_task_complete_on_missing_text`**
  - *Test that task_is_complete is NOT set when text is missing (self-correction path).*
- **`test_text_analysis_treats_content_as_context`**
  - *Test that the specialist treats uploaded content as context, not target.*
- **`test_text_analysis_preserves_user_message`**
  - *Test that the user's original message is preserved in the context.*

## `app/tests/unit/test_thought_stream_events.py`


## `app/tests/unit/test_tiered_chat_state_management.py`

- **`test_progenitor_alpha_does_not_modify_messages`**
  - *Verifies ProgenitorAlpha does NOT append to messages (critical for parallel pattern).*
- **`test_progenitor_bravo_does_not_modify_messages`**
  - *Verifies ProgenitorBravo does NOT append to messages (critical for parallel pattern).*
- **`test_progenitors_write_only_to_artifacts`**
  - *Verifies both progenitors write responses to artifacts, not messages.*
- **`test_synthesizer_does_append_to_messages`**
  - *Verifies TieredSynthesizer DOES append to messages (join node pattern).*
- **`test_synthesizer_sets_task_complete`**
  - *Verifies TieredSynthesizer signals workflow completion.*
- **`test_multi_turn_history_accumulation`**
  - *Verifies that multi-turn conversations accumulate clean message history.*
- **`test_progenitors_receive_full_history_but_dont_pollute`**
  - *Verifies progenitors READ full message history but DON'T WRITE to it.*

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
- **`test_tiered_synthesizer_full_synthesis`**
  - *Tests synthesis when both Alpha and Bravo responses are present.*
- **`test_tiered_synthesizer_graceful_degradation_alpha_only`**
  - *Tests synthesis when Bravo is missing.*
- **`test_tiered_synthesizer_graceful_degradation_bravo_only`**
  - *Tests synthesis when Alpha is missing.*
- **`test_tiered_synthesizer_failure_both_missing`**
  - *Tests failure when both are missing.*

## `app/tests/unit/test_triage_architect.py`

- **`test_triage_architect_generates_plan`**
- **`test_triage_architect_handles_no_messages`**
- **`test_triage_architect_handles_llm_error`**
- **`test_triage_populates_recommended_specialists`**
  - *Test that TriageArchitect populates recommended_specialists in scratchpad.*
- **`test_triage_empty_recommendations_for_greeting`**
  - *Test TriageArchitect with empty actions still provides recommendations.*
- **`test_triage_multiple_recommendations`**
  - *Test TriageArchitect can recommend multiple specialists.*
- **`test_triage_default_empty_recommendations_if_not_provided`**
  - *Test TriageArchitect handles LLM not providing recommended_specialists.*
- **`test_triage_appends_system_note_for_text_to_process`**
  - *Test that TriageArchitect appends a system note when text_to_process is in artifacts.*
- **`test_triage_no_system_note_without_text_to_process`**
  - *Test that no system note is appended when text_to_process is NOT in artifacts.*
- **`test_triage_appends_system_note_for_uploaded_image`**
  - *Test that TriageArchitect appends a system note when uploaded_image.png is in artifacts.*
- **`test_triage_both_text_and_image_get_system_notes`**
  - *Test that both text and image system notes are appended when both are present.*

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