"""
core/llm_client.py
==================
Unified async LLM client abstraction.

Features:
- Primary / fallback model switching on timeout or error
- Configurable timeout and exponential-backoff retry
- DEMO_MODE: returns cached JSON from disk instead of calling the API
- Structured output: always returns a Pydantic-validated model
- Supports text, image (bytes), and audio (bytes) input via Google Gemini SDK

Usage:
    from app.core.llm_client import get_llm_client
    client = get_llm_client()
    result = await client.generate_structured(
        prompt="...",
        response_model=MyPydanticModel,
        images=[image_bytes],
    )
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


# ── Custom exceptions ─────────────────────────────────────────────────────────

class LLMError(Exception):
    """Raised when all LLM attempts (primary + fallback) fail."""


class LLMTimeoutError(LLMError):
    """Raised specifically on timeout."""


class LLMValidationError(LLMError):
    """Raised when LLM output fails Pydantic validation after all retries."""


# ── Abstract interface ────────────────────────────────────────────────────────

class LLMClient(ABC):
    """Contract that every LLM backend must satisfy."""

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        *,
        images: Optional[list[bytes]] = None,
        audio: Optional[bytes] = None,
        audio_mime: str = "audio/mp4",
        system: Optional[str] = None,
        temperature: float = 0.2,
        demo_cache_key: Optional[str] = None,
    ) -> T:
        """
        Generate a structured response validated against `response_model`.
        Raises LLMError on unrecoverable failure after all retries.
        """

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Return an embedding vector for `text`."""

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.3,
    ) -> str:
        """Generate a free-text response (for complaint letter generation)."""


# ── Demo-mode replay ─────────────────────────────────────────────────────────

