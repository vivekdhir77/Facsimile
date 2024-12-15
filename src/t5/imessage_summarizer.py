import warnings
import sys
import os
import sqlite3
import glob
from datetime import datetime, timedelta
warnings.filterwarnings("ignore")  

from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

def get_contact_name(identifier, contact_names=None):
    """Convert phone numbers/identifiers to names"""
    if contact_names is None:
        contact_names = {}
    return contact_names.get(identifier, identifier)

def load_model(model_name="philschmid/bart-large-cnn-samsum"):
    """Load BART model and tokenizer"""
    try:
        print("\nLoading summarization model... (this may take a moment on first run)")
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        print("Model loaded successfully!")
        return model, tokenizer
    except Exception as e:
        print(f"Error loading model: {e}")
        sys.exit(1)

def get_contact_names():
    """Get contact names from macOS Contacts database"""
    contact_names = {}
    try:
        possible_paths = [
            "~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb",
            "~/Library/Application Support/AddressBook/Sources/*/AddressBook.adressbook",
            "~/Library/Application Support/Contacts/Sources/*/AddressBook-v22.abcddb",
            "~/Library/Containers/com.apple.ContactsAgent/Data/Library/Application Support/Contacts/Sources/*/AddressBook-v22.abcddb"
        ]
        
        contacts_path = None
        for path in possible_paths:
            expanded_path = os.path.expanduser(path)
            matches = glob.glob(expanded_path)
            if matches:
                contacts_path = matches[0]
                break
        
        if not contacts_path:
            print("Warning: Could not find Contacts database")
            return contact_names

        conn = sqlite3.connect(contacts_path)
        cursor = conn.cursor()

        query = """
            SELECT 
                ZABCDPHONENUMBER.ZFULLNUMBER,
                ZABCDRECORD.ZFIRSTNAME,
                ZABCDRECORD.ZLASTNAME,
                ZABCDRECORD.ZORGANIZATION
            FROM ZABCDPHONENUMBER 
            JOIN ZABCDRECORD ON ZABCDPHONENUMBER.ZOWNER = ZABCDRECORD.Z_PK
            WHERE ZABCDPHONENUMBER.ZFULLNUMBER IS NOT NULL
        """
        
        cursor.execute(query)
        
        for number, first, last, org in cursor.fetchall():
            if number:
                formatted_number = ''.join(c for c in number if c.isdigit())
                if len(formatted_number) == 10:
                    formatted_number = '+1' + formatted_number
                elif len(formatted_number) > 10:
                    formatted_number = '+' + formatted_number
                
                name = ' '.join(filter(None, [first, last]))
                if not name and org:
                    name = org
                
                if name:
                    contact_names[formatted_number] = name.strip()

        conn.close()
    except Exception as e:
        print(f"Warning: Error accessing contacts: {e}")
    
    return contact_names

