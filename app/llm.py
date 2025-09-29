from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy import text

from .db import session_scope
from .models import (
    ChunkSummary,
    StructuredSummary,
    TextChunk,
    create_cache_key,
    create_content_hash,
    extract_first_sentences,
)

# Configure logging
logger = logging.getLogger(__name__)

# Configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("NEWSBRIEF_LLM_MODEL", "llama3.2:3b")
MAX_CONTENT_LENGTH = int(os.getenv("NEWSBRIEF_MAX_CONTENT_LENGTH", "8000"))
SUMMARY_MAX_LENGTH = int(os.getenv("NEWSBRIEF_SUMMARY_MAX_LENGTH", "300"))

# Chunking configuration (new in v0.3.2)
CHUNK_SIZE_TOKENS = int(
    os.getenv("NEWSBRIEF_CHUNK_SIZE", "1500")
)  # Target chunk size in tokens
MAX_CHUNK_SIZE_TOKENS = int(
    os.getenv("NEWSBRIEF_MAX_CHUNK_SIZE", "2000")
)  # Max chunk size
CHUNK_OVERLAP_TOKENS = int(
    os.getenv("NEWSBRIEF_CHUNK_OVERLAP", "200")
)  # Overlap between chunks
CHUNKING_THRESHOLD_TOKENS = int(
    os.getenv("NEWSBRIEF_CHUNKING_THRESHOLD", "3000")
)  # When to trigger chunking


@dataclass
class SummaryResult:
    """Result of a summarization operation."""

    # Legacy fields for backward compatibility
    summary: str
    model: str
    success: bool
    error: Optional[str] = None
    tokens_used: Optional[int] = None
    generation_time: Optional[float] = None
    # New structured summary fields
    structured_summary: Optional[StructuredSummary] = None
    content_hash: Optional[str] = None
    cache_hit: bool = False


