import os
from dotenv import load_dotenv
from openai import OpenAI
from sentence_transformers import SentenceTransformer

from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility,
)
load_dotenv(override=True, dotenv_path="../.env.local")

milvus_uri = os.getenv("MILVUS_URI")
milvus_token = os.getenv("MILVUS_API_KEY")

# ---------------------------
# Semantic Search Function
# ---------------------------

def retrieve_similiar_contexts(query, collection_name="employee_policies", top_k=3):
    """
    Given a user query, return top K semantically similar texts from Milvus.
    """
    # connections.connect("default", host="localhost", port="19530")
    connections.connect(
        alias="default",
        uri=milvus_uri,
        token=milvus_token
    )

    print("Connected to Milvus on Zilliz Cloud")

    collection = Collection(collection_name)
    model = SentenceTransformer("all-MiniLM-L6-v2")

    query_vector = model.encode([query]).tolist()

    results = collection.search(
        data=query_vector,
        anns_field="embedding",
        param={"metric_type": "COSINE", "params": {"nprobe": 10}},
        limit=top_k,
        output_fields=["content"]
    )

    top_docs = []
    for hit in results[0]:
        top_docs.append({
            "content": hit.entity.get("content"),
            "score": hit.distance
        })

    return top_docs


# ---------------------------
# LLM Answer Generation
# ---------------------------

def generate_answer(query, contexts):
    """
    Generate an answer using OpenAI GPT model based on retrieved contexts.
    """
    load_dotenv(override=True, dotenv_path="../.env")
    my_api_key = os.getenv("OPEN_AI_API_KEY")

    client = OpenAI(api_key=my_api_key)


    context_str = "\n".join(contexts)
    prompt = f"Context:\n{context_str}\n\nQuestion: {query}\nAnswer:"

    response = client.chat.completions.create(
        model="gpt-5-nano",  # or gpt-4o if you have access
        messages=[
            {"role": "system", "content": "You are a helpful assistant that answers based only on context."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content.strip()