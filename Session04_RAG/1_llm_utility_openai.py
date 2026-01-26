import os
import dotenv 

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(override=True, dotenv_path="../.env.local")
my_api_key = os.getenv("OPENAI_API_KEY")
print(f"my api key is:[{my_api_key[:4]}...{my_api_key[-4:]}]")

client = OpenAI(api_key=my_api_key) 


def ask_question_openai(prompt,context):
    
    response = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that answers questions based on the provided context."},
            {"role": "user", "content": f"context: {context}\n\nprompt: {prompt}"}
        ]
    )
    return response.choices[0].message.content


if __name__ == "__main__": 
    prompt = "What is the capital of France?"
    context = "France is a country in Europe. Its capital city is Paris."
    response = ask_question_openai(prompt, context)
    print(f"Response from OpenAI llm: {response}")

