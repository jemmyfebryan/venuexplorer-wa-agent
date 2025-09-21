question_class_details = {
    "inquiry": {
        "description": "Inquiry regarding venue details, including booking process, venue specifications, available amenities, and related information. If the user want to book but the chat is too early (2 first chat), just go to 'general_talk' class. But If the chat is long enough, go for this class.",
        "subclass": {
            "confirm_booking": {
                "description": "Use this subclass when the user clearly indicates they want to confirm or finalize. Only for final decision of booking, not just providing extra detail.",
                "tools": "confirm_booking"
            },
            "venue_recommendation": {
                "description": "Use this subclass when the user is still exploring options — asking for venue details, comparing choices, or responding to the assistant's suggestions about potential venues.",
                "tools": "venue_recommendation",
            }
        }

    },
    "general_talk": {
        "description": "Very general message such as basic confirming, greetings, thanks, apologies, and so on.",
        "tools": "general_talk",
    },
    "end_session": {
        "description": "Choose this class if the user want to end the chat session.",
        "tools": "end_session",
    }
}

