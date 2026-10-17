<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const roomId = route.params.id || 'test-room'

// Состояние
const isHost = ref(true)               // пока хардкод, потом из API
const isConnected = ref(false)
const isSharing = ref(false)
const participants = ref([])
const localVideo = ref(null)
const remoteVideos = ref([])           // массив { id, stream }

let ws = null
let localStream = null
let peerConnections = {}               // userId -> RTCPeerConnection

// ====================== WebSocket ======================
function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${protocol}://${window.location.host}/ws/room/${roomId}`

  ws = new WebSocket(url)

  ws.onopen = () => {
    isConnected.value = true
    console.log('WebSocket подключён')
  }

  ws.onmessage = async (event) => {
    const data = JSON.parse(event.data)
    console.log('WS сообщение:', data)

    switch (data.type) {
      case 'user-joined':
      case 'user-left':
        participants.value = data.participants || []
        break

      case 'offer':
        await handleOffer(data)
        break

      case 'answer':
        await handleAnswer(data)
        break

      case 'ice-candidate':
        await handleIceCandidate(data)
        break
    }
  }

  ws.onclose = () => {
    isConnected.value = false
    console.log('WebSocket отключён')
  }
}

function send(data) {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data))
  }
}

// ====================== WebRTC ======================
function createPeerConnection(userId) {
  const pc = new RTCPeerConnection({
    iceServers: [
      { urls: 'stun:stun.l.google.com:19302' },
      // Потом можно добавить свой TURN
    ]
  })

  // Добавляем локальные треки (экран)
  if (localStream) {
    localStream.getTracks().forEach(track => {
      pc.addTrack(track, localStream)
    })
  }

  pc.onicecandidate = (event) => {
    if (event.candidate) {
      send({
        type: 'ice-candidate',
        candidate: event.candidate,
        to: userId
      })
    }
  }

  pc.ontrack = (event) => {
    console.log('Получили удалённый поток от', userId)
    const stream = event.streams[0]

    // Добавляем в список, если ещё нет
    const exists = remoteVideos.value.find(v => v.id === userId)
    if (!exists) {
      remoteVideos.value.push({ id: userId, stream })
    }
  }

  peerConnections[userId] = pc
  return pc
}

// Ведущий начинает трансляцию экрана
async function startScreenShare() {
  try {
    localStream = await navigator.mediaDevices.getDisplayMedia({
      video: {
        cursor: 'always',
        displaySurface: 'monitor' // или 'window'
      },
      audio: true
    })

    isSharing.value = true

    // Показываем себе
    await nextTick()
    if (localVideo.value) {
      localVideo.value.srcObject = localStream
    }

    // Когда пользователь нажимает "Остановить доступ" в браузере
    localStream.getVideoTracks()[0].onended = () => {
      stopScreenShare()
    }

    // Создаём offer для всех текущих участников
    for (const user of participants.value) {
      if (user.user_id) {
        await createAndSendOffer(user.user_id)
      }
    }

  } catch (err) {
    console.error('Ошибка захвата экрана:', err)
    alert('Не удалось начать трансляцию экрана')
  }
}

function stopScreenShare() {
  if (localStream) {
    localStream.getTracks().forEach(track => track.stop())
    localStream = null
  }
  isSharing.value = false
  if (localVideo.value) {
    localVideo.value.srcObject = null
  }
}

async function createAndSendOffer(userId) {
  const pc = createPeerConnection(userId)
  const offer = await pc.createOffer()
  await pc.setLocalDescription(offer)

  send({
    type: 'offer',
    sdp: offer,
    to: userId
  })
}

async function handleOffer(data) {
  const fromUser = data.from_user || data.from
  const pc = createPeerConnection(fromUser)

  await pc.setRemoteDescription(new RTCSessionDescription(data.sdp))
  const answer = await pc.createAnswer()
  await pc.setLocalDescription(answer)

  send({
    type: 'answer',
    sdp: answer,
    to: fromUser
  })
}

