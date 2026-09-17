import os
from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

response = client.models.embed_content(
    model="models/gemini-embedding-2",
    contents=["first string", "second string", "third string"],
    config=types.EmbedContentConfig(
        output_dimensionality=768,
        task_type="RETRIEVAL_DOCUMENT"
    )
)

print(f"Generated {len(response.embeddings)} embeddings")
for i, emb in enumerate(response.embeddings):
    print(f"Embedding {i} length: {len(emb.values)}")