class DemoModeClient(LLMClient):
    """
    Replays pre-cached JSON responses from disk.
    Used when DEMO_MODE=true or as a last-resort fallback.
    """

    def __init__(self, cache_dir: str):
        self._cache_dir = Path(cache_dir)

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        *,
        images: Optional[list[bytes]] = None,
        audio: Optional[bytes] = None,
        audio_mime: str = "audio/mp4",
        system: Optional[str] = None,
        temperature: float = 0.2,
        demo_cache_key: Optional[str] = None,
    ) -> T:
        target_file: Optional[Path] = None

        if demo_cache_key:
            exact = self._cache_dir / f"{demo_cache_key}.json"
            if exact.exists():
                target_file = exact
            else:
                # Suffix matching (e.g. perceive, router, intake, severity, text_classify)
                suffix = demo_cache_key.rsplit("_", 1)[-1]
                if suffix == "classify":
                    suffix = "perceive"

                # Only inspect the report context, not the schema's list of
                # allowed hazard labels (which always contains "pothole").
                prompt_lower = prompt.lower()

                # Extract category marker if present
                category_text = ""
                if "detected category:" in prompt_lower:
                    category_text = prompt_lower.split("detected category:", 1)[1].split("\n", 1)[0].strip()
                elif "\n  category:" in prompt_lower:
                    category_text = prompt_lower.split("\n  category:", 1)[1].split("\n", 1)[0].strip()
                elif "\ncategory:" in prompt_lower:
                    category_text = prompt_lower.split("\ncategory:", 1)[1].split("\n", 1)[0].strip()

                # Extract user / grievance description text
                user_text = ""
                if "grievance description:" in prompt_lower:
                    after_marker = prompt_lower.split("grievance description:", 1)[1].strip()
                    for stop_marker in ("\nuse the grievance", "\nassessment tasks:", "\nreturn a json", "\n\n"):
                        if stop_marker in after_marker:
                            after_marker = after_marker.split(stop_marker, 1)[0].strip()
                    user_text = after_marker
                elif "issue description:" in prompt_lower:
                    after_marker = prompt_lower.split("issue description:", 1)[1]
                    for stop_marker in ("\ndetected category:", "\nassessment", "\nlocation:", "\n\n"):
                        if stop_marker in after_marker:
                            after_marker = after_marker.split(stop_marker, 1)[0].strip()
                    user_text = after_marker
                elif "description to classify:" in prompt_lower:
                    user_text = prompt_lower.split("description to classify:", 1)[1].strip()
                elif "\n  description:" in prompt_lower:
                    user_text = prompt_lower.split("\n  description:", 1)[1].split("\n", 1)[0].strip()
                elif "\ndescription:" in prompt_lower:
                    user_text = prompt_lower.split("\ndescription:", 1)[1].split("\n", 1)[0].strip()
                elif "description:" in prompt_lower:
                    after_desc = prompt_lower.split("description:", 1)[1].strip()
                    user_text = after_desc.split("\n", 1)[0].strip()

                user_text = user_text.strip(" \t\r\n\"'")

                category_norm = (
                    category_text.replace("issuecategory.", "").replace("category.", "").replace("-", "_").strip()
                )
                if category_norm in ("road_damage", "road damage", "pothole"):
                    idx = "001"
                elif category_norm in ("water_leak", "water leak", "water", "flood"):
                    idx = "002"
                elif category_norm in ("streetlight", "street_light", "street light"):
                    idx = "003"
                elif category_norm in ("garbage", "waste", "solid_waste"):
                    idx = "004"
                elif category_norm in ("sewage", "drainage", "drain"):
                    idx = "005"
                elif any(w in user_text for w in (
                    "streetlight", "street light", "streetlights", "street lights",
                    "street lamp", "lamp post", "light pole", "luminaire",
                    "junction box", "230v", "exposed wire", "dangling wire", "electric pole",
                    "dark street", "lights out", "blackout", "illumination", "dark corridor"
                )):
                    idx = "003"
                elif any(w in user_text for w in (
                    "pothole", "potholes", "crater", "craters", "asphalt", "arterial road",
                    "swerving", "road damage", "road collapse", "pavement"
                )):
                    idx = "001"
                elif any(w in user_text for w in (
                    "water leak", "pipeline rupture", "rupture", "leakage", "water pipe",
                    "pipe burst", "burst pipe", "potable water", "drinking water",
                    "water supply", "water main"
                )):
                    idx = "002"
                elif any(w in user_text for w in (
                    "garbage", "waste burning", "dumpster", "toxic smoke", "trash",
                    "waste dump", "litter", "biohazard"
                )):
                    idx = "004"
                elif any(w in user_text for w in (
                    "sewage", "sewer", "drain", "gutter", "manhole", "overflowing drain",
                    "foul smell", "blackwater"
                )):
                    idx = "005"
                elif any(w in user_text for w in ("water", "flood", "flooding", "waterlogged")):
                    idx = "002"
                else:
                    idx = "001"

                cand = self._cache_dir / f"golden_{idx}_{suffix}.json"
                if cand.exists():
                    target_file = cand
                else:
                    # Look for any matching golden file with this suffix
                    matches = list(self._cache_dir.glob(f"golden_*_{suffix}.json"))
                    if matches:
                        target_file = matches[0]

        if target_file and target_file.exists():
            try:
                data = json.loads(target_file.read_text(encoding="utf-8"))
                return response_model.model_validate(data)
            except Exception as e:
                logger.warning("Failed to validate cached demo data from %s: %s", target_file, e)

        # Fallback to response_model defaults or category-aware defaults if available
        try:
            fields = getattr(response_model, "model_fields", {})
            if "subtype" in fields and "asset_type" in fields:
                subtypes = {"001": "pothole", "002": "pipeline_leak", "003": "outage", "004": "bulk_dumping", "005": "blockage"}
                assets = {"001": "municipal_road", "002": "water_pipeline", "003": "public_streetlight", "004": "public_land", "005": "manhole"}
                return response_model(
                    subtype=subtypes.get(idx, "any"),
                    asset_type=assets.get(idx, "unknown"),
                    confidence=0.95,
                    is_ambiguous=False,
                    ambiguity_reason="",
                )
            return response_model()
        except Exception:
            raise LLMError(f"No matching demo cache or valid default for {demo_cache_key}")

    async def embed(self, text: str) -> list[float]:
        cache_file = self._cache_dir / "embeddings_cache.json"
        if cache_file.exists():
            try:
                store = json.loads(cache_file.read_text(encoding="utf-8"))
                if text in store:
                    return store[text]
            except Exception:
                pass
        settings = get_settings()
        return [0.0] * settings.EMBED_DIMENSION

    async def generate_text(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.3,
    ) -> str:
        return "This is a demo complaint letter. Network unavailable."


