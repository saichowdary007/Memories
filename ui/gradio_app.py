from __future__ import annotations

from typing import Dict, List

import gradio as gr
import httpx

API_BASE = "http://localhost:8000"


def build_app() -> gr.Blocks:
    with gr.Blocks(title="Personal Knowledge Brain") as demo:
        gr.Markdown("# Personal Knowledge Brain\nChat with your private knowledge graph.")
        token_box = gr.Textbox(label="JWT Token", value="", type="password")
        chatbot = gr.Chatbot(label="Assistant")
        query_box = gr.Textbox(label="Ask a question")
        citations = gr.JSON(label="Citations")

        async def on_submit(query: str, history: List[Dict[str, str]], token: str):
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{API_BASE}/ask",
                    json={"query": query, "top_k": 5},
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
            messages = history + [[query, data["answer"]]]
            citation_list = data.get("citations", [])
            return messages, citation_list, ""

        query_box.submit(fn=on_submit, inputs=[query_box, chatbot, token_box], outputs=[chatbot, citations, query_box])
    return demo


if __name__ == "__main__":
    demo = build_app()
    demo.queue()
    demo.launch()
