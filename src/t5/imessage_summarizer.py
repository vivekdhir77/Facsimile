# pyright: ignore-errors

import os
import warnings
from datetime import datetime, timedelta
from loguru import logger
from database import MessageDatabase
from summarizer_utils import MessageSummarizer
import json

warnings.filterwarnings("ignore")

class MessageProcessor:
    def __init__(self):
        logger.info("Initializing Message Processor")
        self.db = MessageDatabase()
        self.summarizer = MessageSummarizer()

    def process_messages(self):
        """Main processing function"""
        try:
            logger.info("Starting message processing")

            # Fetch and store new messages
            new_messages = self._fetch_new_messages()
            if not new_messages:
                logger.info("No new messages to process")
                return

            # Process messages by contact
            self._process_messages_by_contact()

            # Generate weekly summaries
            self._generate_weekly_summaries()

            # Update identity summaries
            self._update_identity_summaries()

            # Optimize database
            self.db.optimize_database()

            logger.info("Message processing completed")

        except Exception as e:
            logger.error(f"Error in message processing: {e}")
        finally:
            self.db.close()

    def _fetch_new_messages(self):
        """Fetch and store new messages from iMessage"""
        try:
            messages_db = os.path.expanduser("~/Library/Messages/chat.db")
            if not os.path.exists(messages_db):
                logger.error("Messages database not found")
                return False

            # Get last processed message date from our database
            last_processed = self.db.get_last_processed_date()

            # Fetch new messages from iMessage
            conversation, messages = self.db.fetch_messages(
                start_date=last_processed if last_processed else None
            )

            if messages:
                # Store new messages in our database
                for msg in messages:
                    self.db.store_message(
                        contact_identifier=msg["sender"],
                        message_date=msg["date"],
                        text=msg["text"],
                        is_from_me=msg["is_from_me"],
                        chat_id=msg["chat_id"],
                        is_group_chat=msg["is_group_chat"]
                    )
                logger.info(f"Stored {len(messages)} new messages")
                return True

            return False

        except Exception as e:
            logger.error(f"Error fetching new messages: {e}")
            return False

    def _process_messages_by_contact(self):
        """Process messages grouped by contact"""
        try:
            contacts = self.db.get_all_contacts()

            for contact in contacts:
                unprocessed = self.db.get_unprocessed_messages(contact["id"])
                if unprocessed:
                    logger.info(f"Processing messages for contact: {contact['display_name']}")

                    # Convert tuple to dict for processing
                    messages = [
                        {
                            "id": msg[0],
                            "message_date": msg[2],
                            "text": msg[3],
                            "is_from_me": msg[4],
                            "chat_id": msg[5]
                        }
                        for msg in unprocessed
                    ]

                    # Mark messages as processed
                    self.db.mark_messages_processed([msg["id"] for msg in messages])

        except Exception as e:
            logger.error(f"Error processing messages by contact: {e}")

    def _generate_weekly_summaries(self):
        """Generate weekly summaries for each contact"""
        try:
            contacts = self.db.get_all_contacts()
            
            # Get earliest message date
            earliest_date = self.db.get_earliest_message_date()
            if not earliest_date:
                logger.warning("No messages found for weekly summaries")
                return
            
            logger.info(f"Generating weekly summaries from {earliest_date} to now")
            
            # Generate summaries week by week from earliest date
            current_date = datetime.now().date()
            week_start = earliest_date.date() - timedelta(days=earliest_date.weekday())
            
            while week_start <= current_date:
                week_end = week_start + timedelta(days=7)
                logger.info(f"Processing week: {week_start} to {week_end}")
                
                for contact in contacts:
                    messages = self.db.get_messages_for_timeframe(
                        contact["id"],
                        start_date=week_start,
                        end_date=week_end
                    )
                    
                    if messages:
                        logger.info(f"Found {len(messages)} messages for {contact['display_name']} in week {week_start}")
                        summary = self.summarizer.generate_weekly_summary(messages)
                        
                        if summary:
                            logger.info(f"Generated summary for {contact['display_name']}: {summary[:100]}...")
                            self.db.store_weekly_summary(
                                contact["id"],
                                week_start,
                                week_end,
                                summary
                            )
                        else:
                            logger.warning(f"No summary generated for {contact['display_name']}")
                            
                week_start = week_end

        except Exception as e:
            logger.error(f"Error generating weekly summaries: {e}")

    def _update_identity_summaries(self):
        """Update identity summaries for each contact"""
        try:
            contacts = self.db.get_all_contacts()

            for contact in contacts:
                messages = self.db.get_all_messages_for_contact(contact["id"])

                if messages:
                    logger.info(f"Updating identity summary for: {contact['display_name']}")

                    previous_summary = self.db.get_latest_identity_summary(contact["id"])

                    summary, analysis = self.summarizer.generate_identity_summary(
                        messages,
                        previous_summary["summary_text"] if previous_summary else None
                    )

                    if summary and analysis:
                        confidence_scores = {
                            "personality": analysis.get("personality_confidence", 0.0),
                            "relationship": analysis.get("relationship_confidence", 0.0),
                            "topics": analysis.get("topics_confidence", 0.0)
                        }

                        self.db.store_identity_summary(
                            contact["id"],
                            summary,
                            analysis["personality_traits"],
                            analysis["relationship_context"],
                            analysis["common_topics"],
                            json.dumps(confidence_scores)
                        )

        except Exception as e:
            logger.error(f"Error updating identity summaries: {e}")

def main():
    processor = MessageProcessor()
    processor.process_messages()

if __name__ == "__main__":
    main()
