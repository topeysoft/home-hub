/* A moving picture from a camera, best way first. WebRTC: the brain relays our offer to HA's go2rtc and
   the video comes straight from it. Motion JPEG: the brain passes HA's stream through an <img>. Each
   attempt reports once, playing or failed; the viewer decides what to try next. */
export type Live = { stop(): void }
const WAIT = 12000   // ms before an attempt that has shown nothing is given up on

export function webrtc(id: string, video: HTMLVideoElement, on: { playing(): void; failed(why: string): void }): Live {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/devices/${encodeURIComponent(id)}/webrtc`)
  const stream = new MediaStream()
  let pc: RTCPeerConnection | null = null, ended = false, played = false, remote = false
  const held: RTCIceCandidateInit[] = []     // HA's candidates that arrive before its answer
  const stop = () => { clearTimeout(timer); video.onplaying = null; pc?.close(); pc = null; if (ws.readyState < 2) ws.close(); video.srcObject = null }
  const fail = (why: string) => { if (ended) return; ended = true; stop(); on.failed(why) }   // also after playing: a picture that stops is a failure too
  const timer = setTimeout(() => fail('timeout'), WAIT)
  video.onplaying = () => { if (ended || played) return; played = true; clearTimeout(timer); on.playing() }
  ws.onmessage = async (e) => {
    const m = JSON.parse(e.data)
    try {
      if (m.type === 'config') {
        pc = new RTCPeerConnection({ iceServers: m.configuration?.iceServers ?? [] })
        pc.addTransceiver('video', { direction: 'recvonly' })
        pc.addTransceiver('audio', { direction: 'recvonly' })
        pc.ontrack = (ev) => { stream.addTrack(ev.track); if (!video.srcObject) video.srcObject = stream }
        pc.onicecandidate = (ev) => { if (ev.candidate && ws.readyState === 1) ws.send(JSON.stringify({ type: 'candidate', candidate: ev.candidate.toJSON() })) }
        pc.onconnectionstatechange = () => { if (pc && (pc.connectionState === 'failed' || pc.connectionState === 'closed')) fail(pc.connectionState) }
        const offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        ws.send(JSON.stringify({ type: 'offer', offer: offer.sdp }))
      } else if (m.type === 'answer' && pc) {
        await pc.setRemoteDescription({ type: 'answer', sdp: m.answer })
        remote = true
        for (const c of held.splice(0)) await pc.addIceCandidate(c)
      } else if (m.type === 'candidate' && pc) {
        if (remote) await pc.addIceCandidate(m.candidate); else held.push(m.candidate)
      } else if (m.type === 'error') fail(m.message || m.code || 'error')
    } catch (err) { fail(String(err)) }
  }
  ws.onerror = () => fail('socket')
  ws.onclose = () => fail('closed')      // the brain ends HA's session with the socket, so a drop is the end of the picture
  return { stop: () => { ended = true; stop() } }
}

export function mjpeg(id: string, img: HTMLImageElement, on: { playing(): void; failed(why: string): void }): Live {
  let ended = false, played = false
  const stop = () => { clearTimeout(timer); clearInterval(poll); img.onerror = null; img.removeAttribute('src') }
  const fail = (why: string) => { if (ended) return; ended = true; stop(); on.failed(why) }
  const timer = setTimeout(() => fail('timeout'), WAIT)
  // load never fires reliably for a stream that has no end; a first frame does give the image a size.
  const poll = setInterval(() => { if (!ended && !played && img.naturalWidth > 0) { played = true; clearTimeout(timer); clearInterval(poll); on.playing() } }, 300)
  img.onerror = () => fail('error')
  img.src = `/devices/${encodeURIComponent(id)}/stream?t=${Date.now()}`
  return { stop: () => { ended = true; stop() } }
}
