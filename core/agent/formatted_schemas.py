def get_question_class_formatted_schema(question_classes_list):
    return {
        "name": "question_class",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "question_class": {
                    "type": "string",
                    "enum": question_classes_list
                }
            },
            "required": ["question_class"],
            "additionalProperties": False
        }
    }

def get_confirm_booking_formatted_schema():
    return {
        "name": "parsed_venue",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "venue_name": {
                    "type": "string"
                },
                "venue_id": {
                    "type": "string"
                },
                "venue_location": {
                    "type": "string"
                },
                "venue_amenities": {
                    "type": "string"
                }
            },
            "required": ["venue_name", "venue_id", "venue_location", "venue_amenities"],
            "additionalProperties": False
        }
    }

def get_final_response_formatted_schema():
    return {
        "name": "response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "response_header": {
                    "type": "string"
                },
                "response_content": {
                    "type": "string"
                },
                "response_footer": {
                    "type": "string"
                }
            },
            "required": ["response_header", "response_content", "response_footer"],
            "additionalProperties": False
        }
    }
    
def get_extract_user_requirements_formatted_schema():
    return {
        "name": "user_requirements",
        "strict": True,
        "schema": {
            "description": "Extracted user requirements for venue booking",
            "type": "object",
            "properties": {
                "event_type": {"type": ["string", "null"], "description": "Type of event, null if not mentioned"},
                "location": {"type": ["string", "null"], "description": "Venue location, null if not mentioned"},
                "attendees": {"type": ["integer", "null"], "description": "Number of attendees, null if not mentioned"},
                "budget": {"type": ["string", "null"], "description": "Budget for the event, null if not mentioned"},
                "start_date": {"type": ["string", "null"], "description": "Event start date in YYYY-MM-DD format, null if not mentioned"},
                "end_date": {"type": ["string", "null"], "description": "Event end date in YYYY-MM-DD format, null if not mentioned"},
                "email": {"type": ["string", "null"], "description": "User's email address, null if not explicitly provided"},
                "customer_name": {"type": ["string", "null"], "description": "User's full name for booking - must be explicitly stated by user, NOT extracted from email, null if not provided"}
            },
            "required": ["event_type", "location", "attendees", "budget", "start_date", "end_date", "email", "customer_name"],
            "additionalProperties": False
        }
    }