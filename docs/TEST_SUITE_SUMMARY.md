# Test Suite Summary

## Overview

| Category | Files | Tests |
|----------|-------|-------|
| Unit | 57 | 384 |
| Integration | 21 | 133 |
| Other | 7 | 99 |
| **Total** | **85** | **616** |


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
- **`test_no_router_in_routing_history`**
  - *Verify router_specialist does not appear in routing_history.*
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
  - *Tests simple artifact passing: file_specialist → data_extractor_specialist*
- **`test_artifact_chain_three_specialists`**
  - *Tests artifact chain: systems_architect → web_builder → critic_specialist*
- **`test_conditional_artifacts_any_of`**
  - *Tests conditional artifact requirements (any-of pattern).*
- **`test_artifact_cleanup_not_leaked`**
  - *Tests that artifacts don't leak between workflow runs.*

## `app/tests/integration/test_batch_processor_live.py`

- **`test_batch_sort_parses_all_explicit_files`**
  - *Test that BatchProcessorSpecialist parses ALL explicitly listed files.*
- **`test_batch_sort_summary_matches_file_count`**
  - *Test that batch_sort_summary reports correct file counts.*

## `app/tests/integration/test_chat_specialist_routing.py`

- **`test_router_invokes_chat_specialist_for_conversational_query`**
  - *End-to-end test: User asks a question → Router → ChatSpecialist → Response*
- **`test_chat_specialist_appears_in_router_specialist_map`**
  - *Simpler test: Verify ChatSpecialist is registered and discoverable by router.*

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

## `app/tests/integration/test_external_mcp.py`


## `app/tests/integration/test_gradio_integration.py`


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

## `app/tests/integration/test_invariant_monitor.py`

- **`test_invariant_monitor_called_during_execution`**
  - *Verifies that the InvariantMonitor is invoked during the execution lifecycle.*

## `app/tests/integration/test_live_llm.py`

- **`test_live_gemini_adapter_interaction`**
  - *Tests a basic interaction with a live Gemini model via the AdapterFactory.*

## `app/tests/integration/test_live_lmstudio.py`

- **`test_live_lmstudio_adapter_interaction`**
  - *Tests a basic interaction with a live LM Studio model via the AdapterFactory.*

## `app/tests/integration/test_mcp_tools_integration.py`

- **`test_file_exists_returns_false_for_missing_file`**
  - *Verify file_exists returns False for non-existent file.*
- **`test_file_exists_returns_true_for_existing_file`**
  - *Verify file_exists returns True for existing file.*
- **`test_write_and_read_file`**
  - *Verify write_file and read_file work together.*
- **`test_append_to_file`**
  - *Verify append_to_file adds content to existing file.*
- **`test_list_files`**
  - *Verify list_files returns directory contents.*
- **`test_create_directory`**
  - *Verify create_directory creates new directory.*
- **`test_rename_file`**
  - *Verify rename_file moves/renames files.*
- **`test_delete_file`**
  - *Verify delete_file removes files.*
- **`test_create_zip`**
  - *Verify create_zip creates archive from directory.*
- **`test_create_manifest`**
  - *Verify create_manifest creates valid JSON manifest.*
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
- **`test_file_specialist_accessible_from_graph`**
  - *Verify file_specialist MCP functions work from graph context.*

## `app/tests/integration/test_parallel_execution.py`


## `app/tests/integration/test_routing_integration.py`

- **`test_specialist_dependency_routing`**
  - *Verifies specialist dependency requirements are treated as CRITICAL, not advisory.*
- **`test_triage_advisory_not_restrictive`**
  - *Verifies triage recommendations are advisory (not restrictive).*
- **`test_loop_detection_when_dependency_unsatisfied`**
  - *Verifies loop detection kicks in if specialist dependencies can't be satisfied.*
- **`test_file_upload_routing_success`**
  - *End-to-end test for the original bug scenario that motivated ADR-CORE-011.*
