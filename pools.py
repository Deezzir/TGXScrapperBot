import logging
import asyncio
import json
from os import getenv
from aiohttp import ClientSession
from solana.rpc.websocket_api import connect as ws_connect
from solana.rpc.async_api import AsyncClient
from solders.rpc.responses import GetTransactionResp, GetSignaturesForAddressResp
from solana.rpc.types import MemcmpOpts, Commitment
from solders.pubkey import Pubkey
from solders.transaction_status import (
    UiTransaction,
    EncodedTransactionWithStatusMeta,
    UiPartiallyDecodedInstruction,
)
from solders.rpc.config import RpcTransactionLogsFilterMentions
from solders.signature import Signature
from typing import Optional, Tuple, List, Dict, Any, Union, TypedDict
import pprint
from dataclasses import dataclass
from dotenv import load_dotenv
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.types import URLInputFile
import utils

load_dotenv()

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

RPC = getenv("RPC")
RAYDIUN_PROGRAM_ID = Pubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")
SOL_MINT = Pubkey.from_string("So11111111111111111111111111111111111111112")
PUMP_WALLET = Pubkey.from_string("39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg")
ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string(
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
)
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")


@dataclass
class Holder:
    address: str
    allocation: int


@dataclass
class HoldersInfo:
    top_holders: List[Holder]
    dev_allocation: int
    top_holders_allocation: int


@dataclass
class AssetData:
    dev_wallet: str
    dev_allocation: int
    top_holders: List[Holder]
    top_holders_allocation: int
    ca: str
    img_url: str
    name: str
    fill_time: str
    symbol: str
    twitter: Optional[str]
    telegram: Optional[str]
    website: Optional[str]
    pump: Optional[str]
    dex: str


