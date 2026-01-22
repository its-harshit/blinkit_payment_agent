import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export default api

// Auth API
export const authAPI = {
  login: (mobileNumber) => api.post('/auth/login', { mobile_number: mobileNumber }),
  verifyOTP: (mobileNumber, otp) => api.post('/auth/verify-otp', { mobile_number: mobileNumber, otp }),
}

// Chat API
export const chatAPI = {
  createChat: () => api.post('/api/chat/create'),
  getMessages: (chatId) => api.get(`/api/chat/${chatId}/messages`),
  streamMessage: async (message, chatId, onChunk) => {
    const token = localStorage.getItem('access_token')
    const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({ message, chat_id: chatId }),
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value)
      const lines = chunk.split('\n')

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            onChunk(data)
          } catch (e) {
            console.error('Error parsing chunk:', e)
          }
        }
      }
    }
  },
}