- **`test_router_respects_specialist_cannot_proceed`**
  - *Verifies router treats "cannot proceed" messages as blocking, not advisory.*
- **`test_context_aware_routing_prevents_loop`**
  - *End-to-end test verifying context-aware routing prevents infinite loop.*

## `app/tests/integration/test_specialist_execution.py`

- **`test_systems_architect_produces_system_plan`**
  - *Verify SystemsArchitect creates system_plan artifact.*
- **`test_systems_architect_raises_on_missing_json`**
  - *Verify SystemsArchitect raises error when json_response missing.*
- **`test_web_builder_produces_html_artifact`**
  - *Verify WebBuilder creates HTML artifact.*
- **`test_chat_specialist_produces_response`**
  - *Verify ChatSpecialist produces conversational response.*
- **`test_sentiment_classifier_classifies_positive`**
  - *Verify SentimentClassifier identifies positive sentiment.*
- **`test_sentiment_classifier_classifies_negative`**
  - *Verify SentimentClassifier identifies negative sentiment.*
- **`test_text_analysis_summarizes_content`**
  - *Verify TextAnalysisSpecialist summarizes text content.*
- **`test_batch_processor_initializes`**
  - *Verify BatchProcessorSpecialist initializes correctly.*
- **`test_researcher_initializes_with_mcp`**
  - *Verify ResearcherSpecialist initializes and registers MCP.*
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
  - *Verify triage_architect is the entry point for complex requests.*
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

## `app/tests/specialists/test_batch_processor_specialist.py`

- **`test_successful_batch_sort`**
  - *Test successful batch sorting of all files.*
- **`test_partial_failure`**
  - *Test handling of partial failures in batch operation.*
- **`test_missing_mcp_client`**
  - *Test error handling when MCP client is not available.*
- **`test_empty_messages`**
  - *Test error handling when no messages provided.*
- **`test_llm_parse_failure`**
  - *Test error handling when LLM cannot parse request.*
- **`test_batch_sort_with_content_reading`**
  - *Test batch sorting with content reading enabled.*
- **`test_mcp_error_during_execution`**
  - *Test graceful handling of MCP errors during file operations.*

## `app/tests/specialists/test_file_operations_specialist.py`

- **`test_init`**
  - *Test FileOperationsSpecialist initializes correctly.*
- **`test_list_files_operation`**
  - *Test listing files via MCP.*
- **`test_read_file_operation`**
  - *Test reading file contents via MCP.*
- **`test_write_file_operation`**
  - *Test writing file via MCP.*
- **`test_create_directory_operation`**
  - *Test creating directory via MCP.*
- **`test_delete_file_operation`**
  - *Test deleting file via MCP.*
- **`test_rename_file_operation`**
  - *Test renaming file via MCP.*
- **`test_no_mcp_client_error`**
  - *Test error handling when MCP client not available.*
- **`test_no_tool_calls_from_llm`**
  - *Test handling when LLM doesn't return tool calls.*
- **`test_mcp_call_failure`**
  - *Test error handling when MCP call fails.*
- **`test_empty_file_list_response`**
  - *Test handling of empty directory.*
- **`test_append_to_file_operation`**
  - *Test appending content to file via MCP.*

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
- **`test_execute_logic_handles_missing_final_response`**
  - *Tests edge case where final_user_response.md is missing.*
- **`test_archiver_summarize_conversation_with_objects`**
  - *Reproduces the 'AttributeError: 'HumanMessage' object has no attribute 'get''*
- **`test_archiver_execute_logic_integration`**
  - *Integration-like test for _execute_logic with real message objects in state.*

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

## `app/tests/unit/test_context_engineering_graph.py`

- **`test_context_engineering_graph_wiring`**
  - *Tests that the Context Engineering subgraph is correctly wired:*

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

## `app/tests/unit/test_facilitator.py`

