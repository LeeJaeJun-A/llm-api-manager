"""
Read the source config.yaml template and filter out models whose
provider API keys are not set in environment variables.
Only model_list entries are filtered; general_settings and litellm_settings
are passed through unchanged.
"""

import os
import re
import sys

import yaml

ENV_REF = re.compile(r"^os\.environ/(.+)$")

TEMPLATE_PATH = "/app/config.template.yaml"
OUTPUT_PATH = "/app/config.yaml"


def _extract_env_keys(params: dict) -> list[str]:
    """Extract all os.environ/XXX references from litellm_params."""
    keys = []
    for value in params.values():
        if isinstance(value, str):
            m = ENV_REF.match(value)
            if m:
                keys.append(m.group(1))
    return keys


def _is_available(params: dict) -> bool:
    """
    A model is available if ALL its env-referenced keys are set to
    a non-empty value. This handles api_key, aws_access_key_id, etc.
    """
    env_keys = _extract_env_keys(params)
    if not env_keys:
        return True
    return all(os.environ.get(k, "").strip() for k in env_keys)


def generate():
    if not os.path.exists(TEMPLATE_PATH):
        print(f"[config] ERROR: Template not found at {TEMPLATE_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(TEMPLATE_PATH) as f:
        config = yaml.safe_load(f)

    original_models = config.get("model_list", [])
    kept = []
    skipped = []

    for entry in original_models:
        name = entry.get("model_name", "unknown")
        params = entry.get("litellm_params", {})
        if _is_available(params):
            kept.append(entry)
            print(f"[config] ✓ {name}")
        else:
            env_keys = _extract_env_keys(params)
            missing = [k for k in env_keys if not os.environ.get(k, "").strip()]
            skipped.append(name)
            print(f"[config] ✗ {name} — missing: {', '.join(missing)}")

    config["model_list"] = kept

    with open(OUTPUT_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    print(f"[config] Generated {OUTPUT_PATH}: {len(kept)} models registered, {len(skipped)} skipped")
    if skipped:
        print(f"[config] Skipped: {skipped}")


if __name__ == "__main__":
    generate()
