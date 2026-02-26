from dotenv import load_dotenv
import os
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel
from agents.extensions.models.litellm_model import LitellmModel

flg_env = load_dotenv()
print('\nENV loaded:', flg_env)

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

client = None
MODEL = None

if OPENAI_API_KEY:
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    MODEL = OpenAIChatCompletionsModel(
        model="gpt-4o-mini",
        openai_client=client
    )