import copy
from datetime import datetime, timedelta, timezone
from typing import List, Dict
import pandas as pd
import json
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from core.openai import chat_completion
from core.agent.formatted_schemas import (
    get_question_class_formatted_schema,
    get_confirm_booking_formatted_schema,
    get_final_response_formatted_schema,
)
from core.agent.prompts import (
    QUESTION_CLASS_SYSTEM_PROMPT,
    VENUE_SUMMARY_SYSTEM_PROMPT,
    VENUE_CONCLUSION_SYSTEM_PROMPT,
    CONFIRM_BOOKING_SYSTEM_PROMPT,
    FINAL_RESPONSE_SYSTEM_PROMPT,
)

from core.logger import get_logger

logger = get_logger(__name__, service="LLM")

async def get_question_class(
    openai_client: AsyncOpenAI,
    messages: List[ChatCompletionMessageParam],
    question_class_details: Dict[str, Dict],
    # Reccuring
    depth: int = 1,
) -> List[str]:
    question_classes_list = list(question_class_details.keys())
    question_classes_description = {
        key: value["description"] for key, value in question_class_details.items()
    }
    
    question_class_llm_result: Dict = await chat_completion(
        openai_client=openai_client,
        user_prompt=messages,
        system_prompt=QUESTION_CLASS_SYSTEM_PROMPT.format(
            question_classes_list=question_classes_list,
            question_classes_description=question_classes_description
        ),
        formatted_schema=get_question_class_formatted_schema(
            question_classes_list=question_classes_list
        ),
        model_name="gpt-4.1",
    )
    
    question_class_result: List[str] = [question_class_llm_result.get("question_class", "")]
    
    logger.info(f"Question Class at depth {depth}: {question_class_result[0]}")
    
    # Check if the class has subclass
    question_class_dict = question_class_details.get(question_class_result[0])

    is_class_has_subclass = "subclass" in question_class_dict.keys()
    if is_class_has_subclass:
        question_class_result = question_class_result + await get_question_class(
            openai_client=openai_client,
            messages=messages,
            question_class_details=question_class_dict.get("subclass"),
            depth=depth+1
        )
        
    return question_class_result

async def get_venue_summary(
    openai_client: AsyncOpenAI,
    messages: List[ChatCompletionMessageParam]
):
    # messages_user = [msg for msg in messages if msg.get("role") == "user"]
    venue_summary = await chat_completion(
        openai_client=openai_client,
        user_prompt=messages,
        system_prompt=VENUE_SUMMARY_SYSTEM_PROMPT,
        model_name="gpt-4.1-mini",
    )
    
    return venue_summary

async def get_venue_conclusion(
    openai_client: AsyncOpenAI,
    messages: List[ChatCompletionMessageParam],
    venue_recommendation: Dict
):
    venue_conclusion = await chat_completion(
        openai_client=openai_client,
        user_prompt=messages,
        system_prompt=VENUE_CONCLUSION_SYSTEM_PROMPT.format(
            venue_recommendation=str(venue_recommendation)
        ),
        model_name="gpt-4.1-mini"
    )
    
    return venue_conclusion

async def get_confirm_booking(
    openai_client: AsyncOpenAI,
    messages: List[ChatCompletionMessageParam],
    venue_recommendation: str,
):
    confirm_book_response = await chat_completion(
        openai_client=openai_client,
        user_prompt=messages,
        system_prompt=CONFIRM_BOOKING_SYSTEM_PROMPT.format(
            venue_recommendation=str(venue_recommendation)
        ),
        formatted_schema=get_confirm_booking_formatted_schema(),
        model_name="gpt-4.1-mini",
    )
    
    return confirm_book_response

async def get_final_response(
    openai_client: AsyncOpenAI,
    messages: List[ChatCompletionMessageParam],
    extra_prompt: str,
):
    final_response = await chat_completion(
        openai_client=openai_client,
        user_prompt=messages,
        system_prompt=FINAL_RESPONSE_SYSTEM_PROMPT.format(
            extra_prompt=extra_prompt,
        ),
        formatted_schema=get_final_response_formatted_schema(),
        model_name="gpt-4.1-mini",
    )
    
    return final_response