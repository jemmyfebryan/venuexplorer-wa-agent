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