- **`test_facilitator_executes_research_action`**
- **`test_facilitator_executes_read_file_action`**
- **`test_facilitator_handles_missing_plan`**
- **`test_facilitator_handles_mcp_error`**
- **`test_facilitator_reads_artifact_instead_of_file_for_uploaded_image`**
  - *Test that Facilitator retrieves in-memory artifacts instead of trying to read from filesystem.*
- **`test_facilitator_reads_artifact_for_uploaded_image_png_key`**
  - *Test artifact retrieval with 'uploaded_image.png' key.*
- **`test_facilitator_calls_file_specialist_when_artifact_not_in_state`**
  - *Test that Facilitator falls back to file_specialist when artifact is NOT in state.*

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

- **`test_file_exists_returns_true_for_existing_file`**
  - *Test that file_exists returns True for existing file.*
- **`test_file_exists_returns_true_for_existing_directory`**
  - *Test that file_exists returns True for existing directory.*
- **`test_file_exists_returns_false_for_nonexistent_path`**
  - *Test that file_exists returns False for nonexistent path.*
- **`test_file_exists_rejects_path_escape_attempt`**
  - *Test that file_exists rejects directory traversal attempts.*
- **`test_read_file_returns_content`**
  - *Test that read_file returns file contents.*
- **`test_read_file_handles_multiline_content`**
  - *Test that read_file preserves newlines.*
- **`test_read_file_raises_on_nonexistent_file`**
  - *Test that read_file raises SpecialistError for nonexistent file.*
- **`test_read_file_raises_on_directory`**
  - *Test that read_file raises SpecialistError when path is directory.*
- **`test_read_file_rejects_path_escape_attempt`**
  - *Test that read_file rejects directory traversal attempts.*
- **`test_write_file_creates_new_file`**
  - *Test that write_file creates new file with content.*
- **`test_write_file_overwrites_existing_file`**
  - *Test that write_file overwrites existing file.*
- **`test_write_file_creates_parent_directories`**
  - *Test that write_file creates missing parent directories.*
- **`test_write_file_handles_empty_content`**
  - *Test that write_file can write empty file.*
- **`test_write_file_rejects_path_escape_attempt`**
  - *Test that write_file rejects directory traversal attempts.*
- **`test_list_files_returns_directory_contents`**
  - *Test that list_files returns all files and directories.*
- **`test_list_files_returns_empty_for_empty_directory`**
  - *Test that list_files returns empty list for empty directory.*
- **`test_list_files_lists_subdirectory`**
  - *Test that list_files can list subdirectory contents.*
- **`test_list_files_raises_on_nonexistent_directory`**
  - *Test that list_files raises SpecialistError for nonexistent directory.*
- **`test_list_files_raises_on_file_path`**
  - *Test that list_files raises SpecialistError when path is file.*
- **`test_list_files_rejects_path_escape_attempt`**
  - *Test that list_files rejects directory traversal attempts.*
- **`test_create_directory_creates_new_directory`**
  - *Test that create_directory creates new directory.*
- **`test_create_directory_creates_nested_directories`**
  - *Test that create_directory creates missing parent directories.*
- **`test_create_directory_succeeds_if_already_exists`**
  - *Test that create_directory is idempotent (succeeds if dir exists).*
- **`test_create_directory_rejects_path_escape_attempt`**
  - *Test that create_directory rejects directory traversal attempts.*
- **`test_create_zip_creates_archive`**
  - *Test that create_zip creates zip archive from directory.*
- **`test_create_zip_preserves_directory_structure`**
  - *Test that create_zip preserves nested directory structure.*
- **`test_create_zip_handles_zip_extension_in_dest`**
  - *Test that create_zip handles .zip extension correctly.*
- **`test_create_zip_raises_on_nonexistent_source`**
  - *Test that create_zip raises SpecialistError for nonexistent source.*
- **`test_create_zip_raises_on_file_source`**
  - *Test that create_zip raises SpecialistError when source is file.*
