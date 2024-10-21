import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

assistant_id = os.getenv("ASSISTANT_ID")

print(api_key)
print(assistant_id)