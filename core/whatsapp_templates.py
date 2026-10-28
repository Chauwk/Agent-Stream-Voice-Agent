"""
Helpers for the per-agent WhatsApp template catalog.

The `whatsappTemplate` field on an `exotel_agents` document is authored by the
admin portal, so this module is deliberately tolerant of several shapes and
normalizes them into a single list the LLM can choose from:

    None / "" / []                         -> []  (no templates; tool falls back)
    "order_confirmation"                   -> one name-only template
    {"name": "...", "description": "..."}  -> one template
    [ {...}, {...} ]                        -> many templates
    ["hello_world", "brochure"]            -> name-only templates
    {"hello_world": "Greet a new customer"}-> name -> description map

Each normalized template is a dict:
    {
      "name":         str,           # the templateName to send
      "description":  str,           # "when to use this" — shown to the agent only
      "languageCode": str | None,    # optional; the send API resolves it if omitted
      "variables":    [ {"slot": int, "meaning": str}, ... ],  # body {{1}}.. placeholders
    }

Field aliases accepted per template: name/templateName/template; description/desc/
whenToUse/when_to_use; languageCode/language/lang; variables/bodyParameters/params.
"""
from typing import Any, Optional

_NAME_KEYS = ("name", "templateName", "template")
_DESC_KEYS = ("description", "desc", "whenToUse", "when_to_use")
_LANG_KEYS = ("languageCode", "language", "lang")
_VAR_KEYS = ("variables", "bodyParameters", "body_parameters", "params")


def _first(d: dict, keys) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _normalize_variables(raw: Any) -> list:
    """Return [{'slot': int, 'meaning': str}, ...] from a variety of shapes."""
    if not raw:
        return []
    out = []
    if isinstance(raw, dict):
        raw = [raw]
    if isinstance(raw, (list, tuple)):
        for i, v in enumerate(raw, start=1):
            if isinstance(v, dict):
                slot = v.get("slot") or v.get("index") or i
                meaning = _first(v, ("meaning", "description", "desc", "name", "label")) or f"value {i}"
                try:
                    slot = int(slot)
                except (TypeError, ValueError):
                    slot = i
                out.append({"slot": slot, "meaning": str(meaning)})
            else:
                out.append({"slot": i, "meaning": str(v)})
    return out


def normalize_templates(raw: Any) -> list:
    """Coerce the raw `whatsappTemplate` field into a list of normalized dicts."""
    if not raw:
        return []

    # dict of {name: description} vs a single template object
    if isinstance(raw, dict):
        if any(k in raw for k in (_NAME_KEYS + _DESC_KEYS + _LANG_KEYS + _VAR_KEYS)):
            raw = [raw]
        else:
            raw = [{"name": k, "description": v} for k, v in raw.items()]

    if not isinstance(raw, (list, tuple)):
        raw = [raw]

    templates = []
    for item in raw:
        if isinstance(item, str):
            name, desc, lang, variables = item, "", None, []
        elif isinstance(item, dict):
            name = _first(item, _NAME_KEYS)
            desc = _first(item, _DESC_KEYS) or ""
            lang = _first(item, _LANG_KEYS)
            variables = _normalize_variables(_first(item, _VAR_KEYS))
        else:
            continue
        name = (str(name).strip() if name else "")
        if not name:
            continue
        templates.append({
            "name": name,
            "description": str(desc).strip(),
            "languageCode": (str(lang).strip() if lang else None),
            "variables": variables,
        })
    return templates


def first_template(raw: Any) -> Optional[dict]:
    """Return this agent's single configured template (the first one), or None.

    Each agent has exactly one approved template, so we only ever use the first
    normalized entry — but normalize_templates still tolerates a stray list.
    """
    templates = normalize_templates(raw)
    return templates[0] if templates else None


def render_single_template(template: Optional[dict]) -> str:
    """Render the one approved template for the system prompt. '' when none."""
    if not template:
        return ""
    purpose = f" Purpose: {template['description']}" if template["description"] else ""
    lines = [
        "### WhatsApp Message",
        f'This agent has one pre-approved WhatsApp template, "{template["name"]}". '
        f"When the customer wants it sent, call the send_whatsapp tool.{purpose}",
    ]
    if template["variables"]:
        slots = ", ".join(f"{{{{{v['slot']}}}}} = {v['meaning']}" for v in template["variables"])
        lines.append(
            f"It needs body_parameters in order: [{slots}]. "
            f"Collect these values from the customer before sending."
        )
    return "\n".join(lines)
