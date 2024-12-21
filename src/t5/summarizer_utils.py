import json
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from loguru import logger
from transformers import (
    AutoTokenizer, 
    AutoModelForSeq2SeqLM, 
    AutoModelForSequenceClassification,
    pipeline
)

class MessageSummarizer:
    def __init__(self):
        logger.info("Initializing summarization models...")
        
        # Load conversation summarization model
        self.conv_tokenizer = AutoTokenizer.from_pretrained("philschmid/bart-large-cnn-samsum")
        self.conv_model = AutoModelForSeq2SeqLM.from_pretrained("philschmid/bart-large-cnn-samsum")
        
        # Load personality analysis model
        self.personality_tokenizer = AutoTokenizer.from_pretrained("facebook/bart-large-mnli")
        self.personality_model = AutoModelForSequenceClassification.from_pretrained("facebook/bart-large-mnli")
        
        # Create personality analysis pipeline
        self.personality_pipeline = pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli",
            tokenizer="facebook/bart-large-mnli"
        )
        
        logger.info("Models loaded successfully")

    def generate_weekly_summary(self, messages: List[Dict]) -> str:
        """Generate a summary of conversations for a week"""
        try:
            # Format messages for summarization
            conversation = self._format_messages_for_summary(messages)
            
            # Generate summary
            inputs = self.conv_tokenizer(
                conversation,
                max_length=1024,
                truncation=True,
                padding="longest",
                return_tensors="pt"
            )
            
            summary_ids = self.conv_model.generate(
                inputs["input_ids"],
                max_length=500,  # 500 words as requested
                min_length=200,
                num_beams=4,
                length_penalty=2.0,
                early_stopping=True
            )
            
            summary = self.conv_tokenizer.decode(summary_ids[0], skip_special_tokens=True)
            return summary
            
        except Exception as e:
            logger.error(f"Error generating weekly summary: {e}")
            return ""

    def analyze_personality(self, messages: List[Dict]) -> Dict:
        """Analyze personality traits and relationship dynamics"""
        try:
            # Combine messages for analysis
            text = " ".join([msg["text"] for msg in messages])
            
            # Personality traits to analyze
            traits = [
                "friendly", "professional", "formal", "casual", "emotional",
                "analytical", "supportive", "demanding", "humorous", "serious"
            ]
            
            # Relationship contexts to analyze
            contexts = [
                "close friend", "family member", "professional contact",
                "acquaintance", "romantic interest", "mentor/mentee"
            ]
            
            # Analyze personality traits
            trait_results = self.personality_pipeline(
                text,
                candidate_labels=traits,
                multi_label=True
            )
            
            # Analyze relationship context
            context_results = self.personality_pipeline(
                text,
                candidate_labels=contexts,
                multi_label=False
            )
            
            # Extract common topics
            topics = self._extract_common_topics(messages)
            
            return {
                "personality_traits": {
                    label: score 
                    for label, score in zip(trait_results["labels"], trait_results["scores"])
                    if score > 0.5  # Only include confident predictions
                },
                "relationship_context": {
                    context_results["labels"][0]: context_results["scores"][0]
                },
                "common_topics": topics
            }
            
        except Exception as e:
            logger.error(f"Error analyzing personality: {e}")
            return {
                "personality_traits": {},
                "relationship_context": {"unknown": 0.0},
                "common_topics": {}
            }

    def _format_messages_for_summary(self, messages: List[Dict]) -> str:
        """Format messages for the summarization model"""
        formatted = []
        for msg in messages:
            sender = "Me" if msg["is_from_me"] else msg["sender"]
            formatted.append(f"{sender}: {msg['text']}")
        return "\n".join(formatted)

    def _format_messages_for_analysis(self, messages: List[Dict]) -> str:
        """Format messages for personality analysis"""
        # Combine all messages with context
        return " ".join([msg["text"] for msg in messages])

    def _extract_common_topics(self, messages: List[Dict]) -> Dict[str, float]:
        """Extract and score common conversation topics"""
        try:
            # Common topics to look for
            topics = [
                "work", "family", "hobbies", "travel", "food",
                "entertainment", "sports", "technology", "education",
                "personal life", "future plans", "shared memories"
            ]
            
            # Combine messages
            text = self._format_messages_for_analysis(messages)
            
            # Analyze topics
            results = self.personality_pipeline(
                text,
                candidate_labels=topics,
                multi_label=True
            )
            
            return {
                label: score 
                for label, score in zip(results["labels"], results["scores"])
                if score > 0.3  # Include topics with reasonable confidence
            }
            
        except Exception as e:
            logger.error(f"Error extracting topics: {e}")
            return {}

    def generate_identity_summary(self, messages: List[Dict], previous_summary: str = None) -> Tuple[str, Dict]:
        """Generate or update identity summary with confidence scores"""
        try:
            # Analyze personality and get confidence score
            analysis = self.analyze_personality(messages)
            
            # Create summary prompt with previous context if available
            prompt = (
                "Based on their messages, this person is "
                f"{', '.join(analysis['personality_traits'].keys())}. "
                f"They appear to be a {list(analysis['relationship_context'].keys())[0]}. "
                f"Common topics of discussion include {', '.join(analysis['common_topics'].keys())}."
            )
            
            if previous_summary:
                prompt = f"Previous summary: {previous_summary}\nNew analysis: {prompt}"
            
            # Generate narrative summary
            inputs = self.conv_tokenizer(
                prompt,
                max_length=1024,
                truncation=True,
                return_tensors="pt"
            )
            
            summary_ids = self.conv_model.generate(
                inputs["input_ids"],
                max_length=300,
                min_length=100,
                num_beams=4,
                length_penalty=2.0,
                early_stopping=True
            )
            
            summary = self.conv_tokenizer.decode(summary_ids[0], skip_special_tokens=True)
            
            # Add confidence scores to analysis
            analysis["personality_confidence"] = sum(analysis["personality_traits"].values()) / len(analysis["personality_traits"])
            analysis["relationship_confidence"] = list(analysis["relationship_context"].values())[0]
            analysis["topics_confidence"] = sum(analysis["common_topics"].values()) / len(analysis["common_topics"])
            
            return summary, analysis
            
        except Exception as e:
            logger.error(f"Error generating identity summary: {e}")
            return "", {}