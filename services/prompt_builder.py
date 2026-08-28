import re


# ============================================================
# PROMPT BUILDER
#
# Single source of truth for building the final Qwen prompt
# from a creative template + variables + optional product
# metadata. Do not duplicate this logic in API routes.
# ============================================================

_VARIABLE_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class PromptBuildError(ValueError):
    pass


def build_prompt(template, product_data=None, options=None):

    """
    Build the final generation prompt.

    Args:
        template: template dict from template_service
        product_data: optional dict with future product metadata
                      (productType, color, material, brand...)
        options: optional dict of user-selected variable overrides

    Returns:
        str: final prompt
    """

    if not template or not template.get("promptTemplate"):
        raise PromptBuildError(
            "A valid template with a promptTemplate is required."
        )

    options = options or {}

    variables = dict(template.get("variables") or {})

    # Optional product metadata can contribute variables too
    product_data = product_data or {}
    for key, value in product_data.items():
        if isinstance(value, str) and value.strip():
            variables[key] = value.strip()

    # User selections override defaults last
    for key, value in options.items():
        if value is not None and str(value).strip():
            variables[key] = str(value).strip()

    prompt_template = template["promptTemplate"]

    missing = [
        name
        for name in _VARIABLE_PATTERN.findall(prompt_template)
        if name not in variables
    ]

    if missing:
        raise PromptBuildError(
            f"Template '{template.get('id')}' is missing "
            f"variables: {', '.join(sorted(set(missing)))}"
        )

    def _replace(match):

        return variables[match.group(1)]

    final_prompt = _VARIABLE_PATTERN.sub(
        _replace,
        prompt_template
    )

    return final_prompt
