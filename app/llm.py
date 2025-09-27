from __future__ import annotations
import os
import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

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
    summary: str
    model: str
    success: bool
    error: Optional[str] = None
    tokens_used: Optional[int] = None
    generation_time: Optional[float] = None

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
    
    def _create_summary_prompt(self, title: str, content: str) -> str:
        """Create a focused summarization prompt."""
        # Clean and truncate content if too long
        content = self._clean_content(content)
        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH] + "..."
        
        prompt = f"""Please provide a concise, informative summary of this news article.
Focus on the key facts, main points, and important details.
Keep the summary between 100-{SUMMARY_MAX_LENGTH} words.

Title: {title}

Article:
{content}

Summary:"""
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
    
    def summarize_article(self, title: str, content: str, model: Optional[str] = None) -> SummaryResult:
        """
        Generate an AI summary for an article.
        
        Args:
            title: Article title
            content: Article content (full text)
            model: Optional model override
            
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
        
        # Fallback to title if no content
        if not content:
            return SummaryResult(
                summary=f"Article: {title}",
                model="fallback",
                success=True
            )
        
        try:
            # Check service availability
            if not self.is_available():
                return self._fallback_summary(title, content, "Ollama service unavailable")
            
            # Ensure model is available
            if not self.ensure_model(model):
                return self._fallback_summary(title, content, f"Model {model} unavailable")
            
            # Generate summary
            prompt = self._create_summary_prompt(title, content)
            
            logger.info(f"Generating summary with model {model}")
            response = self.client.generate(
                model=model,
                prompt=prompt,
                options={
                    'temperature': 0.3,  # Lower temperature for more focused summaries
                    'top_k': 40,
                    'top_p': 0.9,
                    'repeat_penalty': 1.1,
                    'num_predict': SUMMARY_MAX_LENGTH  # Limit output length
                }
            )
            
            summary = response.get('response', '').strip()
            if not summary:
                return self._fallback_summary(title, content, "Empty response from LLM")
            
            # Calculate metrics
            generation_time = (datetime.now() - start_time).total_seconds()
            tokens_used = len(prompt.split()) + len(summary.split())  # Rough estimate
            
            return SummaryResult(
                summary=summary,
                model=model,
                success=True,
                tokens_used=tokens_used,
                generation_time=generation_time
            )
            
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return self._fallback_summary(title, content, str(e))
    
    def _fallback_summary(self, title: str, content: str, error: str) -> SummaryResult:
        """Generate a fallback summary when LLM fails."""
        # Simple extractive summary: first few sentences
        sentences = content.split('. ')
        if len(sentences) > 3:
            fallback = '. '.join(sentences[:3]) + '.'
        else:
            fallback = content[:300] + "..." if len(content) > 300 else content
        
        if not fallback.strip():
            fallback = title
        
        return SummaryResult(
            summary=fallback,
            model="fallback",
            success=False,
            error=error
        )
    
    def batch_summarize(self, articles: list[tuple[str, str]], model: Optional[str] = None) -> list[SummaryResult]:
        """
        Summarize multiple articles in batch.
        
        Args:
            articles: List of (title, content) tuples
            model: Optional model override
            
        Returns:
            List of SummaryResult objects
        """
        results = []
        for title, content in articles:
            try:
                result = self.summarize_article(title, content, model)
                results.append(result)
            except Exception as e:
                results.append(SummaryResult(
                    summary="",
                    model=model or self.model,
                    success=False,
                    error=f"Batch processing error: {e}"
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

def summarize_article(title: str, content: str, model: Optional[str] = None) -> SummaryResult:
    """Convenience function for summarizing a single article."""
    service = get_llm_service()
    return service.summarize_article(title, content, model)

def is_llm_available() -> bool:
    """Check if LLM service is available."""
    try:
        service = get_llm_service()
        return service.is_available()
    except Exception:
        return False
