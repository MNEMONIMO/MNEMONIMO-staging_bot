import io
from typing import Optional
from aiogram import Bot
from aiogram.types import BufferedInputFile, InputMediaPhoto
from loguru import logger

from app.core.config import settings
from app.db.models import Project, Tariff
from app.integrations.storage.s3 import storage_service
from app.bot.messages import (
    RESULT_HEADER, RESULT_CONCEPT, RESULT_SHOPPING_LIST,
    ERROR_GENERATION, GENERATION_DONE,
)
from app.bot.keyboards.keyboards import result_keyboard


class NotificationService:
    def __init__(self):
        self._bot: Optional[Bot] = None

    def get_bot(self) -> Bot:
        if self._bot is None:
            self._bot = Bot(token=settings.bot_token)
        return self._bot

    async def send_generation_result(self, project: Project) -> None:
        """Send generated images + concept to user."""
        bot = self.get_bot()
        telegram_id = project.user.telegram_id

        output_images = project.output_images
        if not output_images:
            await bot.send_message(telegram_id, ERROR_GENERATION)
            return

        try:
            # Send status message
            await bot.send_message(telegram_id, GENERATION_DONE)

            # Download and send images as media group (if > 1) or single photo
            image_files = []
            for img_record in sorted(output_images, key=lambda x: x.sort_order):
                img_bytes = storage_service.download_bytes(img_record.file_path)
                image_files.append(img_bytes)

            if len(image_files) == 1:
                photo = BufferedInputFile(image_files[0], filename="interior.jpg")
                await bot.send_photo(telegram_id, photo)
            else:
                media_group = [
                    InputMediaPhoto(
                        media=BufferedInputFile(b, filename=f"interior_{i+1}.jpg")
                    )
                    for i, b in enumerate(image_files)
                ]
                await bot.send_media_group(telegram_id, media_group)

            # Send concept text
            if project.concept_text:
                await bot.send_message(
                    telegram_id,
                    RESULT_HEADER + RESULT_CONCEPT.format(concept=project.concept_text),
                    parse_mode="HTML",
                )

            # Send shopping list (paid plans)
            if project.shopping_list and project.shopping_list.get("items"):
                items_text = _format_shopping_list(project.shopping_list["items"])
                await bot.send_message(
                    telegram_id,
                    RESULT_SHOPPING_LIST.format(items=items_text),
                    parse_mode="HTML",
                )

            # Send action buttons
            is_free = project.tariff == Tariff.FREE
            await bot.send_message(
                telegram_id,
                "Что дальше?",
                reply_markup=result_keyboard(has_free_plan=is_free),
            )

        except Exception as e:
            logger.error(f"Failed to send result for project {project.id}: {e}")
            try:
                await bot.send_message(telegram_id, ERROR_GENERATION)
            except Exception:
                pass

    async def notify_admin(self, message: str) -> None:
        """Send a message to all admins."""
        bot = self.get_bot()
        for admin_id in settings.admin_ids:
            try:
                await bot.send_message(admin_id, f"🔔 <b>Admin Alert</b>\n\n{message}", parse_mode="HTML")
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")

    async def broadcast(self, text: str, user_ids: list[int]) -> dict:
        """Broadcast a message to a list of users."""
        bot = self.get_bot()
        sent = 0
        failed = 0
        for uid in user_ids:
            try:
                await bot.send_message(uid, text, parse_mode="HTML")
                sent += 1
            except Exception as e:
                logger.warning(f"Broadcast failed for {uid}: {e}")
                failed += 1
        return {"sent": sent, "failed": failed}


def _format_shopping_list(items: list[dict]) -> str:
    lines = []
    for item in items:
        category = item.get("category", "")
        desc = item.get("description", "")
        color = item.get("color", "")
        price = item.get("price_range", "")
        lines.append(f"• <b>{category}</b> — {desc}, {color} | {price}")
    return "\n".join(lines)
