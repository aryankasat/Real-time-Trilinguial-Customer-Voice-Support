import asyncio
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import Frame, TextFrame, EndFrame


class WaitForParticipantProcessor(FrameProcessor):
    """
    Holds downstream TextFrames until a remote participant (the web user)
    has joined the LiveKit room, listening to transport events and polling
    the room object to guarantee instant release upon connection.
    """
    def __init__(self, transport, timeout: float = 15.0):
        super().__init__()
        self.transport = transport
        self.timeout = timeout
        self._participant_joined = False

        try:
            @self.transport.event_handler("on_participant_connected")
            async def on_participant_connected(transport, participant):
                print(f"[WaitForParticipant] Event: participant connected '{participant}'")
                self._participant_joined = True

            @self.transport.event_handler("on_first_participant_joined")
            async def on_first_participant_joined(transport, participant):
                print(f"[WaitForParticipant] Event: first participant joined '{participant}'")
                self._participant_joined = True
        except Exception as e:
            print(f"[WaitForParticipant] Event handler setup notice: {e}")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TextFrame):
            if not self._participant_joined:
                print(f"[WaitForParticipant] Holding TextFrame until user participant joins LiveKit room...")
                elapsed = 0.0
                poll_interval = 0.1

                while elapsed < self.timeout and not self._participant_joined:
                    try:
                        client = getattr(self.transport, "_client", None)
                        if client and client.room:
                            remotes = getattr(client.room, "remote_participants", None)
                            if remotes and len(remotes) > 0:
                                print(f"[WaitForParticipant] Polled {len(remotes)} remote participant(s) in room!")
                                self._participant_joined = True
                                break
                    except Exception:
                        pass

                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval

                if self._participant_joined:
                    print(f"[WaitForParticipant] Participant confirmed! Sleeping 0.5s for WebRTC audio track subscription...")
                    await asyncio.sleep(0.5)
                else:
                    print(f"[WaitForParticipant] No participant detected after {self.timeout}s — proceeding downstream anyway.")

        await self.push_frame(frame, direction)
