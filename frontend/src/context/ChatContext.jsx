import React, { createContext, useContext, useState, useCallback } from 'react'
import { chatAPI } from '../services/api'

const ChatContext = createContext()

export const ChatProvider = ({ children }) => {
  const [messages, setMessages] = useState([])
  const [currentChatId, setCurrentChatId] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [streamingMessageId, setStreamingMessageId] = useState(null)

  const createChat = useCallback(async () => {
    try {
      const response = await chatAPI.createChat()
      const chatId = response.data.chat_id
      setCurrentChatId(chatId)
      setMessages([])
      return { success: true, chatId }
    } catch (error) {
      console.error('Error creating chat:', error)
      return { success: false, error: error.message }
    }
  }, [])

  const sendMessage = useCallback(async (message, chatId = null) => {
    let activeChatId = chatId || currentChatId
    
    if (!activeChatId) {
      // Create chat first
      const chatResult = await createChat()
      if (!chatResult.success) {
        console.error('Failed to create chat:', chatResult.error)
        return
      }
      activeChatId = chatResult.chatId
      setCurrentChatId(activeChatId)
    }

    // Add user message
    const userMessage = {
      id: `msg_${Date.now()}`,
      content: message,
      isHuman: true,
      timestamp: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMessage])

    // Create streaming AI message
    const streamingId = `streaming_${Date.now()}`
    const aiMessage = {
      id: streamingId,
      content: '',
      isHuman: false,
      timestamp: new Date().toISOString(),
      isStreaming: true,
      toolResult: null,
    }
    setMessages((prev) => [...prev, aiMessage])
    setIsStreaming(true)
    setStreamingMessageId(streamingId)
    setStreamingContent('')

    try {
      await chatAPI.streamMessage(
        message,
        activeChatId,
        (chunk) => {
          if (chunk.type === 'tool_result') {
            // Handle tool result - store it but keep streaming active
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === streamingId
                  ? { ...msg, toolResult: chunk.data }
                  : msg
              )
            )
          } else if (chunk.type === 'content') {
            // Handle streaming content
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === streamingId
                  ? { ...msg, content: (msg.content || '') + chunk.text }
                  : msg
              )
            )
            setStreamingContent((prev) => prev + chunk.text)
          } else if (chunk.type === 'error') {
            // Handle error
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === streamingId
                  ? { ...msg, content: chunk.message, isStreaming: false }
                  : msg
              )
            )
            setIsStreaming(false)
          }
        }
      )

      // Finalize message
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === streamingId ? { ...msg, isStreaming: false } : msg
        )
      )
    } catch (error) {
      console.error('Error streaming message:', error)
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === streamingId
            ? { ...msg, content: 'Error: Could not get response', isStreaming: false }
            : msg
        )
      )
    } finally {
      setIsStreaming(false)
      setStreamingMessageId(null)
      setStreamingContent('')
    }
  }, [currentChatId, createChat])

  const value = {
    messages,
    currentChatId,
    isLoading,
    isStreaming,
    streamingContent,
    streamingMessageId,
    createChat,
    sendMessage,
    setCurrentChatId,
  }

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

export const useChat = () => {
  const context = useContext(ChatContext)
  if (!context) {
    throw new Error('useChat must be used within a ChatProvider')
  }
  return context
}
