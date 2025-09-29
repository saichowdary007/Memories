from __future__ import annotations

import asyncio
import logging
from typing import List

import torch
from PIL import Image
from transformers import SiglipModel, SiglipProcessor

from core.config import settings
from apps.workers.model_manager import model_manager

logger = logging.getLogger(__name__)


class ImageEmbeddingService:
    def __init__(self) -> None:
        self._model_name = settings.image_embeddings_model

    async def _load(self) -> tuple[SiglipProcessor, SiglipModel]:
        async def loader() -> tuple[SiglipProcessor, SiglipModel]:
            def _load_sync() -> tuple[SiglipProcessor, SiglipModel]:
                processor = SiglipProcessor.from_pretrained(self._model_name)
                model = SiglipModel.from_pretrained(self._model_name)
                model.eval()
                if torch.cuda.is_available():
                    model.to("cuda")
                elif torch.backends.mps.is_available():
                    model.to("mps")
                return processor, model

            return await asyncio.to_thread(_load_sync)

        return await model_manager.get_or_load(self._model_name, loader)

    async def embed(self, image: Image.Image) -> List[float]:
        processor, model = await self._load()

        def _run() -> List[float]:
            inputs = processor(images=image, return_tensors="pt")
            if torch.cuda.is_available():
                inputs = {k: v.to("cuda") for k, v in inputs.items()}
            elif torch.backends.mps.is_available():
                inputs = {k: v.to("mps") for k, v in inputs.items()}
            with torch.no_grad():
                embeddings = model.get_image_features(**inputs)
                embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            return embeddings.cpu().tolist()[0]

        return await asyncio.to_thread(_run)


image_embedding_service = ImageEmbeddingService()