# ── Google AI (Gemini) backend ────────────────────────────────────────────────

class GoogleLLMClient(LLMClient):
    """
    Gemini multimodal client using google-generativeai SDK.
    Supports text, image bytes, and audio bytes.
    Falls back to `fallback_model` on timeout or rate-limit errors.
    On total failure, falls back to DemoModeClient if DEMO_CACHE_DIR has data.
    """

    def __init__(
        self,
        primary_model: str,
        fallback_model: str,
        api_key: str,
        timeout: float,
        max_retries: int,
        embed_model: str,
        demo_cache_dir: str,
    ):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._genai = genai
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.embed_model = embed_model
        self._demo_fallback = DemoModeClient(cache_dir=demo_cache_dir)

    def _build_parts(
        self,
        prompt: str,
        images: Optional[list[bytes]],
        audio: Optional[bytes],
        audio_mime: str,
        system: Optional[str],
    ) -> list:
        """Build the Gemini content parts list."""
        parts = []
        if system:
            parts.append(system + "\n\n")
        if images:
            for img_bytes in images:
                mime_type = "image/jpeg"
                if img_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                    mime_type = "image/png"
                elif img_bytes.startswith(b"RIFF") and len(img_bytes) > 12 and img_bytes[8:12] == b"WEBP":
                    mime_type = "image/webp"
                elif img_bytes.startswith(b"GIF"):
                    mime_type = "image/gif"
                parts.append({"mime_type": mime_type, "data": img_bytes})
        if audio:
            clean_audio_mime = audio_mime.split(";")[0].strip().lower()
            if clean_audio_mime in ("video/webm", "application/octet-stream"):
                clean_audio_mime = "audio/webm"
            parts.append({"mime_type": clean_audio_mime, "data": audio})
        parts.append(prompt)
        return parts

    async def _call_model(
        self,
        model_name: str,
        parts: list,
        temperature: float,
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> str:
        """Make a single async Gemini call, respecting timeout."""
        genai = self._genai
        loop = asyncio.get_running_loop()

        def _sync_call():
            config_kwargs: dict[str, Any] = {
                "temperature": temperature,
                "response_mime_type": "application/json",
            }
            try:
                if response_schema is not None:
                    config_kwargs["response_schema"] = response_schema
                model = genai.GenerativeModel(
                    model_name=model_name,
                    generation_config=genai.GenerationConfig(**config_kwargs),
                )
                response = model.generate_content(parts)
                return response.text
            except Exception:
                if response_schema is not None:
                    config_kwargs.pop("response_schema", None)
                    model = genai.GenerativeModel(
                        model_name=model_name,
                        generation_config=genai.GenerationConfig(**config_kwargs),
                    )
                    response = model.generate_content(parts)
                    return response.text
                raise

        async with asyncio.timeout(self.timeout):
            return await loop.run_in_executor(None, _sync_call)

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        *,
        images: Optional[list[bytes]] = None,
        audio: Optional[bytes] = None,
        audio_mime: str = "audio/mp4",
        system: Optional[str] = None,
        temperature: float = 0.2,
        demo_cache_key: Optional[str] = None,
    ) -> T:
        """
        Try primary model, then fallback model, with exponential backoff.
        Falls back to DemoModeClient if demo_cache_key is provided and all LLM attempts fail.
        """
        parts = self._build_parts(prompt, images, audio, audio_mime, system)
        last_exc: Exception | None = None

        for model_name in (self.primary_model, self.fallback_model):
            for attempt in range(self.max_retries):
                try:
                    raw_text = await self._call_model(
                        model_name, parts, temperature, response_schema=response_model
                    )
                    # Strip markdown code fences if present
                    raw_text = raw_text.strip()
                    if raw_text.startswith("```"):
                        raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0]
                    data = json.loads(raw_text)
                    return response_model.model_validate(data)
                except asyncio.TimeoutError as exc:
                    last_exc = LLMTimeoutError(f"Timeout on {model_name} attempt {attempt + 1}")
                    logger.warning("LLM timeout model=%s attempt=%d", model_name, attempt + 1)
                except json.JSONDecodeError as exc:
                    last_exc = LLMValidationError(f"JSON decode failed: {exc}")
                    logger.warning("LLM JSON parse error model=%s attempt=%d: %s", model_name, attempt + 1, exc)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    logger.warning("LLM error model=%s attempt=%d: %s", model_name, attempt + 1, exc)
                    err_str = str(exc).lower()
                    if "404" in err_str or "not found" in err_str or "no longer available" in err_str:
                        # Model does not exist or deprecated — skip retrying this model
                        break
                delay = 2 ** attempt
                logger.info("Retrying in %ds…", delay)
                await asyncio.sleep(delay)

        # All LLM attempts failed — try demo fallback
        if demo_cache_key:
            logger.error("All LLM attempts failed; falling back to demo cache key=%s", demo_cache_key)
            try:
                return await self._demo_fallback.generate_structured(
                    prompt, response_model, demo_cache_key=demo_cache_key
                )
            except LLMError:
                pass  # No demo cache available

        raise last_exc or LLMError("All LLM attempts failed with unknown error")

    async def embed(self, text: str) -> list[float]:
        """Generate embedding using the configured embed model."""
        genai = self._genai
        loop = asyncio.get_running_loop()

        def _sync_embed():
            result = genai.embed_content(
                model=self.embed_model,
                content=text,
                task_type="retrieval_document",
            )
            return result["embedding"]

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                async with asyncio.timeout(self.timeout):
                    return await loop.run_in_executor(None, _sync_embed)
            except asyncio.TimeoutError as exc:
                last_exc = LLMTimeoutError(f"Embed timeout attempt {attempt + 1}")
                logger.warning("Embed timeout attempt=%d", attempt + 1)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("Embed error attempt=%d: %s", attempt + 1, exc)
            await asyncio.sleep(2 ** attempt)

        logger.error("Embed failed after %d attempts; returning zero vector", self.max_retries)
        settings = get_settings()
        return [0.0] * settings.EMBED_DIMENSION

    async def generate_text(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.3,
    ) -> str:
        """Generate free-text (non-JSON) response for complaint letters."""
        genai = self._genai
        loop = asyncio.get_running_loop()

        def _sync_call(model_name: str):
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config=genai.GenerationConfig(temperature=temperature),
            )
            parts = []
            if system:
                parts.append(system + "\n\n")
            parts.append(prompt)
            return model.generate_content(parts).text

        for model_name in (self.primary_model, self.fallback_model):
            for attempt in range(self.max_retries):
                try:
                    async with asyncio.timeout(self.timeout):
                        return await loop.run_in_executor(None, _sync_call, model_name)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("generate_text error model=%s attempt=%d: %s", model_name, attempt + 1, exc)
                    err_str = str(exc).lower()
                    if "404" in err_str or "not found" in err_str or "no longer available" in err_str:
                        break
                await asyncio.sleep(2 ** attempt)

        return await self._demo_fallback.generate_text(prompt, system=system, temperature=temperature)


