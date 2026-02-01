# Session Configuration
INACTIVITY_WARNING_SECONDS = 3 * 60  # 3 minutes
INACTIVITY_END_SECONDS = 5 * 60  # 5 minutes
FORCED_SESSION_SECONDS = 1 * 30 * 30  # 1 hour
FORCED_WARNING_BEFORE = 5 * 60  # 5 minutes

# Messages Configuration
AGENT_ERROR_DEFAULT_MESSAGE = "Sorry, but I can't assist you with that."
AGENT_SESSION_WARNING_MESSAGE = "Mary will end this chat in 2 minutes due to inactivity. Just reply to continue the conversation."
AGENT_SESSION_LIMIT_MESSAGE = "Mary will end this chat in 5 minutes due to session limit."
AGENT_SESSION_END_MESSAGE = "Thank you for contacting Mary! If you need help again later, feel free to reach out anytime."


# Question Class Configuration
question_class_details = {
    "inquiry": {
        "description": "Inquiry regarding venue details, including booking process, venue specifications, available amenities, and related information. If the user want to book but the chat is too early (2 first chat), just go to 'general_talk' class. But If the chat is long enough, go for this class.",
        "subclass": {
            "confirm_booking": {
                "description": "Use this subclass when the user clearly indicates they want to confirm or finalize. Only for final decision of booking, not just providing extra detail.",
                "tools": "confirm_booking"
            },
            "venue_recommendation": {
                "description": "Use this subclass when the user is still exploring options — asking for venue details, comparing choices, or responding to the assistant's suggestions about potential venues. If the chat history never giving venue comparison to user, you must choose this subclass. IMPORTANT: Also use this subclass when user asks for 'best venues', 'venue recommendations', 'suggest venues', or any request to see available venues in a location.",
                "tools": "venue_recommendation",
            }
        }

    },
    "general_talk": {
        "description": "Very general message such as basic confirming, greetings, thanks, apologies, and so on. DO NOT use this class if user asks for venue recommendations or best venues - use 'inquiry/venue_recommendation' instead.",
        "tools": "general_talk",
    },
    "end_session": {
        "description": "Choose this class if the user want to end the chat session.",
        "tools": "end_session",
    }
}

