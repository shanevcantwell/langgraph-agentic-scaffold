# app/src/ui/__main__.py
"""
Dynamic UI loader - loads UI module specified in user_settings.yaml

This makes the `ui` directory runnable as a package using `python -m app.src.ui`.
The actual UI module loaded is determined by the `ui_module` setting in user_settings.yaml.

Available UIs:
- gradio_app: Standard clean UI (default)
- gradio_vegas: L.A.S. VEGAS retro terminal UI
- gradio_lassi: LASSI yogurt drink UI
"""
import importlib
import sys
import yaml
from pathlib import Path


def main():
    """Load and launch the UI module specified in user_settings.yaml"""
    # Load ui_module setting directly from user_settings.yaml
    ui_module_name = "gradio_app"  # Default

    try:
        user_settings_path = Path(__file__).parent.parent.parent.parent / "user_settings.yaml"
        if user_settings_path.exists():
            with open(user_settings_path, 'r') as f:
                user_settings = yaml.safe_load(f)
                if user_settings and "ui_module" in user_settings:
                    ui_module_name = user_settings["ui_module"]
        else:
            print(f"⚠️  user_settings.yaml not found, using default UI")
    except Exception as e:
        print(f"⚠️  WARNING: Could not load user_settings.yaml: {e}")
        print(f"   Falling back to default UI: gradio_app")

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
        print(f"      - gradio_app (standard clean UI)")
        print(f"      - gradio_vegas (L.A.S. VEGAS retro terminal)")
        print(f"      - gradio_lassi (LASSI yogurt drink UI)")
        print(f"   Check your user_settings.yaml 'ui_module' setting")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERROR: Failed to launch UI module '{ui_module_name}': {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()