class LLMService:
    """Service for LLM-based content summarization using Ollama."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = DEFAULT_MODEL):
        self.base_url = base_url
        self.model = model
        self._client = None

    @property
    def client(self):
        """Lazy initialization of Ollama client."""
        if self._client is None:
            try:
                import ollama

                self._client = ollama.Client(host=self.base_url)
            except ImportError:
                logger.error("Ollama package not installed. Run: pip install ollama")
                raise
            except Exception as e:
                logger.error(f"Failed to initialize Ollama client: {e}")
                raise
        return self._client

    def is_available(self) -> bool:
        """Check if Ollama service is available."""
        try:
            # Try to list models to check connectivity
            self.client.list()
            return True
        except Exception as e:
            logger.warning(f"Ollama service not available: {e}")
            return False

    def ensure_model(self, model: Optional[str] = None) -> bool:
        """Ensure the specified model is available, pull if necessary."""
        model = model or self.model
        try:
            models = self.client.list()
            # Handle different response formats
            if isinstance(models, dict) and "models" in models:
                model_names = [
                    m.get("name", m.get("model", "")) for m in models["models"] if m
                ]
            else:
                model_names = []

            if model not in model_names:
                logger.info(f"Pulling model {model}...")
                self.client.pull(model)
                logger.info(f"Successfully pulled model {model}")

            return True
        except Exception as e:
            logger.error(f"Failed to ensure model {model}: {e}")
            return False

    def _count_tokens(self, text: str, model: str = "cl100k_base") -> int:
        """Count tokens in text using tiktoken."""
        try:
            import tiktoken

            encoding = tiktoken.get_encoding(model)
            return len(encoding.encode(text))
        except ImportError:
            logger.warning("tiktoken not available, using rough estimate")
            # Rough estimate: 1 token ≈ 4 characters
            return len(text) // 4
        except Exception as e:
            logger.warning(f"Token counting failed: {e}, using rough estimate")
            return len(text) // 4

    def _should_chunk_content(self, content: str) -> bool:
        """Determine if content should be chunked based on token count."""
        token_count = self._count_tokens(content)
        return token_count > CHUNKING_THRESHOLD_TOKENS

    def _chunk_text(self, title: str, content: str) -> List[TextChunk]:
        """
        Intelligently chunk text into segments respecting sentence boundaries.

        Uses a hierarchical approach:
        1. Split by paragraphs first
        2. Split by sentences if paragraphs are too long
        3. Split by words if sentences are too long
        """
        content = self._clean_content(content)
        total_tokens = self._count_tokens(f"{title}\n\n{content}")

        if total_tokens <= CHUNKING_THRESHOLD_TOKENS:
            return [
                TextChunk(
                    content=content,
                    start_pos=0,
                    end_pos=len(content),
                    token_count=total_tokens,
                    chunk_index=0,
                )
            ]

        chunks = []
        chunk_index = 0

        # Split by paragraphs
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

        current_chunk = ""
        current_start = 0

        for paragraph in paragraphs:
            # Include title context in first chunk
            test_content = (
                f"Title: {title}\n\n{current_chunk}\n\n{paragraph}".strip()
                if chunk_index == 0 and current_chunk == ""
                else f"{current_chunk}\n\n{paragraph}".strip()
            )
            test_tokens = self._count_tokens(test_content)

            if test_tokens <= CHUNK_SIZE_TOKENS or current_chunk == "":
                # Add paragraph to current chunk
                if current_chunk == "":
                    current_chunk = (
                        f"Title: {title}\n\n{paragraph}"
                        if chunk_index == 0
                        else paragraph
                    )
                else:
                    current_chunk = f"{current_chunk}\n\n{paragraph}"
            else:
                # Current chunk is complete, save it
                if current_chunk:
                    chunk_tokens = self._count_tokens(current_chunk)
                    chunks.append(
                        TextChunk(
                            content=current_chunk,
                            start_pos=current_start,
                            end_pos=current_start + len(current_chunk),
                            token_count=chunk_tokens,
                            chunk_index=chunk_index,
                        )
                    )
                    chunk_index += 1
                    current_start += len(current_chunk) + 2  # +2 for \n\n

                # Start new chunk with current paragraph
                current_chunk = paragraph

        # Add final chunk if any content remains
        if current_chunk:
            chunk_tokens = self._count_tokens(current_chunk)
            chunks.append(
                TextChunk(
                    content=current_chunk,
                    start_pos=current_start,
                    end_pos=current_start + len(current_chunk),
                    token_count=chunk_tokens,
                    chunk_index=chunk_index,
                )
            )

        # Handle chunks that are still too large by sentence splitting
        final_chunks = []
        for chunk in chunks:
            if chunk.token_count > MAX_CHUNK_SIZE_TOKENS:
                sub_chunks = self._split_chunk_by_sentences(chunk)
                final_chunks.extend(sub_chunks)
            else:
                final_chunks.append(chunk)

        logger.info(
            f"Chunked content into {len(final_chunks)} chunks (total tokens: {total_tokens})"
        )
        return final_chunks

    def _split_chunk_by_sentences(self, chunk: TextChunk) -> List[TextChunk]:
        """Split a large chunk by sentences."""
        sentences = re.split(r"[.!?]+\s+", chunk.content)
        sub_chunks = []
        current_content = ""
        chunk_index = chunk.chunk_index

        for sentence in sentences:
            test_content = f"{current_content} {sentence}".strip()
            test_tokens = self._count_tokens(test_content)

            if test_tokens <= CHUNK_SIZE_TOKENS or current_content == "":
                current_content = test_content
            else:
                if current_content:
                    sub_chunks.append(
                        TextChunk(
                            content=current_content,
                            start_pos=chunk.start_pos,
                            end_pos=chunk.start_pos + len(current_content),
                            token_count=self._count_tokens(current_content),
                            chunk_index=chunk_index,
                        )
                    )
                    chunk_index += 1
                current_content = sentence

        if current_content:
            sub_chunks.append(
                TextChunk(
                    content=current_content,
                    start_pos=chunk.start_pos,
                    end_pos=chunk.start_pos + len(current_content),
                    token_count=self._count_tokens(current_content),
                    chunk_index=chunk_index,
                )
            )

        return sub_chunks

    def _create_chunk_summary_prompt(
        self, title: str, chunk_content: str, chunk_index: int, total_chunks: int
    ) -> str:
        """Create prompt for summarizing individual chunks."""
        prompt = f"""You are analyzing part {chunk_index + 1} of {total_chunks} from a news article.

