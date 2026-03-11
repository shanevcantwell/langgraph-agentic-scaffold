import os
import sys
import requests
import yaml
from dotenv import load_dotenv

from .environment import is_docker

# Load env vars
load_dotenv()

def check_url(url, name, timeout=5):
    try:
        print(f"Checking {name} ({url})...", end=" ")
        response = requests.get(url, timeout=timeout)
        # We accept 404 because it means we reached the server (connectivity is OK).
        # We reject 403 because it usually means the Proxy blocked it.
        if response.status_code < 400 or response.status_code == 404:
            print(f"OK (Status: {response.status_code})")
            return True
        else:
            print(f"FAILED (Status: {response.status_code})")
            return False
    except Exception as e:
        print(f"FAILED ({str(e)})")
        return False

def main():
    print("--- Environment Check ---")
    if is_docker():
        print("Running inside Docker")
    else:
        print("Running on HOST (not Docker)")
        print("  -> Integration tests will fail (LMStudio/3090 requires Docker proxy)")
        print("  -> Unit tests will work fine")
        print("  -> For full testing: docker compose exec app pytest")
    print()

    print("--- Connectivity Verification ---")

    # 1. Check Proxy / Internet
    # We check a reliable external site to verify the proxy is working and allowing traffic.
    if not check_url("https://www.google.com", "Internet (Google)"):
        print("CRITICAL: Cannot reach internet. Check proxy settings in proxy/squid.conf.")
        sys.exit(1)

    # 2. Check LangSmith (if enabled)
    if os.getenv("LANGCHAIN_TRACING_V2") == "true":
        endpoint = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
        # The root endpoint might return 404 or 403, but connection should succeed.
        # We'll accept 401/403 as "reachable but auth failed" which is different from connection error.
        try:
            print(f"Checking LangSmith ({endpoint})...", end=" ")
            response = requests.get(endpoint, timeout=5)
            print(f"OK (Status: {response.status_code})")
        except Exception as e:
             print(f"WARNING: LangSmith enabled but unreachable: {e}")
             # Don't exit, just warn

    # 3. Check LLM Providers
    try:
        with open("user_settings.yaml", "r") as f:
            settings = yaml.safe_load(f)
    except FileNotFoundError:
        print("WARNING: user_settings.yaml not found. Skipping LLM checks.")
        return

    # Calculate which providers are actually IN USE
    active_providers = set()
    
    # Add the default provider
    if default := settings.get("default_llm_config"):
        active_providers.add(default)
        
    # Add explicitly bound providers
    bindings = settings.get("specialist_model_bindings", {})
    for specialist, provider_key in bindings.items():
        active_providers.add(provider_key)

    print(f"Active Providers: {', '.join(active_providers)}")

    providers = settings.get("llm_providers", {})
    checked_urls = set()

    for name, config in providers.items():
        # Skip providers that aren't being used
        if name not in active_providers:
            continue

        ptype = config.get("type")
        if ptype in ("local", "local_pool"):
            base_url = os.getenv("LOCAL_INFERENCE_BASE_URL")
            if not base_url:
                print(f"ERROR: Provider '{name}' is '{ptype}' but LOCAL_INFERENCE_BASE_URL not set.")
                continue

            # Base url usually ends in /v1, we want to check /v1/models
            base_url = base_url.rstrip('/')
            check_url_target = f"{base_url}/models"

            if check_url_target not in checked_urls:
                if not check_url(check_url_target, f"Local Inference ({base_url})"):
                    print("CRITICAL: Cannot reach local inference server. Is it running? Is 'host.docker.internal' working?")
                    sys.exit(1)
                checked_urls.add(check_url_target)

        elif ptype == "gemini":
            # Just check google API reachability
            target = "https://generativelanguage.googleapis.com"
            if target not in checked_urls:
                if not check_url(target, "Gemini API"):
                     print("CRITICAL: Cannot reach Gemini API.")
                     sys.exit(1)
                checked_urls.add(target)

    print("--- Verification Complete ---")

if __name__ == "__main__":
    main()
