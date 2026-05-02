import httpx
import asyncio
import base64
from typing import List
from loguru import logger
from app.core.config import settings
from app.db.models import Project


# ─── Prompt builder ───────────────────────────────────────────────────────────

STYLE_PROMPTS = {
    "japandi": "japandi style, minimal, warm wood tones, natural textures, zen atmosphere",
    "minimalism": "minimalist interior, clean lines, neutral palette, uncluttered",
    "modern": "modern interior design, contemporary furniture, sleek surfaces",
    "scandinavian": "scandinavian style, light colors, functional furniture, hygge",
    "loft": "loft style interior, exposed brick, industrial elements, open space",
    "neoclassic": "neoclassical interior, elegant moldings, symmetry, refined decor",
    "cozy_light": "cozy bright interior, warm lighting, soft textiles, inviting atmosphere",
}

BUDGET_QUALITY = {
    "minimal": "budget-friendly furnishing, IKEA-level quality",
    "medium": "mid-range furnishing, quality materials",
    "above_medium": "premium furnishing, designer pieces",
    "premium": "luxury interior, high-end materials and furniture",
}

ROOM_CONTEXT = {
    "kitchen": "kitchen interior",
    "bedroom": "bedroom interior",
    "living": "living room interior",
    "kids": "children's room interior",
    "bathroom": "bathroom interior",
    "office": "home office interior",
    "hallway": "hallway interior",
    "other": "room interior",
}


def build_image_prompt(project: Project) -> str:
    parts = []

    room = ROOM_CONTEXT.get(project.room_type, "room interior")
    parts.append(f"photorealistic {room}")

    if project.style:
        style_desc = STYLE_PROMPTS.get(project.style, project.style)
        parts.append(style_desc)

    if project.budget_tier:
        budget_desc = BUDGET_QUALITY.get(project.budget_tier, "")
        if budget_desc:
            parts.append(budget_desc)

    if project.area_m2:
        parts.append(f"{project.area_m2} square meters")

    if project.free_space_percent:
        parts.append(f"{project.free_space_percent}% open space, good flow")

    if project.ceiling_height:
        parts.append(f"{project.ceiling_height}m ceiling height")

    if project.keep_items:
        parts.append(f"keeping: {project.keep_items}")

    if project.extra_notes:
        parts.append(project.extra_notes)

    parts += [
        "8k resolution",
        "architectural photography",
        "professional interior design photo",
        "no distortion",
        "natural lighting",
    ]

    return ", ".join(parts)


def build_negative_prompt() -> str:
    return (
        "blurry, low quality, distorted perspective, cluttered, messy, "
        "blocked windows, blocked doors, oversized furniture, cartoon, "
        "illustration, sketch, watermark, text overlay"
    )


# ─── AI Client ────────────────────────────────────────────────────────────────

class AIGenerationClient:
    """Adapter for AI image generation APIs.
    Currently supports Replicate (stable-diffusion-xl).
    Easy to swap for Stability AI, OpenAI, etc.
    """

    REPLICATE_API_URL = "https://api.replicate.com/v1/predictions"

    async def generate_interior(
        self,
        project: Project,
        input_image_bytes: bytes,
        num_variants: int = 1,
    ) -> List[bytes]:
        """Generate interior visualization images.
        Returns list of image bytes.
        """
        prompt = build_image_prompt(project)
        negative_prompt = build_negative_prompt()

        logger.info(f"AI prompt for project {project.id}: {prompt[:100]}...")

        # Encode input image to base64
        image_b64 = base64.b64encode(input_image_bytes).decode()

        results = []
        for i in range(num_variants):
            try:
                image_bytes = await self._call_replicate(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    image_b64=image_b64,
                )
                results.append(image_bytes)
                logger.info(f"Generated variant {i+1}/{num_variants} for project {project.id}")
            except Exception as e:
                logger.error(f"Generation variant {i+1} failed: {e}")
                if not results:
                    raise  # fail if zero results

        return results

    async def _call_replicate(
        self,
        prompt: str,
        negative_prompt: str,
        image_b64: str,
    ) -> bytes:
        """Call Replicate API for SDXL image generation."""
        headers = {
            "Authorization": f"Token {settings.ai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "version": settings.ai_model,
            "input": {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "image": f"data:image/jpeg;base64,{image_b64}",
                "prompt_strength": 0.75,
                "num_inference_steps": 30,
                "guidance_scale": 7.5,
                "width": 1024,
                "height": 1024,
            },
        }

        async with httpx.AsyncClient(timeout=120) as client:
            # Create prediction
            response = await client.post(
                self.REPLICATE_API_URL, headers=headers, json=payload
            )
            response.raise_for_status()
            prediction = response.json()
            prediction_id = prediction["id"]

            # Poll for result
            poll_url = f"{self.REPLICATE_API_URL}/{prediction_id}"
            for attempt in range(60):  # Max 60 * 3 = 3 minutes
                await asyncio.sleep(3)
                poll_response = await client.get(poll_url, headers=headers)
                poll_response.raise_for_status()
                data = poll_response.json()

                status = data.get("status")
                if status == "succeeded":
                    output_url = data["output"][0]
                    img_response = await client.get(output_url)
                    img_response.raise_for_status()
                    return img_response.content
                elif status == "failed":
                    raise RuntimeError(f"Replicate prediction failed: {data.get('error')}")

            raise TimeoutError("AI generation timed out after 3 minutes")

    async def analyze_photo(self, image_bytes: bytes) -> dict:
        """Basic vision analysis stub. In production, call GPT-4V or similar."""
        # This is a stub — replace with real vision API call
        return {
            "quality": "ok",
            "detected_objects": [],
            "estimated_room_type": "unknown",
        }


ai_client = AIGenerationClient()
