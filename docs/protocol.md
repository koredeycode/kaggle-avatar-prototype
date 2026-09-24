# WebSocket protocol

The first client message is:

```json
{"type":"auth","protocol":1,"token":"runtime-token","client":"browser"}
```

The server returns a `ready` event containing the session ID, epoch, capture wire format, and capabilities. Binary input is raw mono PCM16LE at the browser capture rate. Binary output uses the `AV` header defined in `src/avatar_prototype/protocol.py`.

The output header contains:

- Protocol and audio type.
- Flags and session epoch.
- Response, turn, and segment UUIDs.
- Media sequence.
- Sample rate and channel count.
- Payload length.

Clients must reject frames from an old epoch or response. Reliable JSON events and replaceable avatar/caption events have separate recovery rules. A client acknowledgement is a conservative playout checkpoint, not proof of physical speaker output.