class NewPoolsScrapper:
    def __init__(self, rpc: str):
        self.rpc = rpc
        self.task: Optional[asyncio.Task[Any]] = None
        self.topic_id = 35117
        self.bot: Optional[Bot] = None
        self.chat_id: Optional[int] = None

    async def start(self, chat_id: int, bot: Bot) -> None:
        if self.task:
            await bot.send_message(chat_id, "Pool scrapper already running.")
            return
        await bot.send_message(chat_id, "Starting New Pools scrapper...")
        task = asyncio.create_task(self._get_new_pools())
        self.task = task
        self.bot = bot
        self.chat_id = chat_id
        await task

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            self.task = None
            self.bot = None
            self.chat_id = None

    def _compress_dev_link(self, dev: str) -> str:
        compressed_string = dev[:4] + "\.\.\." + dev[-4:]
        profile_link = f"[{compressed_string}](https://pump.fun/profile/{dev})"
        return profile_link

    async def _post_new_pool(self, asset_info: AssetData) -> None:
        if not self.task or not self.bot or not self.chat_id:
            LOGGER.error("Task not initialized")
            return

        keyboard_buttons: List[List[InlineKeyboardButton]] = []
        top_buttons = []
        bottom_buttons = []

        payload = (
            f"*NEW POOL LAUNCHED*\n\n"
            f"*{asset_info.name} \(${asset_info.symbol}\)*\n"
            f"*CA:* `{asset_info.ca}`\n\n"
            f"*Dev:* {self._compress_dev_link(asset_info.dev_wallet)}\n"
            f"*Dev Allocation:* {asset_info.dev_allocation if asset_info.dev_allocation > 1 else '<1%'}%\n\n"
            f"*Top Holders:* "
        )
        allocation_strings = [
            f"{holder.allocation}%" for holder in asset_info.top_holders[:5]
        ]
        result = " \| ".join(allocation_strings)
        payload += result
        payload += f"\n*Top Holders Allocation:* {asset_info.top_holders_allocation}%\n"
        payload += (
            f"\n*Fill time: *{utils.calculate_timespan(int(asset_info.fill_time))}"
        )

        if asset_info.twitter:
            top_buttons.append(
                InlineKeyboardButton(
                    text="Twitter",
                    url=asset_info.twitter,
                )
            )
        if asset_info.telegram:
            top_buttons.append(
                InlineKeyboardButton(
                    text="Telegram",
                    url=asset_info.telegram,
                )
            )
        if asset_info.website:
            top_buttons.append(
                InlineKeyboardButton(
                    text="Website",
                    url=asset_info.website,
                )
            )

        bottom_buttons.append(
            InlineKeyboardButton(
                text="Pump Fun",
                url=asset_info.pump,
            )
        )
        bottom_buttons.append(
            InlineKeyboardButton(
                text="DEX Screener",
                url=asset_info.dex,
            )
        )
        keyboard_buttons.append(top_buttons)
        keyboard_buttons.append(bottom_buttons)
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        image = URLInputFile(asset_info.img_url)
        msg = await utils.send_photo(
            self.bot,
            self.chat_id,
            image,
            payload,
            self.topic_id,
            keyboard,
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    def _find_instruction_by_program_id(
        self, transaction: UiTransaction, target_program_id: Pubkey
    ) -> Optional[UiPartiallyDecodedInstruction]:
        if not self.task:
            return None
        if not transaction.message or not transaction.message.instructions:
            return None

        for instruction in transaction.message.instructions:
            if not isinstance(instruction, UiPartiallyDecodedInstruction):
                continue
            if instruction.program_id == target_program_id:
                return instruction
        return None

    async def _get_asset(self, session: ClientSession, mint: Pubkey) -> Optional[dict]:
        if not self.task:
            return None
        headers = {"Content-Type": "application/json"}
        payload = {
            "jsonrpc": "2.0",
            "id": "text",
            "method": "getAsset",
            "params": {"id": str(mint)},
        }

        try:
            async with session.post(
                f"https://{RPC}", headers=headers, data=json.dumps(payload)
            ) as response:
                data = await response.json()
                return data["result"]
        except Exception as e:
            LOGGER.error(f"Error in _get_asset: {e}")
            return None

    async def _get_token_uri_metadata(
        self, session: ClientSession, uri: str
    ) -> Optional[dict]:
        if not self.task or not uri:
            return None
        try:
            async with session.get(uri) as response:
                data = await response.json()
                return data
        except Exception as e:
            LOGGER.error(f"Error in _get_token_uri_metadata: {e}")
            return None

    async def _get_tx_details(
        self, client: AsyncClient, sig: Signature
    ) -> Optional[UiTransaction]:
        if not self.task:
            return None
        tx_raw = GetTransactionResp(None)
        attempt = 0

        try:
            while attempt < 10:
                tx_raw = await client.get_transaction(
                    sig, "jsonParsed", Commitment("confirmed"), 0
                )
                if tx_raw != GetTransactionResp(None):
                    break
                else:
                    LOGGER.warning(f"Failed to get transaction {sig}, retrying...")
                    attempt += 1
                    await asyncio.sleep(0.5)
            if (
                tx_raw.value
                and tx_raw.value.transaction
                and isinstance(tx_raw.value.transaction.transaction, UiTransaction)
            ):
                return tx_raw.value.transaction.transaction
        except Exception as e:
            LOGGER.error(f"Error in _get_tx_details: {e}")
        return None

    async def _process_log(
        self, client: AsyncClient, log: dict
    ) -> Optional[Tuple[Pubkey, Pubkey]]:
        if not self.task:
            return None
        value = log[0].result.value
        if value.err:
            return None
        if any(init_log for init_log in value.logs if "initialize2" in init_log):
            sig = value.signature
            await asyncio.sleep(0.5)
            tx = await self._get_tx_details(client, sig)
            if not tx:
                return None
            LOGGER.info(f"Found the initilize new pool tx: {sig}")
            init_instr = self._find_instruction_by_program_id(
                tx,
                RAYDIUN_PROGRAM_ID,
            )
            if init_instr:
                address_a = init_instr.accounts[8]
                address_b = init_instr.accounts[9]
                pair = init_instr.accounts[4]
                LOGGER.info(
                    f"FOUND new pair: Token A: {address_a} Token B: {address_b}"
                )
                if init_instr.accounts[17] != PUMP_WALLET:
                    LOGGER.info("Not a pump wallet transaction")
                    return None
                if address_a == SOL_MINT:
                    return (address_b, pair)
                elif address_b == SOL_MINT:
                    return (address_a, pair)
        return None

    async def _get_new_pools(self):
        if not self.task:
            return
        async with ClientSession() as session:
            async with AsyncClient(f"https://{self.rpc}") as client:
                async with ws_connect(f"wss://{self.rpc}") as websocket:
                    sub_id = None
                    try:
                        await websocket.logs_subscribe(
                            RpcTransactionLogsFilterMentions(RAYDIUN_PROGRAM_ID),
                            "confirmed",
                        )
                        LOGGER.info("Subscribed to logs. Waiting for messages...")
                        first_resp = await websocket.recv()
                        sub_id = first_resp[0].result

                        async for log in websocket:
                            try:
                                mint_pair = await self._process_log(client, log)
                                if mint_pair:
                                    LOGGER.info(f"Found new pool: {str(mint_pair[0])}")
                                    asset_info = await self._get_asset_info(
                                        session, client, mint_pair[0], mint_pair[1]
                                    )
                                    if asset_info:
                                        await self._post_new_pool(asset_info)
                            except Exception as e:
                                LOGGER.error(f"Error processing a log: {e}")
                    except asyncio.CancelledError:
                        LOGGER.info("Program Logs Task was cancelled.")
                    except Exception as e:
                        LOGGER.error(f"Error in Program Logs Task: {e}")
                    finally:
                        if sub_id:
                            await websocket.logs_unsubscribe(sub_id)
                        LOGGER.info("Cleaned up resources.")

    def _sort_holders(self, top_holders: List[Holder]) -> List[Holder]:
        return sorted(top_holders, key=lambda x: x.allocation, reverse=True)

    async def _get_allocation_info(
        self,
        client: AsyncClient,
        mint: Pubkey,
        dev: Optional[Pubkey],
        bonding_curve: Optional[Pubkey],
    ) -> HoldersInfo:
        info = HoldersInfo(top_holders=[], dev_allocation=0, top_holders_allocation=0)
        if not self.task:
            return info
        try:
            total_supply = await client.get_token_supply(mint)
            holders_raw = await client.get_token_largest_accounts(mint)
            for holder_raw in holders_raw.value:
                info.top_holders.append(
                    Holder(
                        address=str(holder_raw.address),
                        allocation=int(
                            round(
                                int(holder_raw.amount.amount)
                                / int(total_supply.value.amount)
                                * 100
                            )
                        ),
                    )
                )
            if dev:
                dev_token = Pubkey.find_program_address(
                    [
                        bytes(dev),
                        bytes(TOKEN_PROGRAM_ID),
                        bytes(mint),
                    ],
                    ASSOCIATED_TOKEN_PROGRAM_ID,
                )[0]
                for holder in info.top_holders:
                    if holder.address == str(dev_token):
                        info.dev_allocation = holder.allocation
                        break
            if bonding_curve:
                bonding_curve_token = Pubkey.find_program_address(
                    [
                        bytes(bonding_curve),
                        bytes(TOKEN_PROGRAM_ID),
                        bytes(mint),
                    ],
                    ASSOCIATED_TOKEN_PROGRAM_ID,
                )[0]
                info.top_holders = [
                    holder
                    for holder in info.top_holders
                    if holder.address != str(bonding_curve_token)
                ]
            info.top_holders_allocation = int(
                sum(holder.allocation for holder in info.top_holders)
            )

            return info
        except Exception as e:
            LOGGER.error(f"Error in get_allocation_info: {e}")
            return info

    async def _get_asset_info(
        self, session: ClientSession, client: AsyncClient, mint: Pubkey, pair: Pubkey
    ) -> Optional[AssetData]:
        if not self.task:
            return None
        asset = await self._get_asset(session, mint)
        if asset:
            uri_meta = await self._get_token_uri_metadata(
                session, asset["content"]["json_uri"]
            )
            if not uri_meta:
                return None

            token_info = await utils.get_token_info(str(mint))
            twitter = uri_meta.get("twitter", None)
            telegram = uri_meta.get("telegram", None)
            website = uri_meta.get("website", None)
            img_url = uri_meta.get("image", None)
            if token_info:
                alloc_info = await self._get_allocation_info(
                    client, mint, token_info.dev, token_info.bonding_curve
                )

            return AssetData(
                dev_wallet=(str(token_info.dev) if token_info else "Unknown"),
                fill_time=(token_info.created_timestamp if token_info else "Unknown"),
                dev_allocation=alloc_info.dev_allocation if alloc_info else 0,
                top_holders=alloc_info.top_holders if alloc_info else [],
                top_holders_allocation=(
                    alloc_info.top_holders_allocation if alloc_info else 0
                ),
                ca=asset["id"],
                name=asset["content"]["metadata"]["name"],
                symbol=asset["content"]["metadata"]["symbol"],
                twitter=twitter,
                img_url=img_url,
                telegram=telegram,
                website=website,
                pump=(f"https://pump.fun/{mint}"),
                dex=f"https://dexscreener.com/solana/{pair}",
            )
        return None


async def test():
    processor = NewPoolsScrapper(RPC)
    try:
        await processor.start()
    except KeyboardInterrupt:
        await processor.stop()


# Example usage
if __name__ == "__main__":
    asyncio.run(test())