async function handleAnswer(data) {
  const fromUser = data.from_user || data.from
  const pc = peerConnections[fromUser]
  if (pc) {
    await pc.setRemoteDescription(new RTCSessionDescription(data.sdp))
  }
}

async function handleIceCandidate(data) {
  const fromUser = data.from_user || data.from
  const pc = peerConnections[fromUser]
  if (pc && data.candidate) {
    try {
      await pc.addIceCandidate(new RTCIceCandidate(data.candidate))
    } catch (err) {
      console.error('Ошибка ICE:', err)
    }
  }
}

// ====================== Жизненный цикл ======================
onMounted(() => {
  connectWebSocket()
})

onUnmounted(() => {
  stopScreenShare()
  ws?.close()
  Object.values(peerConnections).forEach(pc => pc.close())
})
</script>

<template>
  <div class="room-container">
    <!-- Статус -->
    <div class="status-bar">
      <span :class="['badge', isConnected ? 'bg-success' : 'bg-danger']">
        {{ isConnected ? 'Подключён' : 'Отключён' }}
      </span>
      <span class="ms-3">Комната: {{ roomId }}</span>
    </div>

    <div class="main-content">
      <!-- Видео-зона -->
      <div class="video-area">
        <!-- Локальный экран (ведущий) -->
        <div v-if="isHost" class="video-box local">
          <video ref="localVideo" autoplay muted playsinline></video>
          <div class="label">Ваш экран</div>
        </div>

        <!-- Удалённые экраны -->
        <div
          v-for="item in remoteVideos"
          :key="item.id"
          class="video-box remote"
        >
          <video
            :ref="el => { if (el) el.srcObject = item.stream }"
            autoplay
            playsinline
          ></video>
          <div class="label">Участник {{ item.id }}</div>
        </div>

        <div v-if="!isSharing && remoteVideos.length === 0" class="placeholder">
          Ожидание трансляции...
        </div>
      </div>

      <!-- Боковая панель -->
      <div class="sidebar">
        <h4>Участники ({{ participants.length }})</h4>
        <ul class="participants-list">
          <li v-for="(p, index) in participants" :key="index">
            {{ p.username || 'Гость' }}
            <span v-if="p.hand_raised">✋</span>
          </li>
        </ul>

        <div class="controls mt-4">
          <button
            v-if="isHost && !isSharing"
            class="btn btn-primary w-100 mb-2"
            @click="startScreenShare"
          >
            Начать трансляцию экрана
          </button>

          <button
            v-if="isHost && isSharing"
            class="btn btn-danger w-100 mb-2"
            @click="stopScreenShare"
          >
            Остановить трансляцию
          </button>

          <button
            v-if="!isHost"
            class="btn btn-outline-secondary w-100"
            disabled
          >
            Поднять руку (скоро)
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.room-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #1a1a1a;
  color: #fff;
}

.status-bar {
  padding: 10px 20px;
  background: #2d2d2d;
  display: flex;
  align-items: center;
}

.main-content {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.video-area {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 16px;
  align-content: flex-start;
  overflow-y: auto;
}

.video-box {
  position: relative;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
  width: 48%;
  min-width: 320px;
  aspect-ratio: 16/9;
}

.video-box video {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.video-box .label {
  position: absolute;
  bottom: 8px;
  left: 8px;
  background: rgba(0,0,0,0.7);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 13px;
}

.placeholder {
  width: 100%;
  text-align: center;
  padding-top: 100px;
  color: #888;
  font-size: 18px;
}

.sidebar {
  width: 280px;
  background: #252525;
  padding: 20px;
  border-left: 1px solid #333;
}

.participants-list {
  list-style: none;
  padding: 0;
  margin: 12px 0;
}

.participants-list li {
  padding: 8px 0;
  border-bottom: 1px solid #333;
}
</style>
