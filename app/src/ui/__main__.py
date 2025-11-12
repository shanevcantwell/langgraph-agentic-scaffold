# app/src/ui/__main__.py
"""
Dynamic UI loader - loads UI module specified in user_settings.yaml

This makes the `ui` directory runnable as a package using `python -m app.src.ui`.
The actual UI module loaded is determined by the `ui_module` setting in user_settings.yaml.

Available UIs:
- gradio_app: Standard clean UI (default)
- gradio_lassie: Retro terminal UI with NIXIE readouts and CRT effects
"""
import importlib
import sys


def main():
    """Load and launch the UI module specified in user_settings.yaml"""
    # Load config
    try:
        from app.src.utils.config_loader import ConfigLoader
        config = ConfigLoader()
        user_settings = config.get_user_settings()
        ui_module_name = user_settings.get("ui_module", "gradio_app") if user_settings else "gradio_app"
    except Exception as e:
        print(f"⚠️  WARNING: Could not load user_settings.yaml: {e}")
        print(f"   Falling back to default UI: gradio_app")
        ui_module_name = "gradio_app"

    print(f"🎨 Loading UI module: {ui_module_name}")

    # Dynamic import
    try:
        ui_module = importlib.import_module(f"app.src.ui.{ui_module_name}")

        if not hasattr(ui_module, "main"):
            print(f"❌ ERROR: UI module '{ui_module_name}' is missing main() function")
            print(f"   Each UI module must implement a main() function that launches the UI")
            sys.exit(1)

        # Launch the UI
        ui_module.main()

    except ModuleNotFoundError:
        print(f"❌ ERROR: UI module '{ui_module_name}' not found")
        print(f"   Available UI modules:")
        print(f"      - gradio_app (standard UI)")
        print(f"      - gradio_lassie (retro terminal UI)")
        print(f"   Check your user_settings.yaml 'ui_module' setting")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERROR: Failed to launch UI module '{ui_module_name}': {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()