- **`test_create_zip_rejects_source_path_escape`**
  - *Test that create_zip rejects directory traversal in source path.*
- **`test_create_zip_rejects_dest_path_escape`**
  - *Test that create_zip rejects directory traversal in dest path.*
- **`test_create_manifest_creates_valid_json`**
  - *Test that create_manifest creates a valid JSON file.*
- **`test_create_manifest_validates_schema`**
  - *Test that create_manifest raises error for invalid data.*
- **`test_create_manifest_rejects_path_escape`**
  - *Test that create_manifest rejects directory traversal.*
- **`test_validate_path_accepts_relative_paths`**
  - *Test that relative paths within root_dir are accepted.*
- **`test_validate_path_accepts_current_directory`**
  - *Test that '.' resolves to root_dir.*
- **`test_validate_path_rejects_parent_directory_traversal`**
  - *Test that .. traversal escaping root_dir is rejected.*
- **`test_validate_path_rejects_absolute_path_outside_root`**
  - *Test that absolute paths outside root_dir are rejected.*
- **`test_validate_path_accepts_absolute_path_inside_root`**
  - *Test that absolute paths within root_dir are accepted.*
- **`test_register_mcp_services_exposes_all_functions`**
  - *Test that register_mcp_services exposes all 6 functions.*
- **`test_execute_logic_returns_empty_dict`**
  - *Test that _execute_logic returns empty dict (no-op).*
- **`test_execute_logic_logs_warning`**
  - *Test that _execute_logic logs warning about MCP-only mode.*

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

## `app/tests/unit/test_install.py`

- **`test_install_script_creates_venv_and_installs_pytest`**
  - *Test that install.sh creates a virtual environment and installs pytest.*

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
- **`test_check_task_completion_explicit_complete`**
  - *Test that explicit task completion overrides barrier (edge case).*

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
- **`test_progenitor_alpha_stores_content_in_artifacts`**
  - *Tests that ProgenitorAlpha stores response content in artifacts (state management).*
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
- **`test_progenitor_bravo_stores_content_in_artifacts`**
  - *Tests that ProgenitorBravo stores response content in artifacts (state management).*
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

## `app/tests/unit/test_researcher.py`

- **`test_researcher_performs_search`**
- **`test_researcher_registers_mcp`**
- **`test_researcher_handles_no_messages`**

## `app/tests/unit/test_router_parallel.py`

- **`test_validate_llm_choice_single`**
  - *Test validation of a single specialist choice.*
- **`test_validate_llm_choice_list`**
  - *Test validation of a list of specialist choices.*
- **`test_validate_llm_choice_list_partial_invalid`**
  - *Test validation filters out invalid choices from a list.*
- **`test_validate_llm_choice_list_all_invalid`**
  - *Test fallback when all choices in list are invalid.*
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
- **`test_validate_llm_choice`**
  - *Tests the validation of the LLM's routing choice.*
- **`test_validate_llm_choice_list`**
  - *Tests validation when LLM returns a list of specialists (Scatter-Gather).*
- **`test_router_stage_3_termination_logic`**
  - *Tests Stage 3 of termination: when an archive report is present, the router*
- **`test_router_normal_llm_routing`**
  - *Tests the primary path where the router uses the LLM to decide the next specialist.*
- **`test_router_handles_llm_invocation_error`**
  - *Tests that the router propagates an LLMInvocationError if the adapter fails.*
- **`test_router_handles_invalid_llm_response`**
  - *Tests that the router self-corrects if the LLM returns an invalid specialist name.*
- **`test_get_available_specialists_context_aware_filtering_with_tags`**
  - *Tests that context_engineering specialists are filtered out after context gathering.*
- **`test_get_llm_choice_vision_logic_with_tags`**
  - *Tests that vision-capable specialists are identified via tags when an image is present.*
- **`test_get_llm_choice_dependency_logic_with_tags`**
  - *Tests that dependency logic correctly excludes planning specialists based on tags.*

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