def fetch_messages(days_back=7, contact=None):
    """Fetch messages from iMessage"""
    try:
        messages_db = os.path.expanduser("~/Library/Messages/chat.db")
        if not os.path.exists(messages_db):
            print(f"Messages database not found at: {messages_db}")
            return "Error: Messages database not found. Make sure you've granted Full Disk Access to Terminal.", []

        contact_names = get_contact_names()
        
        conn = sqlite3.connect(messages_db)
        cursor = conn.cursor()
        
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
                chat.display_name
            FROM message 
            JOIN chat_message_join ON message.ROWID = chat_message_join.message_id
            JOIN chat ON chat_message_join.chat_id = chat.ROWID
            LEFT JOIN handle ON message.handle_id = handle.ROWID
            WHERE message.date > 0
            AND datetime(message.date/1000000000 + strftime("%s", "2001-01-01"), "unixepoch", "localtime") > datetime('now', ?)
            AND message.text IS NOT NULL
            AND length(message.text) > 0
            ORDER BY chat.ROWID, message_date ASC
        """
        
        days_back_str = f"-{days_back} days"
        cursor.execute(query, (days_back_str,))
        messages = cursor.fetchall()
        
        chat_messages = {}
        for msg in messages:
            try:
                if not msg[0] or not msg[1]:
                    continue
                
                msg_date = datetime.strptime(msg[0], "%Y-%m-%d %H:%M:%S")
                text = str(msg[1]).strip()
                sender = "Me" if msg[3] == 1 else get_contact_name(str(msg[2]), contact_names)
                chat_id = msg[4]
                chat_name = msg[5] if msg[5] else get_contact_name(chat_id, contact_names)
                
                # Skip automated messages and reactions
                if any(skip_text in text.lower() for skip_text in [
                    'liked', 'emphasized', 'sent you $', 'usps', 'tracking',
                    'duolingo', 'bofa:', 'u.s. post'
                ]) or len(text.split()) < 2:
                    continue
                
                if contact is None or contact.lower() in sender.lower():
                    if chat_id not in chat_messages:
                        chat_messages[chat_id] = {
                            'name': chat_name,
                            'messages': []
                        }
                    chat_messages[chat_id]['messages'].append((msg_date, sender, text))
                
            except Exception as e:
                continue
        
        conn.close()
        
        if not chat_messages:
            return "No messages found in the specified time period.", []
        
        all_messages = []
        conversation_text = "Multiple conversations:\n\n"
        
        for chat_id, chat_data in chat_messages.items():
            if chat_data['messages']:
                conversation_text += f"Chat with {chat_data['name']}:\n"
                for msg in chat_data['messages']:
                    formatted_msg = f"{msg[0].strftime('%Y-%m-%d %H:%M')} - {msg[1]}: {msg[2]}"
                    all_messages.append(formatted_msg)
                    conversation_text += f"{msg[1]}: {msg[2]}\n"
                conversation_text += "\n---\n\n"
        
        print(f"Found messages from {len(chat_messages)} conversations")
        return conversation_text, all_messages
        
    except Exception as e:
        print(f"Error: {e}")
        return f"Error fetching messages: {e}", []

def generate_summary(text, model, tokenizer, max_length=150, min_length=30):
    """Generate summary using BART"""
    try:
        contact_names = get_contact_names()
        
        conversations = text.split("---")
        summaries = []
        
        for conversation in conversations:
            if not conversation.strip():
                continue
                
            formatted_text = (
                "can you summarize these messages in detail, including:\n"
                "- what started the conversation\n"
                "- specific details about games or activities mentioned\n"
                "- exact plans made\n"
                "- specific scores or achievements shared\n\n"
                f"{conversation.strip()}"
            )
            
            inputs = tokenizer(
                formatted_text,
                max_length=1024,
                truncation=True,
                padding="longest",
                return_tensors="pt"
            )
            
            summary_ids = model.generate(
                inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                max_length=max_length,
                min_length=min_length,
                num_beams=5,
                length_penalty=1.2,
                early_stopping=True,
                no_repeat_ngram_size=2,
                do_sample=True,
                temperature=0.7,
                top_p=0.92,
                repetition_penalty=1.2
            )
            
            summary = tokenizer.decode(summary_ids[0], skip_special_tokens=True)
            
            prefixes = ["The conversation shows", "In this conversation", "This is about", "The messages show"]
            for prefix in prefixes:
                if summary.lower().startswith(prefix.lower()):
                    summary = summary[len(prefix):].strip()
                    if summary.startswith("that"):
                        summary = summary[4:].strip()
                    break
            
            if summary:
                chat_name = ""
                if "Chat with" in conversation:
                    chat_name = conversation.split("Chat with")[1].split("\n")[0].strip(":\n ")
                    chat_name = get_contact_name(chat_name, contact_names)
                    summary = f"[{chat_name}] {summary}"
                
                summaries.append(summary)
        
        final_summary = "\n\n".join(summaries)
        return final_summary.strip()
        
    except Exception as e:
        return f"Error generating summary: {e}"

def main():
    model, tokenizer = load_model()
    
    print("\nWelcome to iMessage Conversation Summarizer!")
    print("Type 'quit' or 'exit' to end the program")
    print("-" * 50)
    
    try:
        while True:
            try:
                days_input = input("\nHow many days of messages to summarize? (default: 7): ").strip()
                days = int(days_input) if days_input else 7
                
                contact = input("Enter contact name to filter (or press Enter for all contacts): ").strip()
                
                if contact.lower() in ['quit', 'exit']:
                    break
                
                print("\nFetching messages...")
                conversation, display_messages = fetch_messages(days, contact if contact else None)
                
                if not display_messages:
                    print("No messages found!")
                    continue
                
                print("\nSample of messages:")
                for msg in display_messages[:5]:
                    print(msg)
                
                max_words = input("\nMaximum summary length in words (press Enter for default): ").strip()
                max_length = int(max_words) * 4 if max_words else 200
                
                print("\nGenerating summary...")
                print("-" * 50)
                summary = generate_summary(conversation, model, tokenizer, max_length=max_length)
                
                print(f"\nSummary of the last {days} days of messages:")
                if contact:
                    print(f"(Filtered for contact: {contact})")
                print("-" * 50)
                print(summary)
                print("-" * 50)
                
                if input("\nShow full conversation? (y/n): ").lower().startswith('y'):
                    print("\nFull Conversation:")
                    print("-" * 50)
                    for msg in display_messages:
                        print(msg)
                    print("-" * 50)
                
                if not input("\nSummarize more messages? (y/n): ").lower().startswith('y'):
                    break
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
                continue
    
    except Exception as e:
        print(f"An error occurred: {e}")
    
    print("\nGoodbye!")

if __name__ == "__main__":
    main() 