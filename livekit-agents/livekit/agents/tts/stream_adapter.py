from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable
from typing import Any
import logging
import re

from .. import tokenize, utils
from ..types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, APIConnectOptions, NotGivenOr
from .stream_pacer import SentenceStreamPacer
from .tts import (
    TTS,
    AudioEmitter,
    ChunkedStream,
    SynthesizedAudio,
    SynthesizeStream,
    TTSCapabilities,
)

# already a retry mechanism in TTS.synthesize, don't retry in stream adapter
DEFAULT_STREAM_ADAPTER_API_CONNECT_OPTIONS = APIConnectOptions(
    max_retry=0, timeout=DEFAULT_API_CONNECT_OPTIONS.timeout
)

logger = logging.getLogger("StreamAdapter")

class StreamAdapter(TTS):
    def __init__(
        self,
        *,
        tts: TTS,
        sentence_tokenizer: NotGivenOr[tokenize.SentenceTokenizer] = NOT_GIVEN,
        text_pacing: SentenceStreamPacer | bool = False,
    ) -> None:
        super().__init__(
            capabilities=TTSCapabilities(streaming=True, aligned_transcript=True),
            sample_rate=tts.sample_rate,
            num_channels=tts.num_channels,
        )
        self._wrapped_tts = tts
        self._sentence_tokenizer = sentence_tokenizer or tokenize.blingfire.SentenceTokenizer(
            retain_format=True
        )
        self._stream_pacer: SentenceStreamPacer | None = None
        if text_pacing is True:
            self._stream_pacer = SentenceStreamPacer()
        elif isinstance(text_pacing, SentenceStreamPacer):
            self._stream_pacer = text_pacing

        @self._wrapped_tts.on("metrics_collected")
        def _forward_metrics(*args: Any, **kwargs: Any) -> None:
            # TODO(theomonnom): The segment_id needs to be populated!
            self.emit("metrics_collected", *args, **kwargs)

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> ChunkedStream:
        return self._wrapped_tts.synthesize(text=text, conn_options=conn_options)

    def stream(
        self,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        callback: any,
        words_per_sec: float
    ) -> StreamAdapterWrapper:
        logger.info("In streamAdapter stream")
        return StreamAdapterWrapper(tts=self, conn_options=conn_options, callback=callback, words_per_sec=words_per_sec)

    def prewarm(self) -> None:
        self._wrapped_tts.prewarm()


class StreamAdapterWrapper(SynthesizeStream):
    def __init__(self, *, tts: StreamAdapter, conn_options: APIConnectOptions, callback: any, words_per_sec: float) -> None:
        super().__init__(tts=tts, conn_options=DEFAULT_STREAM_ADAPTER_API_CONNECT_OPTIONS)
        self._tts: StreamAdapter = tts
        self._wrapped_tts_conn_options = conn_options
        self._callback = callback
        self._words_per_sec = words_per_sec
        logger.info(f"In streamAdapterWrapper init - words_per_sec = {self._words_per_sec}")

            
    def get_duration(self, s):
        if s.startswith("<trl-break"):
            match = re.search(r"""duration\s*=\s*['"](\d+)(ms|s)?['"]""", s)
            if match:
                value = int(match.group(1))
                unit = match.group(2)
                if unit == 'ms':
                    return value / 1000
                else:  # 's' or None
                    return value
        return 0
            
    async def _metrics_monitor_task(self, event_aiter: AsyncIterable[SynthesizedAudio]) -> None:
        pass  # do nothing

    async def _run(self, output_emitter: AudioEmitter) -> None:
        sent_stream = self._tts._sentence_tokenizer.stream()
        if self._tts._stream_pacer:
            sent_stream = self._tts._stream_pacer.wrap(
                sent_stream=sent_stream,
                audio_emitter=output_emitter,
            )

        request_id = utils.shortuuid()
        output_emitter.initialize(
            request_id=request_id,
            sample_rate=self._tts.sample_rate,
            num_channels=self._tts.num_channels,
            mime_type="audio/pcm",
            stream=True,
        )

        segment_id = utils.shortuuid()
        output_emitter.start_segment(segment_id=segment_id)

        async def _forward_input() -> None:
            async for data in self._input_ch:
                if isinstance(data, self._FlushSentinel):
                    sent_stream.flush()
                    continue

                sent_stream.push_text(data)

            sent_stream.end_input()

        async def _synthesize() -> None:
            total_time = 0
            tag_index = 0
            tag_pattern = re.compile(r'\{(.*?)\}')  # Non-greedy match between {}
            from ..voice.io import TimedString

            duration = 0.0
            async for ev in sent_stream:
                total_break_time = 0
                parts = tag_pattern.split(ev.token)
                result_parts = []

                # Cumulative words from the start of this event
                cumulative_words = 0
                total_len = len(parts)
                
                for i, part in enumerate(parts):
                    if i % 2 == 1:  # Odd indices are tags (content inside {})
                        # Calculate time offset for all words before this tag
                        time_for_words = cumulative_words / self._words_per_sec if self._words_per_sec > 0 else 0
                        if (total_len == i+2): # +2 because we are checking for odd only for this block
                            # Reduce the trigger time for the tag at the end of the input so that its always played before the input finishes.
                            total_time = total_time-0.1 if total_time > 0.1 else total_time
                        tag_index += 1
                        clean_text = await self._callback(part, tag_index, total_time + time_for_words + total_break_time)
                        # For <trl-break tags, callback will return changing it to <break tag which we need to include in the text sent out to TTS for synthesis but don't want to count it as a word.
                        if clean_text:
                            result_parts.append(' ' + clean_text + ' ')

                        # Also for trl-break update the duration to delay the tags.
                        break_time = self.get_duration(part.strip())
                        total_break_time = total_break_time + break_time
                    else:
                        # Remove stray curly braces from text parts
                        clean_part = part.replace('{', '').replace('}', '').strip()
                        if clean_part:
                            num_words = len(clean_part.split())
                            cumulative_words += num_words
                            result_parts.append(clean_part)

                joined = ' '.join(result_parts)

                if joined.strip():
                    logger.info(f"Synthesizing - {joined}")
                    
                    output_emitter.push_timed_transcript(
                        TimedString(text=joined, start_time=duration)
                    )

                    if not joined.strip():
                        continue

                    async with self._tts._wrapped_tts.synthesize(
                        joined, conn_options=self._wrapped_tts_conn_options
                    ) as tts_stream:
                        async for audio in tts_stream:
                            total_time = total_time + audio.frame.duration
                            output_emitter.push(audio.frame.data.tobytes())
                            duration += audio.frame.duration
                        output_emitter.flush()
        tasks = [
            asyncio.create_task(_forward_input()),
            asyncio.create_task(_synthesize()),
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            await sent_stream.aclose()
            await utils.aio.cancel_and_wait(*tasks)