ARTICLE TITLE: {title}

CONTENT CHUNK {chunk_index + 1}/{total_chunks}:
{chunk_content}

Extract the key information from this chunk in JSON format:

{{
  "bullets": ["Key point 1 from this chunk", "Key point 2 from this chunk"],
  "key_topics": ["topic1", "topic2", "topic3"],
  "summary_text": "Brief summary of the main content in this chunk"
}}

INSTRUCTIONS:
- Focus only on information present in this chunk
- Create 2-4 bullet points for key facts/developments  
- Identify 2-5 key topics/themes
- Write 1-2 sentences summarizing the chunk
- Output ONLY valid JSON, no additional text

JSON Response:"""
        return prompt

    def _create_merge_summary_prompt(
        self, title: str, chunk_summaries: List[ChunkSummary]
    ) -> str:
        """Create prompt for merging chunk summaries into final structured summary."""

        # Combine all bullets and topics from chunks
        all_bullets = []
        all_topics = []
        chunk_texts = []

        for i, chunk_summary in enumerate(chunk_summaries):
            all_bullets.extend(chunk_summary.bullets)
            all_topics.extend(chunk_summary.key_topics)
            chunk_texts.append(f"Chunk {i+1}: {chunk_summary.summary_text}")

        combined_chunks = "\n".join(chunk_texts)

        prompt = f"""You are creating a final comprehensive summary by analyzing summaries from {len(chunk_summaries)} content chunks of a news article.

ARTICLE TITLE: {title}

CHUNK SUMMARIES:
{combined_chunks}

ALL EXTRACTED BULLETS:
{chr(10).join(f"- {bullet}" for bullet in all_bullets)}

ALL IDENTIFIED TOPICS:
{', '.join(set(all_topics))}

Create a comprehensive structured summary by synthesizing all chunk information:

{{
  "bullets": ["Synthesized key point 1", "Synthesized key point 2", "Synthesized key point 3"],
  "why_it_matters": "Explanation of overall significance and broader impact",
  "tags": ["tag1", "tag2", "tag3", "tag4"]
}}

INSTRUCTIONS:
- Create 3-5 comprehensive bullets that capture the most important points across all chunks
- Each bullet should be a complete, specific sentence (max 80 chars)
- Write why_it_matters explaining the overall significance (50-150 words)
- Select 3-6 most relevant tags from the identified topics (lowercase, hyphenated)
- Ensure coherent narrative that connects information from all chunks
- Output ONLY valid JSON, no additional text