# ── OpenAI backend ─────────────────────────────────────────────────────────────

class OpenAILLMClient(LLMClient):
    """OpenAI GPT-4o multimodal client (alternative provider)."""

    def __init__(
        self,
        primary_model: str,
        fallback_model: str,
        api_key: str,
        timeout: float,
        max_retries: int,
        embed_model: str,
        demo_cache_dir: str,
    ):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=api_key)
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.embed_model = embed_model
        self._demo_fallback = DemoModeClient(cache_dir=demo_cache_dir)

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        *,
        images: Optional[list[bytes]] = None,
        audio: Optional[bytes] = None,
        audio_mime: str = "audio/mp4",
        system: Optional[str] = None,
        temperature: float = 0.2,
        demo_cache_key: Optional[str] = None,
    ) -> T:
        import base64
        last_exc: Exception | None = None

        for model_name in (self.primary_model, self.fallback_model):
            for attempt in range(self.max_retries):
                try:
                    messages = []
                    if system:
                        messages.append({"role": "system", "content": system})

                    content: list = [{"type": "text", "text": prompt}]
                    if images:
                        for img_bytes in images:
                            b64 = base64.b64encode(img_bytes).decode()
                            content.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                            })
                    messages.append({"role": "user", "content": content})

                    async with asyncio.timeout(self.timeout):
                        resp = await self._client.chat.completions.create(
                            model=model_name,
                            messages=messages,
                            temperature=temperature,
                            response_format={"type": "json_object"},
                        )
                    raw = resp.choices[0].message.content or "{}"
                    return response_model.model_validate(json.loads(raw))
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    logger.warning("OpenAI error model=%s attempt=%d: %s", model_name, attempt + 1, exc)
                await asyncio.sleep(2 ** attempt)

        if demo_cache_key:
            try:
                return await self._demo_fallback.generate_structured(
                    prompt, response_model, demo_cache_key=demo_cache_key
                )
            except LLMError:
                pass
        raise last_exc or LLMError("All OpenAI attempts failed")

    async def embed(self, text: str) -> list[float]:
        for attempt in range(self.max_retries):
            try:
                async with asyncio.timeout(self.timeout):
                    resp = await self._client.embeddings.create(model=self.embed_model, input=text)
                    return resp.data[0].embedding
            except Exception as exc:  # noqa: BLE001
                logger.warning("OpenAI embed error attempt=%d: %s", attempt + 1, exc)
            await asyncio.sleep(2 ** attempt)
        settings = get_settings()
        return [0.0] * settings.EMBED_DIMENSION

    async def generate_text(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.3,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            async with asyncio.timeout(self.timeout):
                resp = await self._client.chat.completions.create(
                    model=self.primary_model,
                    messages=messages,
                    temperature=temperature,
                )
            return resp.choices[0].message.content or ""
        except Exception as exc:
            logger.error("generate_text failed: %s", exc)
            return ""


# ── Factory ───────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """Return the singleton LLM client based on config."""
    settings = get_settings()
    if settings.DEMO_MODE:
        logger.info("DEMO_MODE enabled — using DemoModeClient")
        return DemoModeClient(cache_dir=settings.DEMO_CACHE_DIR)

    if settings.LLM_PROVIDER == "google":
        return GoogleLLMClient(
            primary_model=settings.LLM_PRIMARY_MODEL,
            fallback_model=settings.LLM_FALLBACK_MODEL,
            api_key=settings.GOOGLE_API_KEY,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_retries=settings.LLM_MAX_RETRIES,
            embed_model=settings.EMBED_MODEL,
            demo_cache_dir=settings.DEMO_CACHE_DIR,
        )
    elif settings.LLM_PROVIDER == "openai":
        return OpenAILLMClient(
            primary_model=settings.LLM_PRIMARY_MODEL,
            fallback_model=settings.LLM_FALLBACK_MODEL,
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_retries=settings.LLM_MAX_RETRIES,
            embed_model=settings.EMBED_MODEL,
            demo_cache_dir=settings.DEMO_CACHE_DIR,
        )
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")
