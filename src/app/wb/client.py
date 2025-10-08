import httpx
from .. import settings

class WBClient:
    def __init__(self, token: str | None = None):
        self.token = token or settings.WB_TOKEN
        self.headers = {"Authorization": self.token}

    async def get_prices(self, nm_ids: list[int]) -> dict[int, dict]:
        # Если токен == "MOCK", вернём фейковые данные
        if (self.token or "").upper() == "MOCK":
            return {nm: {"price": 1290, "discount": 15} for nm in nm_ids}

        # Временно опрашиваем по одному nm_id. Потом переделаем на батчи и правильный эндпоинт.
        result: dict[int, dict] = {}
        async with httpx.AsyncClient(timeout=30) as client:
            for nm in nm_ids:
                url = f"https://suppliers-api.wildberries.ru/public/api/v1/info?nmId={nm}"
                r = await client.get(url, headers=self.headers)
                if r.status_code == 200:
                    result[nm] = r.json()
        return result
