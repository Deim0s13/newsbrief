from __future__ import annotations
import os
import json
import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from .models import StructuredSummary, create_content_hash, create_cache_key
from .db import session_scope
from sqlalchemy import text

# Configure logging
logger = logging.getLogger(__name__)

# Configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("NEWSBRIEF_LLM_MODEL", "llama3.2:3b")
MAX_CONTENT_LENGTH = int(os.getenv("NEWSBRIEF_MAX_CONTENT_LENGTH", "8000"))
SUMMARY_MAX_LENGTH = int(os.getenv("NEWSBRIEF_SUMMARY_MAX_LENGTH", "300"))

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
            if isinstance(models, dict) and 'models' in models:
                model_names = [m.get('name', m.get('model', '')) for m in models['models'] if m]
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
        content = ' '.join(content.split())
        
        # Remove common noise patterns
        noise_patterns = [
            "Click here to", "Read more at", "Subscribe to", 
            "Follow us on", "Share this article", "Comments",
            "Advertisement", "Sponsored content"
        ]
        
        for pattern in noise_patterns:
            content = content.replace(pattern, "")
        
        return content.strip()
    
    def _check_structured_cache(self, content_hash: str, model: str) -> Optional[StructuredSummary]:
        """Check if structured summary exists in cache/database."""
        try:
            with session_scope() as s:
                row = s.execute(text("""
                    SELECT structured_summary_json, structured_summary_generated_at
                    FROM items 
                    WHERE structured_summary_content_hash = :content_hash 
                    AND structured_summary_model = :model
                    AND structured_summary_json IS NOT NULL
                    LIMIT 1
                """), {"content_hash": content_hash, "model": model}).first()
                
                if row and row[0]:
                    # Parse from database
                    generated_at = datetime.fromisoformat(row[1]) if row[1] else datetime.now()
                    return StructuredSummary.from_json_string(
                        row[0], content_hash, model, generated_at
                    )
        except Exception as e:
            logger.warning(f"Cache check failed: {e}")
        
        return None
    
    def _store_structured_summary(self, content_hash: str, structured_summary: StructuredSummary, item_id: Optional[int] = None) -> bool:
        """Store structured summary in database cache."""
        try:
            with session_scope() as s:
                if item_id:
                    # Update specific item
                    s.execute(text("""
                        UPDATE items 
                        SET structured_summary_json = :json_data,
                            structured_summary_model = :model,
                            structured_summary_content_hash = :content_hash,
                            structured_summary_generated_at = :generated_at
                        WHERE id = :item_id
                    """), {
                        "json_data": structured_summary.to_json_string(),
                        "model": structured_summary.model,
                        "content_hash": content_hash,
                        "generated_at": structured_summary.generated_at.isoformat(),
                        "item_id": item_id
                    })
                else:
                    # Update all items with matching content hash (for efficiency)
                    s.execute(text("""
                        UPDATE items 
                        SET structured_summary_json = :json_data,
                            structured_summary_model = :model,
                            structured_summary_content_hash = :content_hash,
                            structured_summary_generated_at = :generated_at
                        WHERE content_hash = :content_hash
                        AND (structured_summary_content_hash IS NULL OR structured_summary_model != :model)
                    """), {
                        "json_data": structured_summary.to_json_string(),
                        "model": structured_summary.model,
                        "content_hash": content_hash,
                        "generated_at": structured_summary.generated_at.isoformat()
                    })
                return True
        except Exception as e:
            logger.error(f"Failed to store structured summary: {e}")
            return False
    
    def summarize_article(self, title: str, content: str, model: Optional[str] = None, use_structured: bool = True) -> SummaryResult:
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
                error="No title or content provided"
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
                    generation_time=0.0
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
                    generated_at=datetime.now()
                )
                return SummaryResult(
                    summary=fallback_summary,
                    model="fallback",
                    success=True,
                    structured_summary=structured_summary,
                    content_hash=content_hash
                )
            else:
                return SummaryResult(
                    summary=fallback_summary,
                    model="fallback", 
                    success=True,
                    content_hash=content_hash
                )
        
        try:
            # Check service availability
            if not self.is_available():
                return self._fallback_summary(title, content, "Ollama service unavailable", use_structured, content_hash)
            
            # Ensure model is available
            if not self.ensure_model(model):
                return self._fallback_summary(title, content, f"Model {model} unavailable", use_structured, content_hash)
            
            # Generate summary based on type
            if use_structured:
                return self._generate_structured_summary(title, content, model, content_hash, start_time)
            else:
                return self._generate_legacy_summary(title, content, model, content_hash, start_time)
            
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return self._fallback_summary(title, content, str(e), use_structured, content_hash)
    
    def _generate_structured_summary(self, title: str, content: str, model: str, content_hash: str, start_time: datetime) -> SummaryResult:
        """Generate structured JSON summary."""
        prompt = self._create_structured_summary_prompt(title, content)
        
        logger.info(f"Generating structured summary with model {model}")
        response = self.client.generate(
            model=model,
            prompt=prompt,
            options={
                'temperature': 0.2,  # Lower temperature for consistent JSON
                'top_k': 40,
                'top_p': 0.8,
                'repeat_penalty': 1.1,
            }
        )
        
        raw_response = response.get('response', '').strip()
        if not raw_response:
            return self._fallback_summary(title, content, "Empty response from LLM", True, content_hash)
        
        # Parse JSON response
        try:
            # Clean potential markdown formatting
            if raw_response.startswith('```json'):
                raw_response = raw_response.replace('```json', '').replace('```', '').strip()
            elif raw_response.startswith('```'):
                raw_response = raw_response.replace('```', '').strip()
            
            json_data = json.loads(raw_response)
            
            # Validate required fields
            required_fields = ['bullets', 'why_it_matters', 'tags']
            for field in required_fields:
                if field not in json_data:
                    raise ValueError(f"Missing required field: {field}")
            
            # Create structured summary
            structured_summary = StructuredSummary(
                bullets=json_data['bullets'],
                why_it_matters=json_data['why_it_matters'],
                tags=json_data['tags'],
                content_hash=content_hash,
                model=model,
                generated_at=datetime.now()
            )
            
            # Store in cache
            self._store_structured_summary(content_hash, structured_summary)
            
            # Calculate metrics
            generation_time = (datetime.now() - start_time).total_seconds()
            tokens_used = len(prompt.split()) + len(raw_response.split())
            
            return SummaryResult(
                summary=structured_summary.to_json_string(),  # Legacy field
                model=model,
                success=True,
                tokens_used=tokens_used,
                generation_time=generation_time,
                structured_summary=structured_summary,
                content_hash=content_hash
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}. Raw: {raw_response[:200]}")
            return self._fallback_summary(title, content, f"Invalid JSON response: {e}", True, content_hash)
        except Exception as e:
            logger.error(f"Failed to create structured summary: {e}")
            return self._fallback_summary(title, content, f"Summary creation failed: {e}", True, content_hash)
    
    def _generate_legacy_summary(self, title: str, content: str, model: str, content_hash: str, start_time: datetime) -> SummaryResult:
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
                'temperature': 0.3,
                'top_k': 40,
                'top_p': 0.9,
                'repeat_penalty': 1.1,
                'num_predict': SUMMARY_MAX_LENGTH
            }
        )
        
        summary = response.get('response', '').strip()
        if not summary:
            return self._fallback_summary(title, content, "Empty response from LLM", False, content_hash)
        
        generation_time = (datetime.now() - start_time).total_seconds()
        tokens_used = len(prompt.split()) + len(summary.split())
        
        return SummaryResult(
            summary=summary,
            model=model,
            success=True,
            tokens_used=tokens_used,
            generation_time=generation_time,
            content_hash=content_hash
        )
    
    def _fallback_summary(self, title: str, content: str, error: str, use_structured: bool = False, content_hash: Optional[str] = None) -> SummaryResult:
        """Generate a fallback summary when LLM fails."""
        # Simple extractive summary: first few sentences
        sentences = content.split('. ')
        if len(sentences) > 3:
            fallback_text = '. '.join(sentences[:3]) + '.'
        else:
            fallback_text = content[:300] + "..." if len(content) > 300 else content
        
        if not fallback_text.strip():
            fallback_text = title
        
        if use_structured and content_hash:
            # Create basic structured fallback
            structured_summary = StructuredSummary(
                bullets=[fallback_text[:80] + "..." if len(fallback_text) > 80 else fallback_text],
                why_it_matters="Unable to analyze article content due to technical issues.",
                tags=["article", "news", "error"],
                content_hash=content_hash,
                model="fallback",
                generated_at=datetime.now()
            )
            return SummaryResult(
                summary=fallback_text,
                model="fallback",
                success=False,
                error=error,
                structured_summary=structured_summary,
                content_hash=content_hash
            )
        
        return SummaryResult(
            summary=fallback_text,
            model="fallback",
            success=False,
            error=error,
            content_hash=content_hash
        )
    
    def batch_summarize(self, articles: list[tuple[str, str]], model: Optional[str] = None, use_structured: bool = True) -> list[SummaryResult]:
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
                results.append(SummaryResult(
                    summary="",
                    model=model or self.model,
                    success=False,
                    error=f"Batch processing error: {e}",
                    content_hash=content_hash
                ))
        
        return results

# Singleton service instance
_llm_service = None

def get_llm_service() -> LLMService:
    """Get or create the LLM service singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service

def summarize_article(title: str, content: str, model: Optional[str] = None, use_structured: bool = True) -> SummaryResult:
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