JSON Response:"""
        return prompt

    def _summarize_chunk(
        self, title: str, chunk: TextChunk, model: str
    ) -> ChunkSummary:
        """Summarize a single content chunk (MAP phase)."""
        try:
            prompt = self._create_chunk_summary_prompt(
                title, chunk.content, chunk.chunk_index, 1
            )  # Will be updated with actual total

            response = self.client.generate(
                model=model,
                prompt=prompt,
                options={
                    "temperature": 0.2,
                    "top_k": 40,
                    "top_p": 0.8,
                    "repeat_penalty": 1.1,
                },
            )

            raw_response = response.get("response", "").strip()

            # Clean markdown formatting if present
            if raw_response.startswith("```json"):
                raw_response = (
                    raw_response.replace("```json", "").replace("```", "").strip()
                )
            elif raw_response.startswith("```"):
                raw_response = raw_response.replace("```", "").strip()

            data = json.loads(raw_response)

            return ChunkSummary(
                chunk_index=chunk.chunk_index,
                bullets=data.get("bullets", []),
                key_topics=data.get("key_topics", []),
                summary_text=data.get("summary_text", ""),
                token_count=chunk.token_count,
            )

        except Exception as e:
            logger.warning(f"Failed to summarize chunk {chunk.chunk_index}: {e}")
            # Create fallback summary
            return ChunkSummary(
                chunk_index=chunk.chunk_index,
                bullets=[
                    (
                        chunk.content[:80] + "..."
                        if len(chunk.content) > 80
                        else chunk.content
                    )
                ],
                key_topics=["content"],
                summary_text=(
                    chunk.content[:200] + "..."
                    if len(chunk.content) > 200
                    else chunk.content
                ),
                token_count=chunk.token_count,
            )

    def _merge_chunk_summaries(
        self,
        title: str,
        chunk_summaries: List[ChunkSummary],
        model: str,
        content_hash: str,
    ) -> StructuredSummary:
        """Merge chunk summaries into final structured summary (REDUCE phase)."""
        try:
            prompt = self._create_merge_summary_prompt(title, chunk_summaries)

            response = self.client.generate(
                model=model,
                prompt=prompt,
                options={
                    "temperature": 0.3,
                    "top_k": 40,
                    "top_p": 0.8,
                    "repeat_penalty": 1.1,
                },
            )

            raw_response = response.get("response", "").strip()

            # Clean markdown formatting if present
            if raw_response.startswith("```json"):
                raw_response = (
                    raw_response.replace("```json", "").replace("```", "").strip()
                )
            elif raw_response.startswith("```"):
                raw_response = raw_response.replace("```", "").strip()

            data = json.loads(raw_response)

            # Calculate total tokens across all chunks
            total_tokens = sum(cs.token_count for cs in chunk_summaries)

            return StructuredSummary(
                bullets=data.get("bullets", []),
                why_it_matters=data.get("why_it_matters", ""),
                tags=data.get("tags", []),
                content_hash=content_hash,
                model=model,
                generated_at=datetime.now(),
                # Chunking metadata
                is_chunked=True,
                chunk_count=len(chunk_summaries),
                total_tokens=total_tokens,
                processing_method="map-reduce",
            )

        except Exception as e:
            logger.error(f"Failed to merge chunk summaries: {e}")
            # Create fallback merged summary
            all_bullets = []
            all_topics = []
            for cs in chunk_summaries:
                all_bullets.extend(cs.bullets)
                all_topics.extend(cs.key_topics)

            return StructuredSummary(
                bullets=all_bullets[:5],  # Take first 5 bullets
                why_it_matters="Unable to analyze article significance due to technical issues.",
                tags=list(set(all_topics))[:5],  # Take unique topics, max 5
                content_hash=content_hash,
                model="fallback",
                generated_at=datetime.now(),
                is_chunked=True,
                chunk_count=len(chunk_summaries),
                total_tokens=sum(cs.token_count for cs in chunk_summaries),
                processing_method="map-reduce-fallback",
            )

    def _create_structured_summary_prompt(self, title: str, content: str) -> str:
        """Create a structured JSON summarization prompt."""
        # Clean and truncate content if too long
        content = self._clean_content(content)
        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH] + "..."

        prompt = f"""You are a news analysis AI. Analyze this article and provide a structured summary in JSON format.

ARTICLE DETAILS:
Title: {title}

Content:
{content}

INSTRUCTIONS:
Generate a JSON response with exactly these fields:
- "bullets": Array of 3-5 key points, each as a concise sentence (max 80 chars each)  
- "why_it_matters": Single paragraph explaining significance/impact (50-150 words)
- "tags": Array of 3-6 relevant topic tags (lowercase, single words or hyphenated phrases)

EXAMPLE OUTPUT FORMAT:
{{
  "bullets": [
    "Company announces major product launch with AI features",
    "Stock price rises 15% on positive investor reaction", 
    "New technology could disrupt existing market leaders"
  ],
  "why_it_matters": "This development signals a significant shift in the industry toward AI integration, potentially affecting millions of users and reshaping competitive dynamics among tech giants.",
  "tags": ["technology", "ai", "business", "innovation", "markets"]
}}

