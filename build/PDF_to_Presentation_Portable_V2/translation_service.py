import requests
import uuid
import json
import time
import random
from typing import List, Dict, Optional
from config import AZURE_TRANSLATOR_ENDPOINT, AZURE_TRANSLATOR_KEY, AZURE_TRANSLATOR_REGION

class TranslationService:
    """Robust translation service with rate limiting, retry logic, and error handling"""
    
    def __init__(self):
        self.endpoint = AZURE_TRANSLATOR_ENDPOINT
        self.key = AZURE_TRANSLATOR_KEY
        self.region = AZURE_TRANSLATOR_REGION
        
        # Rate limiting configuration based on Azure limits
        self.max_chars_per_request = 45000  # Leave buffer below 50k limit
        self.max_elements_per_request = 900  # Leave buffer below 1k limit
        self.max_chars_per_minute = 30000   # Conservative rate limit
        self.max_requests_per_minute = 20   # Conservative request limit
        
        # Tracking for rate limiting
        self.request_times = []
        self.char_count_this_minute = 0
        self.request_count_this_minute = 0
        self.last_minute_reset = time.time()
        
        # Retry configuration
        self.max_retries = 5
        self.base_delay = 1.0  # Base delay in seconds
        self.max_delay = 60.0  # Maximum delay in seconds
        
    def _reset_rate_limits(self):
        """Reset rate limiting counters every minute"""
        current_time = time.time()
        if current_time - self.last_minute_reset >= 60:
            self.char_count_this_minute = 0
            self.request_count_this_minute = 0
            self.last_minute_reset = current_time
            # Clean old request times (older than 1 minute)
            self.request_times = [t for t in self.request_times if current_time - t < 60]
    
    def _wait_for_rate_limit(self, text_length: int):
        """Wait if we're approaching rate limits"""
        self._reset_rate_limits()
        
        # Check if we need to wait
        if (self.char_count_this_minute + text_length > self.max_chars_per_minute or
            self.request_count_this_minute >= self.max_requests_per_minute):
            
            wait_time = 60 - (time.time() - self.last_minute_reset)
            if wait_time > 0:
                print(f"⏳ Rate limit reached. Waiting {wait_time:.1f} seconds...")
                time.sleep(wait_time)
                self._reset_rate_limits()
    
    def _chunk_texts(self, texts: List[str], preserve_structure: bool = False) -> List[List[str]]:
        """Split texts into chunks that respect Azure limits
        
        Args:
            texts: List of texts to chunk
            preserve_structure: If True, tries to preserve paragraph/bullet point structure
        """
        chunks = []
        current_chunk = []
        current_chars = 0
        
        for text in texts:
            text_length = len(text)
            
            # If single text exceeds limit, split it intelligently
            if text_length > self.max_chars_per_request:
                if preserve_structure:
                    # Try to split by paragraphs first, then sentences, then words
                    split_texts = self._split_text_preserving_structure(text)
                else:
                    # Split by words for simple rejoining
                    split_texts = self._split_text_by_words(text)
                
                for split_text in split_texts:
                    split_length = len(split_text)
                    
                    # Check if adding this split would exceed limits
                    if (len(current_chunk) >= self.max_elements_per_request or 
                        current_chars + split_length >= self.max_chars_per_request):
                        chunks.append(current_chunk)
                        current_chunk = [split_text]
                        current_chars = split_length
                    else:
                        current_chunk.append(split_text)
                        current_chars += split_length
            else:
                # Check if adding this text would exceed limits
                if (len(current_chunk) >= self.max_elements_per_request or 
                    current_chars + text_length >= self.max_chars_per_request):
                    chunks.append(current_chunk)
                    current_chunk = [text]
                    current_chars = text_length
                else:
                    current_chunk.append(text)
                    current_chars += text_length
        
        # Add remaining chunk
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _split_text_preserving_structure(self, text: str) -> List[str]:
        """Split text while trying to preserve paragraph and sentence structure"""
        # First try to split by double newlines (paragraphs)
        paragraphs = text.split('\n\n')
        if len(paragraphs) > 1:
            result = []
            for paragraph in paragraphs:
                if len(paragraph) <= self.max_chars_per_request:
                    result.append(paragraph.strip())
                else:
                    # Paragraph too long, split by sentences
                    sentences = self._split_by_sentences(paragraph)
                    result.extend(sentences)
            return [p for p in result if p.strip()]
        
        # If no paragraphs, try sentences
        return self._split_by_sentences(text)
    
    def _split_by_sentences(self, text: str) -> List[str]:
        """Split text by sentences"""
        import re
        # Split by sentence endings
        sentences = re.split(r'(?<=[.!?])\s+', text)
        result = []
        current = ""
        
        for sentence in sentences:
            if len(current + " " + sentence) <= self.max_chars_per_request:
                current += " " + sentence if current else sentence
            else:
                if current:
                    result.append(current.strip())
                if len(sentence) <= self.max_chars_per_request:
                    current = sentence
                else:
                    # Sentence too long, split by words
                    result.append(current.strip())
                    word_splits = self._split_text_by_words(sentence)
                    result.extend(word_splits)
                    current = ""
        
        if current:
            result.append(current.strip())
        
        return [s for s in result if s.strip()]
    
    def _split_text_by_words(self, text: str) -> List[str]:
        """Split text by words for simple rejoining"""
        words = text.split()
        result = []
        current = ""
        
        for word in words:
            if len(current + " " + word) <= self.max_chars_per_request:
                current += " " + word if current else word
            else:
                if current:
                    result.append(current.strip())
                current = word
        
        if current:
            result.append(current.strip())
        
        return [w for w in result if w.strip()]
    
    def _rejoin_translated_text(self, translated_chunks: List[str], original_text: str = None) -> str:
        """Rejoin translated chunks with appropriate spacing"""
        if not translated_chunks:
            return ""
        
        # If we have the original text, try to preserve its structure
        if original_text:
            # Check if original had paragraph breaks
            if '\n\n' in original_text:
                # Preserve paragraph structure
                return '\n\n'.join(translated_chunks)
            elif '\n' in original_text:
                # Preserve line breaks
                return '\n'.join(translated_chunks)
        
        # Default: join with spaces
        return ' '.join(translated_chunks)
    
    def _make_translation_request(self, texts: List[str], target_language: str, 
                                source_language: str = 'en') -> List[str]:
        """Make a single translation request with retry logic"""
        
        for attempt in range(self.max_retries):
            try:
                # Prepare the request
                url = f"{self.endpoint}/translate"
                
                params = {
                    'api-version': '3.0',
                    'from': source_language,
                    'to': target_language
                }
                
                headers = {
                    'Ocp-Apim-Subscription-Key': self.key,
                    'Ocp-Apim-Subscription-Region': self.region,
                    'Content-type': 'application/json',
                    'X-ClientTraceId': str(uuid.uuid4())
                }
                
                body = [{'text': text} for text in texts]
                
                # Make the request
                response = requests.post(url, params=params, headers=headers, json=body, timeout=30)
                
                # Handle different HTTP status codes
                if response.status_code == 200:
                    # Success
                    result = response.json()
                    translated_texts = [item['translations'][0]['text'] for item in result]
                    
                    # Update rate limiting counters
                    total_chars = sum(len(text) for text in texts)
                    self.char_count_this_minute += total_chars
                    self.request_count_this_minute += 1
                    self.request_times.append(time.time())
                    
                    return translated_texts
                
                elif response.status_code == 429:
                    # Rate limit exceeded
                    retry_after = response.headers.get('Retry-After')
                    if retry_after:
                        wait_time = int(retry_after)
                    else:
                        # Exponential backoff with jitter
                        wait_time = min(
                            self.base_delay * (2 ** attempt) + random.uniform(0, 1),
                            self.max_delay
                        )
                    
                    print(f"⚠️ Rate limit hit (429). Waiting {wait_time:.1f} seconds before retry {attempt + 1}/{self.max_retries}")
                    time.sleep(wait_time)
                    continue
                
                elif response.status_code in [500, 502, 503, 504]:
                    # Server errors - retry with exponential backoff
                    wait_time = min(
                        self.base_delay * (2 ** attempt) + random.uniform(0, 1),
                        self.max_delay
                    )
                    print(f"⚠️ Server error {response.status_code}. Waiting {wait_time:.1f} seconds before retry {attempt + 1}/{self.max_retries}")
                    time.sleep(wait_time)
                    continue
                
                else:
                    # Other errors - don't retry
                    response.raise_for_status()
                    
            except requests.exceptions.Timeout:
                wait_time = min(
                    self.base_delay * (2 ** attempt) + random.uniform(0, 1),
                    self.max_delay
                )
                print(f"⚠️ Request timeout. Waiting {wait_time:.1f} seconds before retry {attempt + 1}/{self.max_retries}")
                time.sleep(wait_time)
                continue
                
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise Exception(f"Translation request failed after {self.max_retries} attempts: {e}")
                
                wait_time = min(
                    self.base_delay * (2 ** attempt) + random.uniform(0, 1),
                    self.max_delay
                )
                print(f"⚠️ Request error: {e}. Waiting {wait_time:.1f} seconds before retry {attempt + 1}/{self.max_retries}")
                time.sleep(wait_time)
                continue
        
        raise Exception(f"Translation failed after {self.max_retries} attempts")
    
    def translate_text(self, text: str, target_language: str, source_language: str = 'en') -> str:
        """Translate a single text string with robust error handling"""
        if not self.endpoint or not self.key:
            raise Exception("Azure Translator credentials not configured")
        
        if not text or not text.strip():
            return text
        
        # Check rate limits
        self._wait_for_rate_limit(len(text))
        
        # If text is too long, chunk it
        if len(text) > self.max_chars_per_request:
            chunks = self._chunk_texts([text], preserve_structure=True)
            translated_chunks = []
            
            for chunk in chunks:
                translated_chunk = self._make_translation_request(chunk, target_language, source_language)
                translated_chunks.extend(translated_chunk)
            
            # Rejoin the translated chunks with proper spacing
            return self._rejoin_translated_text(translated_chunks, original_text=text)
        else:
            result = self._make_translation_request([text], target_language, source_language)
            return result[0]
    
    def translate_batch(self, texts: List[str], target_language: str, source_language: str = 'en') -> List[str]:
        """Translate multiple text strings with chunking and rate limiting
        
        This method handles different content types:
        - Individual paragraphs/bullet points: Each item is translated separately
        - Long texts: Split intelligently and rejoined properly
        """
        if not self.endpoint or not self.key:
            raise Exception("Azure Translator credentials not configured")
        
        if not texts:
            return []
        
        # Filter out empty texts but keep track of their positions
        non_empty_texts = []
        non_empty_indices = []
        
        for i, text in enumerate(texts):
            if text and text.strip():
                non_empty_texts.append(text)
                non_empty_indices.append(i)
        
        if not non_empty_texts:
            return texts  # Return original list if all empty
        
        # For batch translation, we treat each text as a separate item
        # This preserves the structure of slide content (paragraphs, bullet points, etc.)
        chunks = self._chunk_texts(non_empty_texts, preserve_structure=False)
        
        all_translated = []
        for i, chunk in enumerate(chunks):
            print(f"🔄 Translating chunk {i + 1}/{len(chunks)} ({len(chunk)} items, {sum(len(t) for t in chunk)} chars)")
            
            # Check rate limits before each chunk
            chunk_chars = sum(len(text) for text in chunk)
            self._wait_for_rate_limit(chunk_chars)
            
            # Translate the chunk
            translated_chunk = self._make_translation_request(chunk, target_language, source_language)
            all_translated.extend(translated_chunk)
            
            # Small delay between chunks to be respectful
            if i < len(chunks) - 1:
                time.sleep(0.5)
        
        # Map back to original list structure (preserving empty texts and order)
        result = texts.copy()  # Start with original list
        
        # Replace non-empty texts with their translations
        for i, translated_text in enumerate(all_translated):
            original_index = non_empty_indices[i]
            result[original_index] = translated_text
        
        return result
    
    def translate_medical_content(self, content: Dict, target_language: str) -> Dict:
        """Translate medical content including text and image descriptions"""
        translated_content = content.copy()
        
        try:
            # Collect all texts that need translation
            texts_to_translate = []
            text_mapping = []  # Track where each text came from
            
            # Translate main text content
            if 'text' in content and content['text'].strip():
                texts_to_translate.append(content['text'])
                text_mapping.append(('content', 'text'))
            
            # Translate slide titles and content
            if 'slides' in content:
                for slide_idx, slide in enumerate(content['slides']):
                    if 'title' in slide and slide['title'].strip():
                        texts_to_translate.append(slide['title'])
                        text_mapping.append(('slide', slide_idx, 'title'))
                    
                    if 'content' in slide and slide['content'].strip():
                        texts_to_translate.append(slide['content'])
                        text_mapping.append(('slide', slide_idx, 'content'))
                    
                    # Translate image descriptions if present
                    if 'image_description' in slide and slide['image_description'].strip():
                        texts_to_translate.append(slide['image_description'])
                        text_mapping.append(('slide', slide_idx, 'image_description'))
            
            # Translate all texts in batch
            if texts_to_translate:
                print(f"🔄 Translating {len(texts_to_translate)} medical content items...")
                translated_texts = self.translate_batch(texts_to_translate, target_language)
                
                # Map translated texts back to their locations
                for i, (translated_text, mapping) in enumerate(zip(translated_texts, text_mapping)):
                    if mapping[0] == 'content':
                        translated_content['text'] = translated_text
                    elif mapping[0] == 'slide':
                        slide_idx, field = mapping[1], mapping[2]
                        translated_content['slides'][slide_idx][field] = translated_text
            
            return translated_content
            
        except Exception as e:
            raise Exception(f"Medical content translation failed: {e}")
    
    def is_configured(self) -> bool:
        """Check if translation service is properly configured"""
        return bool(self.endpoint and self.key and self.region)
    
    def get_rate_limit_status(self) -> Dict:
        """Get current rate limit status for monitoring"""
        self._reset_rate_limits()
        return {
            'chars_this_minute': self.char_count_this_minute,
            'requests_this_minute': self.request_count_this_minute,
            'max_chars_per_minute': self.max_chars_per_minute,
            'max_requests_per_minute': self.max_requests_per_minute,
            'time_until_reset': 60 - (time.time() - self.last_minute_reset)
        }