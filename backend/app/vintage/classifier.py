import base64
import json
import io

from anthropic import Anthropic
from PIL import Image

from app.config import settings
from app.vintage.router import _ERAS

_client = Anthropic(api_key=settings.anthropic_api_key)
_MAX_DIM = 1024

_SYSTEM_PROMPT = """You are a fashion historian and vintage garment expert.
Given a list of available fashion eras, garment descriptors, and optional images,
classify which era the garment most likely belongs to.

Respond ONLY with valid JSON in this exact format:
{
  "primary_era": {
    "id": "<era id from the list>",
    "label": "<era label>",
    "confidence": <float 0.0-1.0>,
    "reasoning": "<detailed explanation of why this era matches>"
  },
  "alternate_eras": [
    {"id": "<era id>", "label": "<era label>", "confidence": <float>, "reasoning": "<brief reasoning>"},
    {"id": "<era id>", "label": "<era label>", "confidence": <float>, "reasoning": "<brief reasoning>"}
  ],
  "matching_features": ["<feature 1>", "<feature 2>", "<feature 3>"],
  "related_keywords": ["<keyword 1>", "<keyword 2>", "<keyword 3>", "<keyword 4>", "<keyword 5>", "<keyword 6>"]
}

Rules:
- The era id must exactly match one of the provided era ids
- Confidence scores across primary + alternates should roughly sum to ~1.0
- matching_features should be 3-6 specific observable details that led to the classification
- If images are provided, weight them heavily alongside the text descriptors
- Be specific in your reasoning, referencing actual design elements
- related_keywords must be 5-8 search terms a reseller would actually use to list or search for THIS SPECIFIC GARMENT on eBay, Etsy, Poshmark, or Depop. Focus on the individual item: brand name, garment type, material, decade, wash/cut/style details. Examples for Levi's denim cutoff shorts: "Levi's denim shorts", "90s cutoff shorts", "vintage Levi's", "acid wash denim shorts", "1990s denim shorts vintage". Do NOT use broad era aesthetic labels (e.g. "Grunge", "Minimalism") — use concrete, searchable product terms.
"""


def _resize_image(data: bytes) -> tuple[bytes, str]:
    """Resize to max 1024px on longest side; return (jpeg_bytes, media_type)."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((_MAX_DIM, _MAX_DIM))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), "image/jpeg"


def classify_garment(descriptors: dict, images: list[bytes]) -> dict:
    """
    descriptors: {fabrics, prints, silhouettes, brands, colors, aesthetics,
                  key_garments, notes}  (all lists or strings, all optional)
    images: list of raw image bytes (0-10)
    Returns: {primary_era, alternate_eras, matching_features}
    """
    # Build era reference list for prompt
    era_list = "\n".join(
        f"- {e['id']}: {e['label']} ({e['period']})" for e in _ERAS
    )

    # Build descriptor text
    desc_lines = []
    for field in ("fabrics", "prints", "silhouettes", "brands", "colors",
                  "aesthetics", "key_garments", "hardware", "embellishments", "labels"):
        val = descriptors.get(field)
        if val:
            items = val if isinstance(val, list) else [val]
            if items:
                desc_lines.append(f"{field.replace('_', ' ').title()}: {', '.join(items)}")
    if descriptors.get("notes"):
        desc_lines.append(f"Additional notes: {descriptors['notes']}")

    desc_text = "\n".join(desc_lines) if desc_lines else "(no text descriptors provided)"

    # Build content blocks
    content = []
    for img_bytes in images:
        resized, media_type = _resize_image(img_bytes)
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": base64.standard_b64encode(resized).decode(),
            },
        })

    content.append({
        "type": "text",
        "text": (
            f"Available eras:\n{era_list}\n\n"
            f"Garment descriptors:\n{desc_text}\n\n"
            "Classify this garment. Respond ONLY with valid JSON."
        ),
    })

    response = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fence if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