IMPORTANT:
- Output ONLY valid JSON, no additional text or explanation
- Keep bullets factual and specific
- Make tags relevant and searchable  
- Ensure "why_it_matters" explains broader implications

JSON Response:"""
        return prompt

    def _clean_content(self, content: str) -> str:
        """Clean and normalize content for better summarization."""
        if not content:
            return ""

        # Remove excessive whitespace
        content = " ".join(content.split())

        # Remove common noise patterns
        noise_patterns = [
            "Click here to",
            "Read more at",
            "Subscribe to",
            "Follow us on",
            "Share this article",
            "Comments",
            "Advertisement",
            "Sponsored content",
        ]

        for pattern in noise_patterns:
            content = content.replace(pattern, "")

        return content.strip()

    def _check_structured_cache(
        self, content_hash: str, model: str
    ) -> Optional[StructuredSummary]:
        """Check if structured summary exists in cache/database."""
        try:
            with session_scope() as s:
                row = s.execute(
                    text(
                        """
                    SELECT structured_summary_json, structured_summary_generated_at
                    FROM items 
                    WHERE structured_summary_content_hash = :content_hash 
                    AND structured_summary_model = :model
                    AND structured_summary_json IS NOT NULL
                    LIMIT 1
                """
                    ),
                    {"content_hash": content_hash, "model": model},
                ).first()

                if row and row[0]:
                    # Parse from database
                    generated_at = (
                        datetime.fromisoformat(row[1]) if row[1] else datetime.now()
                    )
                    return StructuredSummary.from_json_string(
                        row[0], content_hash, model, generated_at
                    )
        except Exception as e:
            logger.warning(f"Cache check failed: {e}")

        return None

    def _store_structured_summary(
        self,
        content_hash: str,
        structured_summary: StructuredSummary,
        item_id: Optional[int] = None,
    ) -> bool:
        """Store structured summary in database cache."""
        try:
            with session_scope() as s:
                if item_id:
                    # Update specific item
                    s.execute(
                        text(
                            """
                        UPDATE items 
                        SET structured_summary_json = :json_data,
                            structured_summary_model = :model,
                            structured_summary_content_hash = :content_hash,
                            structured_summary_generated_at = :generated_at
                        WHERE id = :item_id
                    """
                        ),
                        {
                            "json_data": structured_summary.to_json_string(),
                            "model": structured_summary.model,
                            "content_hash": content_hash,
                            "generated_at": structured_summary.generated_at.isoformat(),
                            "item_id": item_id,
                        },
                    )
                else:
                    # Update all items with matching content hash (for efficiency)
                    s.execute(
                        text(
                            """
                        UPDATE items 
                        SET structured_summary_json = :json_data,
                            structured_summary_model = :model,
                            structured_summary_content_hash = :content_hash,
                            structured_summary_generated_at = :generated_at
                        WHERE content_hash = :content_hash
                        AND (structured_summary_content_hash IS NULL OR structured_summary_model != :model)
                    """
                        ),
                        {
                            "json_data": structured_summary.to_json_string(),
                            "model": structured_summary.model,
                            "content_hash": content_hash,
                            "generated_at": structured_summary.generated_at.isoformat(),
                        },
                    )
                return True
        except Exception as e:
            logger.error(f"Failed to store structured summary: {e}")
            return False

    def summarize_article(
        self,
        title: str,
        content: str,
        model: Optional[str] = None,
        use_structured: bool = True,
    ) -> SummaryResult:
        """
        Generate an AI summary for an article.

        Args:
            title: Article title
            content: Article content (full text)
            model: Optional model override
            use_structured: Whether to generate structured JSON summary (default: True)

        Returns:
            SummaryResult with summary and metadata
        """
        model = model or self.model
        start_time = datetime.now()

        # Validate inputs
        if not title and not content:
            return SummaryResult(
                summary="",
                model=model,
                success=False,
                error="No title or content provided",
            )

        # Calculate content hash for caching
        content_hash = create_content_hash(title, content or "")

        # Check cache first (if using structured summaries)
        if use_structured:
            cached_summary = self._check_structured_cache(content_hash, model)
            if cached_summary:
                logger.info(f"Cache hit for content_hash={content_hash}, model={model}")
                return SummaryResult(
                    summary=cached_summary.to_json_string(),  # Legacy field
                    model=model,
                    success=True,
                    structured_summary=cached_summary,
                    content_hash=content_hash,
                    cache_hit=True,
                    generation_time=0.0,
                )

        # Fallback to title if no content
        if not content:
            fallback_summary = f"Article: {title}"
            if use_structured:
                # Create a basic structured summary for title-only
                structured_summary = StructuredSummary(
                    bullets=[title[:75] + "..." if len(title) > 75 else title],
                    why_it_matters="Limited content available for analysis.",
                    tags=["article", "news"],
                    content_hash=content_hash,
                    model="fallback",
                    generated_at=datetime.now(),
                    is_chunked=False,
                    chunk_count=None,
                    total_tokens=None,
                    processing_method="direct",
                )
                return SummaryResult(
                    summary=fallback_summary,
                    model="fallback",
                    success=True,
                    structured_summary=structured_summary,
                    content_hash=content_hash,
                )
            else:
                return SummaryResult(
                    summary=fallback_summary,
                    model="fallback",
                    success=True,
                    content_hash=content_hash,
                )

        try:
            # Check service availability
            if not self.is_available():
                return self._fallback_summary(
                    title,
                    content,
                    "Ollama service unavailable",
                    use_structured,
                    content_hash,
                )

            # Ensure model is available
            if not self.ensure_model(model):
                return self._fallback_summary(
                    title,
                    content,
                    f"Model {model} unavailable",
                    use_structured,
                    content_hash,
                )

            # Generate summary based on type
            if use_structured:
                return self._generate_structured_summary(
                    title, content, model, content_hash, start_time
                )
            else:
                return self._generate_legacy_summary(
                    title, content, model, content_hash, start_time
                )

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return self._fallback_summary(
                title, content, str(e), use_structured, content_hash
            )

    def _generate_structured_summary(
        self,
        title: str,
        content: str,
        model: str,
        content_hash: str,
        start_time: datetime,
    ) -> SummaryResult:
        """Generate structured JSON summary with automatic chunking for long content."""

        # Check if content should be chunked
        if self._should_chunk_content(f"{title}\n\n{content}"):
            logger.info(f"Content requires chunking, using map-reduce approach")
            return self._generate_chunked_summary(
                title, content, model, content_hash, start_time
            )
        else:
            logger.info(f"Content fits in single chunk, using direct approach")
            return self._generate_direct_summary(
                title, content, model, content_hash, start_time
            )

    def _generate_direct_summary(
        self,
        title: str,
        content: str,
        model: str,
        content_hash: str,
        start_time: datetime,
    ) -> SummaryResult:
        """Generate structured summary for content that fits in a single chunk."""
        prompt = self._create_structured_summary_prompt(title, content)

        logger.info(f"Generating direct structured summary with model {model}")
        response = self.client.generate(
            model=model,
            prompt=prompt,
            options={
                "temperature": 0.2,
                "top_k": 40,
                "top_p": 0.8,
                "repeat_penalty": 1.1,
            },
        )

        raw_response = response.get("response", "").strip()
        if not raw_response:
            return self._fallback_summary(
                title, content, "Empty response from LLM", True, content_hash
            )

        try:
            # Clean potential markdown formatting
            if raw_response.startswith("```json"):
                raw_response = (
                    raw_response.replace("```json", "").replace("```", "").strip()
                )
            elif raw_response.startswith("```"):
                raw_response = raw_response.replace("```", "").strip()

            json_data = json.loads(raw_response)

            # Validate required fields
            required_fields = ["bullets", "why_it_matters", "tags"]
            for field in required_fields:
                if field not in json_data:
                    raise ValueError(f"Missing required field: {field}")

            # Create structured summary (direct processing)
            total_tokens = self._count_tokens(f"{title}\n\n{content}")
            structured_summary = StructuredSummary(
                bullets=json_data["bullets"],
                why_it_matters=json_data["why_it_matters"],
                tags=json_data["tags"],
                content_hash=content_hash,
                model=model,
                generated_at=datetime.now(),
                # Chunking metadata (not chunked)
                is_chunked=False,
                chunk_count=1,
                total_tokens=total_tokens,
                processing_method="direct",
            )

            # Store in cache
            self._store_structured_summary(content_hash, structured_summary)

            # Calculate metrics
            generation_time = (datetime.now() - start_time).total_seconds()
            tokens_used = len(prompt.split()) + len(raw_response.split())

            return SummaryResult(
                summary=structured_summary.to_json_string(),
                model=model,
                success=True,
                tokens_used=tokens_used,
                generation_time=generation_time,
                structured_summary=structured_summary,
                content_hash=content_hash,
            )

        except json.JSONDecodeError as e:
            logger.error(
                f"Failed to parse JSON response: {e}. Raw: {raw_response[:200]}"
            )
            return self._fallback_summary(
                title, content, f"Invalid JSON response: {e}", True, content_hash
            )
        except Exception as e:
            logger.error(f"Failed to create structured summary: {e}")
            return self._fallback_summary(
                title, content, f"Summary creation failed: {e}", True, content_hash
            )

    def _generate_chunked_summary(
        self,
        title: str,
        content: str,
        model: str,
        content_hash: str,
        start_time: datetime,
    ) -> SummaryResult:
        """Generate structured summary using map-reduce approach for long content."""
        try:
            # MAP PHASE: Chunk the content
            chunks = self._chunk_text(title, content)
            logger.info(f"MAP-REDUCE: Processing {len(chunks)} chunks")

            # MAP PHASE: Summarize each chunk
            chunk_summaries = []
            for i, chunk in enumerate(chunks):
                # Update prompt with correct total count
                chunk_summary = self._summarize_chunk(title, chunk, model)
                chunk_summaries.append(chunk_summary)
                logger.info(f"Completed chunk {i+1}/{len(chunks)}")

            # REDUCE PHASE: Merge chunk summaries into final summary
            logger.info(f"REDUCE: Merging {len(chunk_summaries)} chunk summaries")
            final_summary = self._merge_chunk_summaries(
                title, chunk_summaries, model, content_hash
            )

            # Store in cache
            self._store_structured_summary(content_hash, final_summary)

            # Calculate metrics
            generation_time = (datetime.now() - start_time).total_seconds()
            total_prompt_tokens = sum(
                len(
                    self._create_chunk_summary_prompt(
                        title, chunk.content, chunk.chunk_index, len(chunks)
                    ).split()
                )
                for chunk in chunks
            )
            merge_prompt_tokens = len(
                self._create_merge_summary_prompt(title, chunk_summaries).split()
            )
            tokens_used = total_prompt_tokens + merge_prompt_tokens

            return SummaryResult(
                summary=final_summary.to_json_string(),
                model=model,
                success=True,
                tokens_used=tokens_used,
                generation_time=generation_time,
                structured_summary=final_summary,
                content_hash=content_hash,
            )

        except Exception as e:
            logger.error(f"Failed to generate chunked summary: {e}")
            return self._fallback_summary(
                title,
                content,
                f"Map-reduce summarization failed: {e}",
                True,
                content_hash,
            )

    def _generate_legacy_summary(
        self,
        title: str,
        content: str,
        model: str,
        content_hash: str,
        start_time: datetime,
    ) -> SummaryResult:
        """Generate legacy plain text summary."""
        prompt = f"""Please provide a concise, informative summary of this news article.
