import httpx
import re
import os

from core.logger import get_logger

logger = get_logger(__name__)

from dotenv import load_dotenv
load_dotenv()

VPS_URL = os.getenv("VPS_URL")

INQUIRY_URL = "{VPS_URL}/api/v1/recommendation/inquiry/whatsapp"
BOOKING_URL = "{VPS_URL}/api/v1/recommendation/inquiry/book/{ticket_id}/{venue_id}"
NEXT_BOOKING_URL = "{VPS_URL}/api/v1/recommendation/inquiry/whatsapp/{ticket_id}/next-recommendation"  # add phone number

async def chat_inquiry(user_name: str, message: str, phone_number: str, k_venue: int = 5) -> str:
    """
    Send a WhatsApp inquiry to the recommendation API and return a formatted response.

    Args:   
        user_name (str): The user's name
        message (str): The user's inquiry message
        phone_number (str): The user's phone number
        k_venue (int, optional): Number of venues to recommend (default 3)

    Returns:
        str: Formatted recommendation message
    """
    payload = {
        "phone_number": phone_number,
        "text_body": message,
        "k_venue": k_venue
    }

    inquiry_url = INQUIRY_URL.format(VPS_URL=VPS_URL)
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(inquiry_url, json=payload)
        # response.raise_for_status()
        
    if response.status_code != 200:
        return "Failed to request inquiry. Please try again later."
    
    data = response.json()

    ticket_id = data.get("ticket_id", "N/A")
    venues = data.get("top_k_venues", [])
    if not venues:
        return f"Ticket ID: {ticket_id}\nHi {user_name}, sorry! I couldn't find any venues matching your request. Kindly request another one or try again later."

    formatted_venues = []
    for idx, venue in enumerate(venues, start=1):
        payload = venue.get("payload", {})
        formatted_venues.append(
            f"{idx}. {payload.get('name')} ({payload.get('id', 'N/A')})\n"
            f"   📍 Location: {payload.get('location', 'N/A')}\n"
            f"   🏷️ Type: {payload.get('type', 'N/A')}\n"
            f"   ⭐ Amenities: {payload.get('amenities', 'N/A')}\n"
        )

    response_text = (
        f"🎟️ Ticket ID: {ticket_id}\n\n"
        f"Hi {user_name}, Welcome to Venuexplorer! Based on your request, here are the top {len(formatted_venues)} venue recommendations:\n"
        + "\n*To book a venue, please response with: book #  (for example: book 1)*"
        + "\n*To request other venue recommendation, please response with: book next*\n\n"
        + "\n".join(formatted_venues)
        + "\n_ⓘ Kindly respond only according to the instructions._"
    )

    return response_text

async def chat_inquiry_next(user_name: str, phone_number: str, last_message: str) -> str:
    """
    Send a WhatsApp inquiry to the recommendation API and return a formatted response.

    Args:
        user_name (str): The user's name
        message (str): The user's inquiry message
        phone_number (str): The user's phone number
        k_venue (int, optional): Number of venues to recommend (default 3)

    Returns:
        str: Formatted recommendation message
    """
    # 1. Extract ticket_id
    ticket_match = re.search(r"Ticket ID:\s*([A-Z0-9\-]+)", last_message)
    if not ticket_match:
        return "Sorry, I could not find a ticket ID in your inquiry. Kindly request another inquiry."

    ticket_id = ticket_match.group(1)
    
    logger.info(f"Chat Inquiry Next: Ticket ID: {ticket_id}")
    
    # 2. Hit booking API
    next_booking_url = NEXT_BOOKING_URL.format(
        VPS_URL=VPS_URL,
        ticket_id=ticket_id
    )
    logger.info(f"Chat Inquiry Next: next_booking_url: {next_booking_url}")
    payload = {
        "phone_number": phone_number
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(next_booking_url, json=payload)
        
    if response.status_code != 200:
        return "Failed to request next booking. Please try again later."
    
    data = response.json()
    logger.info(f"Chat Inquiry Next: response: {str(data)[:50]}")

    # ticket_id = data.get("ticket_id", ticket_id)
    venues = data.get("top_k_venues", [])
    if not venues:
        return f"Ticket ID: {ticket_id}\nHi {user_name}, sorry! There is no other recommendation. Please kindly request an inquiry again."

    formatted_venues = []
    for idx, venue in enumerate(venues, start=1):
        payload = venue.get("payload", {})
        formatted_venues.append(
            f"{idx}. {payload.get('name')} ({payload.get('id', 'N/A')})\n"
            f"   📍 Location: {payload.get('location', 'N/A')}\n"
            f"   🏷️ Type: {payload.get('type', 'N/A')}\n"
            f"   ⭐ Amenities: {payload.get('amenities', 'N/A')}\n"
        )

    response_text = (
        f"🎟️ Ticket ID: {ticket_id}\n\n"
        f"Hi {user_name}! Based on your request, here are the other {len(formatted_venues)} venue recommendations:\n"
        + "\n*To book a venue, please response with: book #  (for example: book 1)*"
        + "\n*To request other venue recommendation, please response with: book next*\n\n"
        + "\n".join(formatted_venues)
        + "\n_ⓘ Requesting additional venue recommendation may lead to inaccurate results._"
        + "\n_ⓘ Kindly respond only according to the instructions._"
    )

    return response_text

async def book_selected_venue(selected_venue_index: int, inquiry_chat: str) -> str:
    """
    Parse inquiry_chat, extract ticket_id and venue info for the selected venue,
    then call the booking API. Returns a user-friendly confirmation message.

    Args:
        selected_venue_index (int): The number of the venue chosen (1-based index).
        inquiry_chat (str): The full chat response generated by chat_response.

    Returns:
        str: Confirmation message for the user.
    """
    # 1. Extract ticket_id
    ticket_match = re.search(r"Ticket ID:\s*([A-Z0-9\-]+)", inquiry_chat)
    if not ticket_match:
        return "Sorry, I could not find a ticket ID in your inquiry. Kindly request another inquiry."

    ticket_id = ticket_match.group(1)

    # 2. Extract all venues
    venue_pattern = re.compile(
        r"(\d+)\.\s+([^\n]+?)\s+\((\d+)\)\r?\n"
        r".*?📍 Location:\s*(.*?)\r?\n"
        r".*?🏷️ Type:\s*(.*?)\r?\n"
        r".*?⭐ Amenities:\s*(.*?)\r?\n",
        re.DOTALL,
    )
    venues = venue_pattern.findall(inquiry_chat)

    if not venues or selected_venue_index < 1 or selected_venue_index > len(venues):
        return "Invalid venue selection. Please try request an inquriy again or try again later."

    # 3. Get selected venue
    selected_venue = venues[selected_venue_index - 1]
    _, name, venue_id, location, venue_type, amenities = selected_venue
    logger.info(f"Book Selected Venue: selected_venues: {selected_venue}")

    # 4. Hit booking API
    booking_url = BOOKING_URL.format(VPS_URL=VPS_URL, ticket_id=ticket_id, venue_id=venue_id)
    logger.info(f"Book Selected Venue: booking_url: {booking_url}")
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(booking_url)

    logger.info(f"Book Selected Venue: response: {response}")
    if response.status_code == 200:
        return f"Success! The venue *{name.strip()}* ({venue_id}) has been successfully booked under ticket {ticket_id}."
    else:
        return f"Failed to book the venue *{name.strip()}* ({venue_id}). Please request another inquiry or try again later."