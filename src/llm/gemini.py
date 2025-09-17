from vertexai.generative_models import HarmBlockThreshold
from vertexai.generative_models import GenerationConfig
from vertexai.generative_models import GenerativeModel
from vertexai.generative_models import HarmCategory
from vertexai.generative_models import Part
from src.config.logging import logger
from typing import Optional, Tuple
from typing import Dict
from typing import List 


def _create_generation_config() -> GenerationConfig:
    """
    Creates and returns a generation configuration.
    """
    try:
        gen_config = GenerationConfig(
            temperature=0.0,
            top_p=1.0,
            candidate_count=1,
            max_output_tokens=8192,
            seed=12345
        )
        return gen_config
    except Exception as e:
        logger.error(f"Error creating generation configuration: {e}")
        raise


def _create_safety_settings() -> Dict[HarmCategory, HarmBlockThreshold]:
    """
    Creates safety settings for content generation.
    """
    try:
        safety_settings = {
            HarmCategory.HARM_CATEGORY_UNSPECIFIED: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE
        }
        return safety_settings
    except Exception as e:
        logger.error(f"Error creating safety settings: {e}")
        raise


def generate(model: GenerativeModel, contents: List[Part], return_usage: bool = False) -> Optional[str]:
    """
    Generates a response using the provided model and contents.
    
    Args:
        model (GenerativeModel): The generative model instance.
        contents (List[Part]): The list of content parts.
    
    Returns:
        Optional[str]: The generated response text, or None if an error occurs.
    """
    try:
        logger.info("Generating response from Gemini")
        response = model.generate_content(
            contents,
            generation_config=_create_generation_config(),
            safety_settings=_create_safety_settings()
        )

        text = getattr(response, "text", None)
        if not text:
            logger.error("Empty response from the model")
            if return_usage:
                return None  # type: ignore[return-value]
            return None

        if not return_usage:
            logger.info("Successfully generated response")
            return text

        # Best-effort usage extraction (SDK versions differ)
        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = 0
        output_tokens = 0
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_token_count", None) or getattr(usage, "input_token_count", 0) or 0
            output_tokens = getattr(usage, "candidates_token_count", None) or getattr(usage, "output_token_count", 0) or 0

        logger.info("Successfully generated response")
        return text, {"token_in": int(prompt_tokens or 0), "token_out": int(output_tokens or 0)}  # type: ignore[return-value]
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        return None