Focus on the key facts, main points, and important details.
Keep the summary between 100-{SUMMARY_MAX_LENGTH} words.

Title: {title}

Article:
{self._clean_content(content)[:MAX_CONTENT_LENGTH]}

Summary:"""

        logger.info(f"Generating legacy summary with model {model}")
        response = self.client.generate(
            model=model,
            prompt=prompt,
            options={
                "temperature": 0.3,
                "top_k": 40,
                "top_p": 0.9,
                "repeat_penalty": 1.1,
                "num_predict": SUMMARY_MAX_LENGTH,
            },
        )

        summary = response.get("response", "").strip()
        if not summary:
            return self._fallback_summary(
                title, content, "Empty response from LLM", False, content_hash
            )

        generation_time = (datetime.now() - start_time).total_seconds()
        tokens_used = len(prompt.split()) + len(summary.split())

        return SummaryResult(
            summary=summary,
            model=model,
            success=True,
            tokens_used=tokens_used,
            generation_time=generation_time,
            content_hash=content_hash,
        )

    def _fallback_summary(
        self,
        title: str,
        content: str,
        error: str,
        use_structured: bool = False,
        content_hash: Optional[str] = None,
    ) -> SummaryResult:
        """Generate a fallback summary when LLM fails using first 2 sentences."""
        logger.info(f"Generating fallback summary due to error: {error}")

        # Use intelligent sentence extraction for better fallback summaries
        fallback_text = extract_first_sentences(content, sentence_count=2)

        # If no content available, use title as fallback
        if not fallback_text.strip():
            fallback_text = title if title else "Content unavailable"

        # If still empty, provide a minimal fallback
        if not fallback_text.strip():
            fallback_text = "Article content could not be processed."

        if use_structured and content_hash:
            # Create intelligent structured fallback using extracted sentences
            sentences = fallback_text.split(". ")
            # Create bullets from individual sentences, limited to reasonable length
            bullets = [
                sentence.strip()
                + ("." if not sentence.strip().endswith((".", "!", "?")) else "")
                for sentence in sentences[:3]  # Max 3 bullets
                if sentence.strip()
            ]

            # Ensure we have at least one bullet
            if not bullets:
                bullets = [title if title else "Content unavailable"]

            # Create basic structured fallback
            structured_summary = StructuredSummary(
                bullets=bullets,
                why_it_matters="AI summarization unavailable. Showing first sentences of article content.",
                tags=["fallback", "content-preview"],
                content_hash=content_hash,
                model="fallback",
                generated_at=datetime.now(),
                is_chunked=False,
                chunk_count=None,
                total_tokens=None,
                processing_method="fallback-sentences",
            )
            return SummaryResult(
                summary=fallback_text,
                model="fallback",
                success=False,
                error=error,
                structured_summary=structured_summary,
                content_hash=content_hash,
            )

        return SummaryResult(
            summary=fallback_text,
            model="fallback",
            success=False,
            error=error,
            content_hash=content_hash,
        )

    def batch_summarize(
        self,
        articles: list[tuple[str, str]],
        model: Optional[str] = None,
        use_structured: bool = True,
    ) -> list[SummaryResult]:
        """
        Summarize multiple articles in batch.

        Args:
            articles: List of (title, content) tuples
            model: Optional model override
            use_structured: Whether to generate structured summaries

        Returns:
            List of SummaryResult objects
        """
        results = []
        for title, content in articles:
            try:
                result = self.summarize_article(title, content, model, use_structured)
                results.append(result)
            except Exception as e:
                content_hash = create_content_hash(title, content or "")
                results.append(
                    SummaryResult(
                        summary="",
                        model=model or self.model,
                        success=False,
                        error=f"Batch processing error: {e}",
                        content_hash=content_hash,
                    )
                )

        return results


# Singleton service instance
_llm_service = None


def get_llm_service() -> LLMService:
    """Get or create the LLM service singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


def summarize_article(
    title: str, content: str, model: Optional[str] = None, use_structured: bool = True
) -> SummaryResult:
    """Convenience function for summarizing a single article."""
    service = get_llm_service()
    return service.summarize_article(title, content, model, use_structured)


def is_llm_available() -> bool:
    """Check if LLM service is available."""
    try:
        service = get_llm_service()
        return service.is_available()
    except Exception:
        return False
