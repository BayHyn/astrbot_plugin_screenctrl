import asyncio
from datetime import datetime
import time
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import Poke
from astrbot.core.platform import AstrMessageEvent
import pyautogui

from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent


@register(
    "astrbot_plugin_screenctrl",
    "Zhalslar",
    "屏幕控制插件，支持截屏、点击、按键等",
    "v1.0.1",
    "https://github.com/Zhalslar/astrbot_plugin_screenctrl",
)
class ScreenshotPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.plugin_data_dir = StarTools.get_data_dir("astrbot_plugin_screenshot")
        self.screen_width, self.screen_height = pyautogui.size()
        self.last_trigger_time: dict = {}
        self.cooldown_seconds: int = 1
        self.poke_screenshot: bool = config.get("poke_screenshot", False)

    async def _capture(self) -> str:
        save_name = datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
        save_path = self.plugin_data_dir / save_name
        screenshot = await asyncio.to_thread(pyautogui.screenshot)
        await asyncio.to_thread(screenshot.save, save_path)
        return str(save_path)

    def _clamp_position(self, x: int, y: int) -> tuple[int, int]:
        """限制坐标在屏幕范围内"""
        x = max(0, min(x, self.screen_width - 1))
        y = max(0, min(y, self.screen_height - 1))
        return x, y

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("截屏")
    async def on_capture(self, event: AstrMessageEvent):
        yield event.image_result(await self._capture())

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("点击")
    async def click_and_screenshot(self, event: AstrMessageEvent, x: int=0, y: int=0):
        x, y = self._clamp_position(x, y)
        pyautogui.click(x, y)
        yield event.image_result(await self._capture())

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("按下")
    async def press_keys_and_screenshot(self, event: AstrMessageEvent, keys: str):
        """
        同时支持：
        - 多个单键按顺序输入，如 `hello`
        - 组合键，如 `win+r`
        """
        valid_keys = set(pyautogui.KEYBOARD_KEYS)
        try:
            if "+" in keys:
                # 组合键，例如 win+r
                combo = [k.strip().lower() for k in keys.split("+")]
                if not all(k in valid_keys for k in combo):
                    invalid = [k for k in combo if k not in valid_keys]
                    yield event.plain_result(f"无效键位: {', '.join(invalid)}")
                    return
                pyautogui.hotkey(*combo)
            else:
                # 连续按键，例如 hello
                for k in keys:
                    if k.lower() not in valid_keys:
                        yield event.plain_result(f"不支持的键：{k}")
                        return
                    pyautogui.press(k.lower())
        except Exception as e:
            yield event.plain_result(f"按键执行失败: {e}")
            return

        yield event.image_result(await self._capture())


    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_poke(self, event: AiocqhttpMessageEvent):
        """戳一戳截屏"""
        if not self.poke_screenshot:
            return
        if not event.is_admin():
            return
        raw_message = getattr(event.message_obj, "raw_message", None)

        if (
            not raw_message
            or not event.message_obj.message
            or not isinstance(event.message_obj.message[0], Poke)
        ):
            return

        target_id: int = raw_message.get("target_id", 0)
        user_id: int = raw_message.get("user_id", 0)
        self_id: int = raw_message.get("self_id", 0)

        # 过滤与自身无关的戳
        if target_id != self_id:
            return

        # 冷却机制
        current_time = time.monotonic()
        last_time = self.last_trigger_time.get(user_id, 0)
        if current_time - last_time < self.cooldown_seconds:
            return
        self.last_trigger_time[user_id] = current_time

        yield event.image_result(await self._capture())
