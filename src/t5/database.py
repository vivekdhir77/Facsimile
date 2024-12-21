import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from loguru import logger
from typing import List, Dict, Tuple
import glob

# Set up logging
logger.add("imessage_summarizer.log", rotation="1 week")

class MessageDatabase:
    def __init__(self):
        # Create database in user's application support directory
        app_dir = Path.home() / "Library" / "Application Support" / "iMessage-Summarizer"
        app_dir.mkdir(parents=True, exist_ok=True)
        
        self.db_path = app_dir / "messages.db"
        self.conn = None
        self.setup_database()

    def setup_database(self):
        """Initialize database with required tables"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            cursor = self.conn.cursor()

            # Create tables
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY,
                    identifier TEXT UNIQUE,
                    display_name TEXT,
                    first_seen_date DATETIME,
                    last_updated DATETIME
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    contact_id INTEGER,
                    message_date DATETIME,
                    text TEXT,
                    is_from_me BOOLEAN,
                    chat_id TEXT,
                    is_group_chat BOOLEAN,
                    processed_in_summary BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id)
                );

                CREATE TABLE IF NOT EXISTS weekly_conversation_summaries (
                    id INTEGER PRIMARY KEY,
                    contact_id INTEGER,
                    week_start_date DATE,
                    week_end_date DATE,
                    summary_text TEXT,
                    created_at DATETIME,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id)
                );

                CREATE TABLE IF NOT EXISTS identity_summaries (
                    id INTEGER PRIMARY KEY,
                    contact_id INTEGER,
                    summary_text TEXT,
                    created_at DATETIME,
                    personality_traits TEXT,
                    relationship_context TEXT,
                    common_topics TEXT,
                    confidence_scores TEXT,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id)
                );

                CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(message_date);
                CREATE INDEX IF NOT EXISTS idx_messages_contact ON messages(contact_id);
                CREATE INDEX IF NOT EXISTS idx_messages_processed ON messages(processed_in_summary);
            """)

            self.conn.commit()
            logger.info("Database initialized successfully")

        except Exception as e:
            logger.error(f"Error setting up database: {e}")
            raise

    def get_contact_name(self, identifier: str) -> str:
        """Get contact name from macOS Contacts database with retry"""
        try:
            # First try AddressBook path
            contacts_path = os.path.expanduser("~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb")
            contacts_db = glob.glob(contacts_path)
            
            if not contacts_db:
                # Try alternate Contacts path
                contacts_path = os.path.expanduser("~/Library/Application Support/Contacts/Sources/*/AddressBook-v22.abcddb")
                contacts_db = glob.glob(contacts_path)
                
            if not contacts_db:
                logger.warning(f"Could not find Contacts database for {identifier}")
                return identifier
                
            conn = sqlite3.connect(contacts_db[0])
            cursor = conn.cursor()
            
            # Try both phone and email queries
            queries = [
                """
                SELECT 
                    ZABCDPHONENUMBER.ZFULLNUMBER,
                    ZABCDRECORD.ZFIRSTNAME,
                    ZABCDRECORD.ZLASTNAME,
                    ZABCDRECORD.ZORGANIZATION
                FROM ZABCDPHONENUMBER 
                JOIN ZABCDRECORD ON ZABCDPHONENUMBER.ZOWNER = ZABCDRECORD.Z_PK
                WHERE ZABCDPHONENUMBER.ZFULLNUMBER IS NOT NULL
                """,
                """
                SELECT 
                    ZABCDEMAILADDRESS.ZADDRESS,
                    ZABCDRECORD.ZFIRSTNAME,
                    ZABCDRECORD.ZLASTNAME,
                    ZABCDRECORD.ZORGANIZATION
                FROM ZABCDEMAILADDRESS 
                JOIN ZABCDRECORD ON ZABCDEMAILADDRESS.ZOWNER = ZABCDRECORD.Z_PK
                WHERE ZABCDEMAILADDRESS.ZADDRESS IS NOT NULL
                """
            ]
            
            for query in queries:
                cursor.execute(query)
                for contact_id, first, last, org in cursor.fetchall():
                    if contact_id:
                        if query.find("ZFULLNUMBER") >= 0:
                            # Format phone number
                            formatted_id = ''.join(c for c in contact_id if c.isdigit())
                            if len(formatted_id) == 10:
                                formatted_id = '+1' + formatted_id
                            elif len(formatted_id) > 10:
                                formatted_id = '+' + formatted_id
                        else:
                            formatted_id = contact_id
                            
                        if formatted_id == identifier:
                            name = ' '.join(filter(None, [first, last]))
                            if not name and org:
                                name = org
                            return name.strip() if name else identifier
            
            conn.close()
            return identifier
                
        except Exception as e:
            logger.error(f"Error getting contact name: {e}")
            return identifier

    def store_message(self, contact_identifier, message_date, text, is_from_me, chat_id, is_group_chat):
        """Store a single message with contact name resolution"""
        try:
            cursor = self.conn.cursor()
            
            # Get contact name
            display_name = self.get_contact_name(contact_identifier)
            
            # First, ensure contact exists
            cursor.execute("""
                INSERT OR IGNORE INTO contacts (identifier, display_name, first_seen_date, last_updated)
                VALUES (?, ?, ?, ?)
            """, (contact_identifier, display_name, datetime.now(), datetime.now()))
            
            # Get contact_id
            cursor.execute("SELECT id FROM contacts WHERE identifier = ?", (contact_identifier,))
            contact_id = cursor.fetchone()[0]
            
            # Store message
            cursor.execute("""
                INSERT OR IGNORE INTO messages 
                (contact_id, message_date, text, is_from_me, chat_id, is_group_chat)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (contact_id, message_date, text, is_from_me, chat_id, is_group_chat))
            
            self.conn.commit()
            
        except Exception as e:
            logger.error(f"Error storing message: {e}")
            self.conn.rollback()

    def get_unprocessed_messages(self, contact_id=None):
        """Get messages that haven't been included in summaries yet"""
        try:
            cursor = self.conn.cursor()
            if contact_id:
                cursor.execute("""
                    SELECT * FROM messages 
                    WHERE contact_id = ? AND processed_in_summary = FALSE
                    ORDER BY message_date
                """, (contact_id,))
            else:
                cursor.execute("""
                    SELECT * FROM messages 
                    WHERE processed_in_summary = FALSE
                    ORDER BY message_date
                """)
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error fetching unprocessed messages: {e}")
            return []

    def store_weekly_summary(self, contact_id: int, week_start: datetime, week_end: datetime, summary_text: str):
        """Store a weekly conversation summary"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO weekly_conversation_summaries 
                (contact_id, week_start_date, week_end_date, summary_text, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (contact_id, week_start, week_end, summary_text, datetime.now()))
            self.conn.commit()
            logger.info(f"Stored weekly summary for contact {contact_id}")
        except Exception as e:
            logger.error(f"Error storing weekly summary: {e}")
            self.conn.rollback()

    def store_identity_summary(self, contact_id, summary_text, personality_traits, 
                             relationship_context, common_topics, confidence_scores):
        """Store an identity summary"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO identity_summaries 
                (contact_id, summary_text, created_at, personality_traits, 
                 relationship_context, common_topics, confidence_scores)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                contact_id, 
                summary_text, 
                datetime.now(),
                json.dumps(personality_traits),
                json.dumps(relationship_context),
                json.dumps(common_topics),
                json.dumps(confidence_scores)
            ))
            self.conn.commit()
            logger.info(f"Stored identity summary for contact {contact_id}")
        except Exception as e:
            logger.error(f"Error storing identity summary: {e}")
            self.conn.rollback()

    def mark_messages_processed(self, message_ids):
        """Mark messages as processed in summaries"""
        try:
            cursor = self.conn.cursor()
            cursor.executemany("""
                UPDATE messages 
                SET processed_in_summary = TRUE 
                WHERE id = ?
            """, [(id,) for id in message_ids])
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error marking messages as processed: {e}")
            self.conn.rollback()

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close() 

    def get_last_processed_date(self) -> datetime:
        """Get the date of the last processed message"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT MAX(message_date) 
                FROM messages
            """)
            result = cursor.fetchone()[0]
            return datetime.strptime(result, "%Y-%m-%d %H:%M:%S") if result else None
        except Exception as e:
            logger.error(f"Error getting last processed date: {e}")
            return None

    def get_all_contacts(self) -> List[Dict]:
        """Get all contacts from database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, identifier, display_name 
                FROM contacts
            """)
            return [
                {"id": row[0], "identifier": row[1], "display_name": row[2]}
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.error(f"Error getting contacts: {e}")
            return []

    def get_messages_for_timeframe(self, contact_id: int, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Get messages for a specific timeframe"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT m.id, m.message_date, m.text, m.is_from_me, m.chat_id, m.is_group_chat,
                       c.display_name as sender_name
                FROM messages m
                JOIN contacts c ON m.contact_id = c.id
                WHERE m.contact_id = ?
                AND m.message_date BETWEEN ? AND ?
                ORDER BY m.message_date
            """, (contact_id, start_date, end_date))
            
            return [
                {
                    "id": row[0],
                    "date": datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S"),
                    "text": row[2],
                    "is_from_me": bool(row[3]),
                    "chat_id": row[4],
                    "is_group_chat": bool(row[5]),
                    "sender": "Me" if bool(row[3]) else row[6]
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.error(f"Error getting messages for timeframe: {e}")
            return []

    def get_all_messages_for_contact(self, contact_id: int) -> List[Dict]:
        """Get all messages for a contact"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT m.id, m.message_date, m.text, m.is_from_me, m.chat_id, m.is_group_chat,
                       c.display_name as sender_name
                FROM messages m
                JOIN contacts c ON m.contact_id = c.id
                WHERE m.contact_id = ?
                ORDER BY m.message_date
            """, (contact_id,))
            
            return [
                {
                    "id": row[0],
                    "date": datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S"),
                    "text": row[2],
                    "is_from_me": bool(row[3]),
                    "chat_id": row[4],
                    "is_group_chat": bool(row[5]),
                    "sender": "Me" if bool(row[3]) else row[6]
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.error(f"Error getting all messages for contact: {e}")
            return []

    def get_latest_identity_summary(self, contact_id: int) -> Dict:
        """Get the most recent identity summary for a contact"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, summary_text, personality_traits, relationship_context, 
                       common_topics, created_at
                FROM identity_summaries
                WHERE contact_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (contact_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "summary_text": row[1],
                    "personality_traits": json.loads(row[2]),
                    "relationship_context": json.loads(row[3]),
                    "common_topics": json.loads(row[4]),
                    "created_at": datetime.strptime(row[5], "%Y-%m-%d %H:%M:%S")
                }
            return None
        except Exception as e:
            logger.error(f"Error getting latest identity summary: {e}")
            return None

    def fetch_messages(self, start_date: datetime = None) -> Tuple[str, List[Dict]]:
        """Fetch messages from iMessage database with optional start date filter"""
        try:
            messages_db = os.path.expanduser("~/Library/Messages/chat.db")
            if not os.path.exists(messages_db):
                logger.error("Messages database not found")
                return "Error: Messages database not found", []

            imessage_conn = sqlite3.connect(messages_db)
            cursor = imessage_conn.cursor()
            
            # Base query
            query = """
                SELECT 
                    datetime(message.date/1000000000 + strftime("%s", "2001-01-01"), "unixepoch", "localtime") as message_date,
                    message.text,
                    CASE 
                        WHEN message.is_from_me = 1 THEN 'Me'
                        ELSE handle.id
                    END as sender,
                    message.is_from_me,
                    chat.chat_identifier,
                    chat.display_name,
                    chat.ROWID as chat_id
                FROM message 
                JOIN chat_message_join ON message.ROWID = chat_message_join.message_id
                JOIN chat ON chat_message_join.chat_id = chat.ROWID
                LEFT JOIN handle ON message.handle_id = handle.ROWID
                WHERE message.text IS NOT NULL
                AND length(message.text) > 0
            """
            
            # Add start_date filter if provided
            params = []
            if start_date:
                query += " AND datetime(message.date/1000000000 + strftime('%s', '2001-01-01'), 'unixepoch', 'localtime') > ?"
                params.append(start_date.strftime("%Y-%m-%d %H:%M:%S"))

            query += " ORDER BY chat.ROWID, message_date ASC"
            
            cursor.execute(query, params)
            messages = cursor.fetchall()
            
            # Process messages
            processed_messages = []
            conversation_text = "Multiple conversations:\n\n"
            
            for msg in messages:
                try:
                    msg_date = datetime.strptime(msg[0], "%Y-%m-%d %H:%M:%S")
                    text = str(msg[1]).strip()
                    sender = msg[2]
                    is_from_me = bool(msg[3])
                    chat_id = msg[4]
                    chat_name = msg[5] if msg[5] else chat_id
                    
                    # Skip automated messages and reactions
                    if any(skip_text in text.lower() for skip_text in [
                        'liked', 'emphasized', 'sent you $', 'usps', 'tracking',
                        'duolingo', 'bofa:', 'u.s. post'
                    ]) or len(text.split()) < 2:
                        continue
                    
                    processed_messages.append({
                        "date": msg_date,
                        "text": text,
                        "sender": sender,
                        "is_from_me": is_from_me,
                        "chat_id": chat_id,
                        "is_group_chat": bool(chat_name != chat_id)
                    })
                    
                    conversation_text += f"Chat with {chat_name}:\n"
                    conversation_text += f"{sender}: {text}\n"
                    
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    continue
            
            imessage_conn.close()
            
            if not processed_messages:
                return "No messages found in the specified time period.", []
            
            logger.info(f"Fetched {len(processed_messages)} messages")
            return conversation_text, processed_messages
            
        except Exception as e:
            logger.error(f"Error fetching messages: {e}")
            return f"Error fetching messages: {e}", []

    def optimize_database(self):
        """Optimize database storage and remove duplicates"""
        try:
            cursor = self.conn.cursor()
            
            # Remove duplicate messages
            cursor.execute("""
                DELETE FROM messages 
                WHERE id NOT IN (
                    SELECT MIN(id)
                    FROM messages
                    GROUP BY contact_id, message_date, text
                )
            """)
            self.conn.commit()
            
            # Close connection before VACUUM
            self.conn.close()
            
            # Reopen connection for VACUUM
            temp_conn = sqlite3.connect(self.db_path)
            temp_conn.execute("VACUUM")
            temp_conn.close()
            
            # Reopen main connection
            self.conn = sqlite3.connect(self.db_path)
            logger.info("Database optimized successfully")
            
        except Exception as e:
            logger.error(f"Error optimizing database: {e}")

    def get_earliest_message_date(self) -> datetime:
        """Get the date of the earliest message in the database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT MIN(message_date)
                FROM messages
            """)
            result = cursor.fetchone()[0]
            return datetime.strptime(result, "%Y-%m-%d %H:%M:%S") if result else None
        except Exception as e:
            logger.error(f"Error getting earliest message date: {e}")
            return None
  