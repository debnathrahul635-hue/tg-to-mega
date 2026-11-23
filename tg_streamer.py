import asyncio
import struct
from pyrogram import raw
from pyrogram.file_id import FileId


class Buffer:
    """Async read buffer that pre-fetches Telegram file chunks."""

    def __init__(self, file, chunk_size=1024 * 1024):
        self._file = file
        self._bytes = b""
        self._offset = 0
        self._chunk_size = chunk_size
        self._eof = False
        self._download_task = None
        self._lock = asyncio.Lock()

    async def start(self):
        """Start background download task."""
        self._download_task = asyncio.create_task(self._background_download())

    async def _background_download(self):
        """Download chunks in background, staying ~2 chunks ahead."""
        offset = 0
        while not self._eof:
            # Wait if buffer is too large (16MB cap)
            while len(self._bytes) - self._offset > 16 * 1024 * 1024:
                await asyncio.sleep(0.1)

            chunk = await self._file.get_chunk_at(offset, self._chunk_size)
            if not chunk:
                self._eof = True
                break

            async with self._lock:
                self._bytes += chunk

            offset += len(chunk)
            if len(chunk) < self._chunk_size:
                self._eof = True

    async def read(self, count: int) -> bytes:
        """Read up to `count` bytes from the buffer."""
        while True:
            async with self._lock:
                available = len(self._bytes) - self._offset
                if available >= count:
                    data = self._bytes[self._offset : self._offset + count]
                    self._offset += count
                    # Free consumed memory
                    if self._offset > 1024 * 1024:
                        self._bytes = self._bytes[self._offset :]
                        self._offset = 0
                    return data
                elif self._eof:
                    data = self._bytes[self._offset :]
                    self._offset = len(self._bytes)
                    return data
            await asyncio.sleep(0.05)


class TelegramFile:
    """Handles streaming file reads from Telegram's MTProto servers."""

    def __init__(self, client, file_id_str: str, file_size: int):
        self._client = client
        self._file_id = FileId.decode(file_id_str)
        self._file_size = file_size
        self._media_session = None
        self._buffer = None

    async def _get_media_session(self):
        """Get or create a media session for the file's DC."""
        if self._media_session:
            return self._media_session

        dc_id = self._file_id.dc_id

        if dc_id != await self._client.storage.dc_id():
            # File is on a different DC, need to export auth
            exported = await self._client.invoke(
                raw.functions.auth.ExportAuthorization(dc_id=dc_id)
            )
            session = await self._client.session.get_media_session(dc_id)
            await session.invoke(
                raw.functions.auth.ImportAuthorization(
                    id=exported.id,
                    bytes=exported.bytes,
                )
            )
            self._media_session = session
        else:
            self._media_session = self._client.session

        return self._media_session

    def _get_location(self):
        """Build the InputFileLocation for this file."""
        file_id = self._file_id

        if file_id.file_type in (0, 2, 14):  # Thumbnail, Photo, PhotoSize
            return raw.types.InputPhotoFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=file_id.thumbnail_size or "",
            )
        else:  # Document, Audio, Video, etc.
            return raw.types.InputDocumentFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=file_id.thumbnail_size or "",
            )

    async def get_chunk_at(self, offset: int, limit: int = 1024 * 1024) -> bytes:
        """Get a chunk of the file at the given offset."""
        session = await self._get_media_session()
        location = self._get_location()

        for attempt in range(5):
            try:
                result = await session.invoke(
                    raw.functions.upload.GetFile(
                        location=location,
                        offset=offset,
                        limit=limit,
                    )
                )
                if isinstance(result, (raw.types.upload.File,)):
                    return result.bytes
                return b""
            except Exception as e:
                if attempt == 4:
                    raise
                await asyncio.sleep(1)

        return b""

    async def start_buffer(self):
        """Initialize and start the streaming buffer."""
        self._buffer = Buffer(self)
        await self._buffer.start()

    async def read(self, count: int) -> bytes:
        """Read bytes from the buffered stream."""
        if self._buffer is None:
            await self.start_buffer()
        return await self._buffer.read(count)
