import os
import json
from typing import List, Dict, Any
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from config import get_azure_openai_client, AZURE_DEPLOYMENT_NAME

class LLMAgent:
    """Main LLM agent for handling PDF to presentation conversion with detailed medical content"""
    
    def __init__(self):
        # Get Azure configuration from environment
        azure_endpoint = os.getenv("AZURE_OAI_ENDPOINT")
        api_key = os.getenv("AZURE_OAI_KEY")
        deployment_name = os.getenv("AZURE_DEPLOYMENT_NAME")
        
        if not azure_endpoint or not api_key or not deployment_name:
            raise ValueError("Azure OpenAI configuration missing. Please check your .env file.")
        
        self.llm = AzureChatOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            azure_deployment=deployment_name,
            openai_api_version="2024-02-15-preview",
            temperature=0.3  # Lower temperature for more consistent, detailed output
        )
    
    def analyze_pdf_content(self, pdf_content: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze PDF content and extract detailed medical information"""
        print("🔍 DEBUG: Starting PDF content analysis...")
        print(f"🔍 DEBUG: PDF has {len(pdf_content.get('pages', []))} pages")
        
        try:
            # Create detailed analysis prompt
            prompt = self._create_detailed_analysis_prompt(pdf_content)
            print(f"🔍 DEBUG: Analysis prompt length: {len(prompt)} characters")
            
            # Define function schema for structured output
            function_schema = {
                "name": "analyze_medical_content",
                "description": "Analyze medical PDF content and extract structured information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Exact main topic from the PDF text"
                        },
                        "summary": {
                            "type": "string", 
                            "description": "Comprehensive summary using only information from the PDF"
                        },
                        "key_concepts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Exact concepts from PDF (full paragraphs)"
                        },
                        "learning_objectives": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Objectives based on PDF content (detailed)"
                        },
                        "main_sections": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Section titles from PDF"
                        },
                        "important_terms": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Terms with exact definitions from PDF (full explanations)"
                        },
                        "visual_elements": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Descriptions of visual elements from PDF"
                        },
                        "presentation_structure": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Slide titles from PDF"
                        },
                        "detailed_content": {
                            "type": "object",
                            "description": "Detailed content sections from PDF"
                        }
                    },
                    "required": ["topic", "summary", "key_concepts", "main_sections", "important_terms"]
                }
            }
            
            # Get LLM response with function calling
            response = self.llm.invoke(prompt, functions=[function_schema], function_call={"name": "analyze_medical_content"})
            print("🔍 DEBUG: Analysis response received")
            print(f"🔍 DEBUG: Analysis response length: {len(response.content)} characters")
            print(f"🔍 DEBUG: Analysis response first 500 chars: {response.content[:500]}")
            
            # Extract function call arguments
            if hasattr(response, 'additional_kwargs') and 'function_call' in response.additional_kwargs:
                function_call = response.additional_kwargs['function_call']
                if function_call and 'arguments' in function_call:
                    analyzed_content = json.loads(function_call['arguments'])
                    print("🔍 DEBUG: Successfully parsed function call JSON")
                    print(f"🔍 DEBUG: Analysis keys: {list(analyzed_content.keys())}")
                    
                    # Debug key information
                    print(f"🔍 DEBUG: Topic: {analyzed_content.get('topic', 'NO TOPIC')}")
                    print(f"🔍 DEBUG: Key concepts count: {len(analyzed_content.get('key_concepts', []))}")
                    print(f"🔍 DEBUG: Main sections count: {len(analyzed_content.get('main_sections', []))}")
                    
                    return analyzed_content
            
            # Fallback to content parsing if function call failed
            print("🔍 DEBUG: Function call failed, trying content parsing")
            cleaned_response = self._clean_llm_response(response.content)
            print(f"🔍 DEBUG: Cleaned analysis response length: {len(cleaned_response)} characters")
            
            # Parse JSON
            analyzed_content = json.loads(cleaned_response)
            print("🔍 DEBUG: Successfully parsed analysis JSON")
            print(f"🔍 DEBUG: Analysis keys: {list(analyzed_content.keys())}")
            
            # Debug key information
            print(f"🔍 DEBUG: Topic: {analyzed_content.get('topic', 'NO TOPIC')}")
            print(f"🔍 DEBUG: Key concepts count: {len(analyzed_content.get('key_concepts', []))}")
            print(f"🔍 DEBUG: Main sections count: {len(analyzed_content.get('main_sections', []))}")
            
            return analyzed_content
            
        except Exception as e:
            print(f"🔍 DEBUG: Error in analyze_pdf_content: {e}")
            # Fallback to basic analysis
            return self._create_fallback_analysis(pdf_content)
    
    def generate_slides(self, analyzed_content: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate detailed slides from analyzed content"""
        print("🔍 DEBUG: Starting slide generation...")
        
        try:
            # Create detailed slide generation prompt
            prompt = self._create_detailed_slide_generation_prompt(analyzed_content)
            print(f"🔍 DEBUG: Slide generation prompt length: {len(prompt)} characters")
            
            # Define function schema for structured slide output
            function_schema = {
                "name": "generate_medical_slides",
                "description": "Generate structured medical presentation slides from analyzed content",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "slides": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {
                                        "type": "string",
                                        "description": "Exact title from PDF content"
                                    },
                                    "content": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "ENTIRE paragraphs from PDF (dense content)"
                                    },
                                    "slide_type": {
                                        "type": "string",
                                        "enum": ["text", "image", "mixed"],
                                        "description": "Type of slide"
                                    }
                                },
                                "required": ["title", "content", "slide_type"]
                            },
                            "description": "Array of slides with titles and content"
                        }
                    },
                    "required": ["slides"]
                }
            }
            
            # Get LLM response with function calling
            response = self.llm.invoke(prompt, functions=[function_schema], function_call={"name": "generate_medical_slides"})
            print("🔍 DEBUG: Raw LLM response received")
            print(f"🔍 DEBUG: Response length: {len(response.content)} characters")
            print(f"🔍 DEBUG: First 500 chars: {response.content[:500]}")
            
            # Extract function call arguments
            if hasattr(response, 'additional_kwargs') and 'function_call' in response.additional_kwargs:
                function_call = response.additional_kwargs['function_call']
                if function_call and 'arguments' in function_call:
                    slides_data = json.loads(function_call['arguments'])
                    slides = slides_data.get('slides', [])
                    print("🔍 DEBUG: Successfully parsed function call JSON")
                    print(f"🔍 DEBUG: Number of slides: {len(slides)}")
                    
                    # Debug slide information
                    for i, slide in enumerate(slides):
                        print(f"🔍 DEBUG: Slide {i+1}:")
                        print(f"  - Title: '{slide.get('title', 'NO TITLE')}'")
                        print(f"  - Type: {slide.get('slide_type', 'NO TYPE')}")
                        print(f"  - Content paragraphs: {len(slide.get('content', []))}")
                        if slide.get('content'):
                            print(f"  - Content 1: '{slide['content'][0][:100]}...'")
                    
                    print(f"🔍 DEBUG: Generated {len(slides)} text slides")
                    for i, slide in enumerate(slides):
                        print(f"🔍 DEBUG: Text slide {i+1}: '{slide.get('title', 'NO TITLE')}' - {len(slide.get('content', []))} paragraphs")
                    
                    return slides
            
            # Fallback to content parsing if function call failed
            print("🔍 DEBUG: Function call failed, trying content parsing")
            cleaned_response = self._clean_llm_response(response.content)
            print(f"🔍 DEBUG: Cleaned response length: {len(cleaned_response)} characters")
            
            # Parse JSON
            slides_data = json.loads(cleaned_response)
            print("🔍 DEBUG: Successfully parsed JSON")
            print(f"🔍 DEBUG: Number of slides: {len(slides_data.get('slides', []))}")
            
            # Debug slide information
            slides = slides_data.get('slides', [])
            for i, slide in enumerate(slides):
                print(f"🔍 DEBUG: Slide {i+1}:")
                print(f"  - Title: '{slide.get('title', 'NO TITLE')}'")
                print(f"  - Type: {slide.get('slide_type', 'NO TYPE')}")
                print(f"  - Content paragraphs: {len(slide.get('content', []))}")
                if slide.get('content'):
                    print(f"  - Content 1: '{slide['content'][0][:100]}...'")
            
            print(f"🔍 DEBUG: Generated {len(slides)} text slides")
            for i, slide in enumerate(slides):
                print(f"🔍 DEBUG: Text slide {i+1}: '{slide.get('title', 'NO TITLE')}' - {len(slide.get('content', []))} paragraphs")
            
            return slides
            
        except Exception as e:
            print(f"🔍 DEBUG: Error in generate_slides: {e}")
            # Fallback to basic slides
            return self._create_fallback_slides(analyzed_content)
    
    def _create_detailed_analysis_prompt(self, pdf_content: Dict[str, Any]) -> str:
        """Create a prompt for detailed content analysis with specific medical information"""
        
        prompt = f"""
        You are a medical content extractor. Your ONLY job is to extract and organize the EXACT content from the PDF below. DO NOT generate any new information. DO NOT use your medical knowledge. ONLY use what is written in the PDF. Generate all content in English.

        PDF Content:
        """
        
        for page in pdf_content.get('pages', []):
            prompt += f"\n=== PAGE {page['page_number']} ===\n"
            prompt += f"{page['text']}\n"
            prompt += f"Images found: {len(page['images'])}\n"
        
        prompt += f"""
        
        CRITICAL INSTRUCTIONS:
        1. Extract ONLY the exact text and information from the PDF above
        2. DO NOT add any medical knowledge or explanations not in the PDF
        3. Use the exact terminology and language from the PDF
        4. Identify the main topics and sections as they appear in the PDF
        5. Extract specific facts, definitions, and details exactly as written
        6. PRESERVE ENTIRE PARAGRAPHS AND TEXT BLOCKS - DO NOT BREAK THEM UP
        7. Extract DENSE content - use large chunks of text, not short summaries
        8. EXTRACT ALL CONTENT - do not limit yourself to any specific number of items
        9. Be comprehensive - include everything important from the PDF
        10. DO NOT add meta-commentary like "All content extracted from..." or "The chapter discusses..."
        11. DO NOT add generic summaries about what the PDF contains
        12. ONLY extract the actual medical content, definitions, and explanations
        13. Generate all content in English - translation will be handled separately
        
        You MUST respond with ONLY a valid JSON object in the following format:
        {{
            "topic": "Exact main topic from the PDF text",
            "summary": "Comprehensive summary using only information from the PDF",
            "key_concepts": [
                "Exact concept 1 from PDF (full paragraph)",
                "Exact concept 2 from PDF (full paragraph)", 
                "Exact concept 3 from PDF (full paragraph)",
                "Exact concept 4 from PDF (full paragraph)",
                "Exact concept 5 from PDF (full paragraph)",
                "Continue with ALL concepts found in PDF..."
            ],
            "learning_objectives": [
                "Objective 1 based on PDF content (detailed)",
                "Objective 2 based on PDF content (detailed)",
                "Objective 3 based on PDF content (detailed)",
                "Continue with ALL objectives found in PDF..."
            ],
            "main_sections": [
                "Section 1 title from PDF",
                "Section 2 title from PDF",
                "Section 3 title from PDF",
                "Continue with ALL sections found in PDF..."
            ],
            "important_terms": [
                "Term 1 with exact definition from PDF (full explanation)",
                "Term 2 with exact definition from PDF (full explanation)",
                "Term 3 with exact definition from PDF (full explanation)",
                "Continue with ALL terms found in PDF..."
            ],
            "visual_elements": [
                "Description of visual element 1 from PDF",
                "Description of visual element 2 from PDF",
                "Continue with ALL visual elements found in PDF..."
            ],
            "presentation_structure": [
                "Slide 1: [exact title from PDF]",
                "Slide 2: [exact title from PDF]",
                "Slide 3: [exact title from PDF]",
                "Continue with ALL slides needed..."
            ],
            "detailed_content": {{
                "section1": {{
                    "title": "Exact section title from PDF",
                    "key_points": [
                        "Exact point 1 from PDF text (full paragraph)",
                        "Exact point 2 from PDF text (full paragraph)",
                        "Exact point 3 from PDF text (full paragraph)",
                        "Continue with ALL points found in PDF..."
                    ],
                    "mechanisms": [
                        "Exact mechanism description from PDF (full paragraph)",
                        "Exact mechanism description from PDF (full paragraph)",
                        "Continue with ALL mechanisms found in PDF..."
                    ],
                    "clinical_correlations": [
                        "Exact clinical correlation from PDF (full paragraph)",
                        "Exact clinical correlation from PDF (full paragraph)",
                        "Continue with ALL clinical correlations found in PDF..."
                    ]
                }},
                "section2": {{
                    "title": "Exact section title from PDF",
                    "key_points": [
                        "Exact point 1 from PDF text (full paragraph)",
                        "Exact point 2 from PDF text (full paragraph)",
                        "Continue with ALL points found in PDF..."
                    ]
                }}
                "Continue with ALL sections found in PDF..."
            }}
        }}
        
        Remember: ONLY extract from the PDF. DO NOT generate new content. USE ENTIRE PARAGRAPHS AND DENSE CONTENT. EXTRACT ALL CONTENT - NO LIMITATIONS. NO META-COMMENTARY. Generate all content in English - translation will be handled separately.
        
        IMPORTANT: Your response must be ONLY the JSON object above. Do not include any other text, explanations, or markdown formatting.
        """
        
        return prompt
    
    def _create_detailed_slide_generation_prompt(self, analyzed_content: Dict[str, Any]) -> str:
        """Create a prompt for detailed slide generation with specific medical information"""
        
        prompt = f"""
        You are a slide content extractor. Create slides using ONLY the exact content from the PDF analysis below. DO NOT generate new information. DO NOT use bullet points. Use ENTIRE PARAGRAPHS and DENSE TEXT BLOCKS extracted directly from the PDF. Generate all content in English.

        Analysis Summary:
        {json.dumps(analyzed_content, indent=2)}
        
        CRITICAL INSTRUCTIONS:
        1. Extract ONLY exact content from the PDF - DO NOT generate new information
        2. NO bullet points - use ENTIRE PARAGRAPHS of text
        3. Use exact titles and content from the PDF
        4. DO NOT add any medical knowledge not in the PDF
        5. Create slides with specific titles from the PDF content
        6. Use exact language and terminology from the PDF
        7. USE DENSE CONTENT - extract large chunks of text, not short summaries
        8. PRESERVE ENTIRE PARAGRAPHS - do not break them up into small pieces
        9. Each slide should contain SUBSTANTIAL content from the PDF
        10. USE ALL CONTENT - create as many slides as needed to cover everything
        11. Put 3-4 paragraphs per slide - do not cram too much content into one slide
        12. Create a proper title slide with the main topic from the PDF
        13. DO NOT create slides with only one paragraph - ALWAYS use 3-4 paragraphs
        14. DO NOT add meta-commentary like "All content extracted from..." or "The chapter discusses..."
        15. DO NOT add generic summaries about what the PDF contains
        16. ONLY extract the actual medical content, definitions, and explanations
        17. NEVER use phrases like "The chapter discusses..." or "This content covers..." - ONLY use the actual medical content from the PDF
        18. Extract SPECIFIC medical facts, mechanisms, and clinical details - NOT summaries about what the content contains
        19. Generate all content in English - translation will be handled separately
        
        Please create slides in the following JSON format:
        {{
            "slides": [
                {{
                    "title": "Exact medical topic from PDF",
                    "content": [
                        "Brief introduction paragraph about the main topic from PDF"
                    ],
                    "slide_type": "text"
                }},
                {{
                    "title": "Exact title from PDF content",
                    "content": [
                        "Paragraph 1: ENTIRE paragraph from PDF (dense content)",
                        "Paragraph 2: ENTIRE paragraph from PDF (dense content)", 
                        "Paragraph 3: ENTIRE paragraph from PDF (dense content)",
                        "Paragraph 4: ENTIRE paragraph from PDF (dense content)"
                    ],
                    "slide_type": "text"
                }},
                {{
                    "title": "Exact title from PDF content",
                    "content": [
                        "Paragraph 1: ENTIRE paragraph from PDF (dense content)",
                        "Paragraph 2: ENTIRE paragraph from PDF (dense content)", 
                        "Paragraph 3: ENTIRE paragraph from PDF (dense content)"
                    ],
                    "slide_type": "text"
                }}
                "Continue creating slides with ALL content from PDF..."
            ]
        }}
        
        CRITICAL: EVERY TEXT SLIDE MUST HAVE 3-4 PARAGRAPHS. DO NOT CREATE SLIDES WITH ONLY 1 PARAGRAPH. IF YOU HAVE ONLY 1 PARAGRAPH OF CONTENT, FIND MORE CONTENT FROM THE PDF TO FILL THE SLIDE WITH 3-4 PARAGRAPHS.
        
        Create the following slides:
        1. Title slide with exact topic from PDF (NO presenter info) - make this a proper title slide with the main medical topic as the title AND include a brief introduction paragraph
        2. Introduction with DENSE content from PDF (entire paragraphs) - 3-4 paragraphs
        3. Content slides (as many as needed) with DENSE information from PDF:
           - Use exact section titles from PDF
           - Use ENTIRE PARAGRAPHS from PDF (not summaries)
           - Use exact terminology from PDF
           - Each slide should contain 3-4 paragraphs maximum
           - Create multiple slides to cover ALL content
           - EVERY SLIDE MUST HAVE A SPECIFIC TITLE - NO GENERIC TITLES
        4. Summary with DENSE key points from PDF (entire paragraphs) - 3-4 paragraphs
        5. References with exact sources from PDF
        
        IMPORTANT: The title slide should have the main medical topic from the PDF as its title, such as "Acute Inflammation" or "Morphologic Patterns of Inflammation" - NOT generic titles. The title slide should also include a brief introduction paragraph with the main topic description.
        
        CRITICAL: The FIRST SLIDE MUST have:
        - A SPECIFIC medical title from the PDF content (NOT "Medical Presentation" or generic titles)
        - A brief introduction paragraph describing the main topic
        - This slide should contain actual content, not be empty
        
        Each slide should have:
        - SPECIFIC title from PDF content (NOT generic titles like "Introduction" or "Content")
        - ENTIRE PARAGRAPHS of text (NO bullet points) with DENSE content from PDF
        - Specific medical terminology exactly as written in PDF
        - SUBSTANTIAL content - not short summaries
        - 3-4 paragraphs maximum per slide
        - NO META-COMMENTARY or generic summaries
        - ALL CONTENT IN ENGLISH (translation will be handled separately)
        
        Remember: ONLY extract from the PDF. NO bullet points. NO generated content. USE DENSE, ENTIRE PARAGRAPHS. CREATE AS MANY SLIDES AS NEEDED TO COVER ALL CONTENT. ALL CONTENT IN ENGLISH.
        """
        
        return prompt
    
    def _create_detailed_fallback_analysis(self, pdf_content: Dict[str, Any]) -> Dict[str, Any]:
        """Create a detailed fallback analysis if JSON parsing fails"""
        return {
            "topic": "Detailed Medical Content Analysis",
            "summary": "Comprehensive analysis of medical PDF content with specific details",
            "key_concepts": [
                "Specific medical concept 1 with detailed explanation",
                "Specific medical concept 2 with detailed explanation",
                "Specific medical concept 3 with detailed explanation"
            ],
            "learning_objectives": [
                "Understand specific medical mechanism 1",
                "Identify specific clinical feature 2",
                "Apply specific diagnostic criteria 3"
            ],
            "main_sections": [
                "Detailed section 1 with specific focus",
                "Detailed section 2 with specific focus",
                "Detailed section 3 with specific focus"
            ],
            "important_terms": [
                "Specific medical term 1 with definition",
                "Specific medical term 2 with definition",
                "Specific medical term 3 with definition"
            ],
            "visual_elements": [
                "Specific diagram 1 with description",
                "Specific image 2 with description"
            ],
            "presentation_structure": [
                "Detailed slide 1 with specific content",
                "Detailed slide 2 with specific content",
                "Detailed slide 3 with specific content"
            ],
            "detailed_content": {
                "section1": {
                    "title": "Specific Medical Section",
                    "key_points": [
                        "Detailed medical point 1",
                        "Detailed medical point 2",
                        "Detailed medical point 3"
                    ],
                    "mechanisms": [
                        "Specific mechanism 1",
                        "Specific mechanism 2"
                    ],
                    "clinical_correlations": [
                        "Specific clinical correlation 1",
                        "Specific clinical correlation 2"
                    ]
                }
            }
        }
    
    def _create_detailed_fallback_slides(self, analyzed_content: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create detailed fallback slides if JSON parsing fails"""
        return [{
            "title": "Detailed Medical Content",
            "content": [
                "Specific medical information extracted from analysis",
                "Detailed mechanism or process explanation",
                "Clinical correlation or diagnostic feature"
            ],
            "slide_type": "text"
        }]

    def _create_fallback_analysis(self, pdf_content: Dict[str, Any]) -> Dict[str, Any]:
        """Create a fallback analysis when LLM fails"""
        print("🔍 DEBUG: Using fallback analysis")
        
        # Extract basic information from PDF
        pages = pdf_content.get('pages', [])
        all_text = ""
        for page in pages:
            all_text += page.get('text', '') + "\n"
        
        # Create basic analysis structure
        return {
            "topic": "Medical Content Analysis",
            "summary": "Content extracted from medical PDF document",
            "key_concepts": [
                "Medical content analysis",
                "PDF document processing",
                "Content extraction"
            ],
            "learning_objectives": [
                "Understand the extracted medical content",
                "Review key medical concepts",
                "Analyze medical information"
            ],
            "main_sections": [
                "Introduction",
                "Main Content",
                "Summary"
            ],
            "important_terms": [
                "Medical terminology",
                "Clinical concepts",
                "Pathological processes"
            ],
            "visual_elements": [
                "Medical images and figures",
                "Clinical photographs",
                "Pathological specimens"
            ],
            "presentation_structure": [
                "Slide 1: Introduction",
                "Slide 2: Main Content",
                "Slide 3: Summary"
            ],
            "detailed_content": {
                "section1": {
                    "title": "Introduction",
                    "key_points": [
                        "Medical content analysis and presentation",
                        "Extraction of key medical concepts",
                        "Review of important medical information"
                    ]
                }
            }
        }
    
    def _create_fallback_slides(self, analyzed_content: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create fallback slides when LLM generation fails"""
        print("🔍 DEBUG: Using fallback slides")
        
        return [
            {
                "title": "Medical Content Analysis",
                "content": [
                    "This presentation contains medical content extracted from the provided PDF document.",
                    "The content includes key medical concepts, clinical information, and important terminology.",
                    "Please review the extracted information for accuracy and completeness."
                ],
                "slide_type": "text"
            },
            {
                "title": "Key Medical Concepts",
                "content": [
                    "Medical terminology and definitions from the source document.",
                    "Clinical correlations and pathological processes.",
                    "Important medical mechanisms and pathways."
                ],
                "slide_type": "text"
            }
        ]

    def _clean_llm_response(self, response_text: str) -> str:
        """Clean LLM response by removing markdown code blocks"""
        content = response_text.strip()
        
        # Remove markdown code blocks if present
        if content.startswith('```json'):
            content = content[7:]  # Remove ```json
        if content.startswith('```'):
            content = content[3:]  # Remove ```
        if content.endswith('```'):
            content = content[:-3]  # Remove ```
        
        return content.strip()
