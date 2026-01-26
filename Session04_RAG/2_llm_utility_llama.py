import os

import ollama

def ask_question_llama(prompt, context):
    response = ollama.chat(
        model='llama3',
        messages=[
            {"role": "system", "content": "You are a helpful assistant that answers questions based on the provided context."},
            {"role": "user", "content": f"context: {context}\nprompt: {prompt}"}
        ]
    )
    return response['message']['content']

if __name__ == "__main__": 
    prompt = "What is the capital of France?"
    context = "France is a country in Europe. Its capital city is Paris."
    response = ask_question_llama(prompt, context)
    print(f"Response from OpenAI llm: {response}")