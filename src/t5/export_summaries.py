import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List

def get_database_path() -> Path:
    """Get path to the messages database"""
    return Path.home() / "Library" / "Application Support" / "iMessage-Summarizer" / "messages.db"

def export_summaries() -> Dict:
    """Export summaries to JSON format"""
    db_path = get_database_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get example summaries
    data = {
        "example_weekly_summaries": [],
        "example_identity_summaries": [],
        "metadata": {
            "export_date": datetime.now().isoformat(),
            "total_contacts": 0,
            "total_messages": 0,
            "note": "These are selected examples to demonstrate the summarization capabilities"
        }
    }
    
    # Get a few interesting weekly summaries (family, friend, professional)
    cursor.execute("""
        SELECT DISTINCT
            c.display_name,
            w.week_start_date,
            w.week_end_date,
            w.summary_text,
            w.created_at
        FROM weekly_conversation_summaries w
        JOIN contacts c ON w.contact_id = c.id
        WHERE c.display_name IN ('Mom', 'Dad', 'Sebastian', 'Tim Tran', 'Professor Loessi')
        AND length(w.summary_text) > 100
        ORDER BY w.created_at DESC
        LIMIT 5
    """)
    
    for row in cursor.fetchall():
        data["example_weekly_summaries"].append({
            "contact": row[0],
            "week_start": row[1],
            "week_end": row[2],
            "summary": row[3],
            "created_at": row[4]
        })
    
    # Get identity summaries for the same contacts
    cursor.execute("""
        SELECT 
            c.display_name,
            i.summary_text,
            i.personality_traits,
            i.relationship_context,
            i.common_topics,
            i.confidence_scores,
            i.created_at
        FROM identity_summaries i
        JOIN contacts c ON i.contact_id = c.id
        WHERE c.display_name IN ('Mom', 'Dad', 'Sebastian', 'Tim Tran', 'Professor Loessi')
        ORDER BY i.created_at DESC
        LIMIT 5
    """)
    
    for row in cursor.fetchall():
        data["example_identity_summaries"].append({
            "contact": row[0],
            "summary": row[1],
            "personality_traits": json.loads(row[2]) if row[2] else {},
            "relationship_context": json.loads(row[3]) if row[3] else {},
            "common_topics": json.loads(row[4]) if row[4] else {},
            "confidence_scores": json.loads(row[5]) if row[5] else {},
            "created_at": row[6]
        })
    
    # Get metadata
    cursor.execute("SELECT COUNT(DISTINCT id) FROM contacts")
    data["metadata"]["total_contacts"] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM messages")
    data["metadata"]["total_messages"] = cursor.fetchone()[0]
    
    conn.close()
    
    # Export to file
    output_path = Path("summary_examples.json")
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    return data

if __name__ == "__main__":
    data = export_summaries()
    print(f"Exported {len(data['example_weekly_summaries'])} example weekly summaries")
    print(f"Exported {len(data['example_identity_summaries'])} example identity summaries")
    print(f"Total contacts in database: {data['metadata']['total_contacts']}")
    print(f"Total messages in database: {data['metadata']['total_messages']}")
    print("\nExported to summary_examples.json") 