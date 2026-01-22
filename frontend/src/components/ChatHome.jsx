import { useState, useEffect, useRef } from 'react'
import { useChat } from '../context/ChatContext'
import { useAuth } from '../context/AuthContext'
import { Send, Search } from 'lucide-react'
import Message from './Message'
import Dashboard from './Dashboard'

const ChatHome = () => {
  const { messages, currentChatId, sendMessage, createChat, isStreaming } = useChat()
  const { logout } = useAuth()
  const [inputValue, setInputValue] = useState('')
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const initializationRef = useRef(false)

  // Auto-create chat and send first message when component loads
  useEffect(() => {
    // Use ref to prevent multiple initializations (handles React StrictMode double execution)
    if (initializationRef.current) return
    if (currentChatId) return // Already have a chat, don't initialize again
    
    initializationRef.current = true
    const initializeChat = async () => {
      const result = await createChat()
      // if (result.success) {
      //   // Wait a bit for UI to load, then send first message
      //   setTimeout(() => {
      //     sendMessage('show my payment details', result.chatId)
      //   }, 500)
      // }
    }
    initializeChat()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // Empty deps - only run once on mount

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Auto-focus input after messages load
  useEffect(() => {
    if (messages.length > 0 && !messages[messages.length - 1]?.isStreaming) {
      setTimeout(() => {
        inputRef.current?.focus()
      }, 100)
    }
  }, [messages])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (inputValue.trim() && !isStreaming) {
      const messageText = inputValue.trim()
      setInputValue('')
      await sendMessage(messageText, currentChatId)
    }
  }

  return (
    <div className="relative h-screen overflow-hidden" style={{ fontFamily: 'Figtree, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif' }}>
      {/* Soft orange-white-green gradient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-orange-80 via-white to-green-80" />

      <div className="relative flex flex-col h-full">
        {/* Header */}
        <div className="flex-shrink-0 bg-white border-b border-[#D6D6D6] px-4 sm:px-6 py-3 sm:py-4 flex items-center justify-between z-10 shadow-sm">
        <h1 className="text-lg sm:text-xl font-semibold text-[#26387E]">Chat Agent POC</h1>
        <button
          onClick={logout}
          className="px-3 sm:px-4 py-2 text-sm text-gray-600 hover:text-[#26387E] transition-colors"
        >
          Logout
        </button>
        </div>

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto px-0 sm:px-4 py-4" style={{ minHeight: 0 }}>
          <div className="max-w-4xl mx-auto w-full space-y-3">
            {messages.length === 0 && !initializationRef.current ? (
              <div className="text-center py-12">
                <div className="typing-indicator justify-center mb-4">
                  <div className="typing-dot"></div>
                  <div className="typing-dot" style={{ animationDelay: '0.2s' }}></div>
                  <div className="typing-dot" style={{ animationDelay: '0.4s' }}></div>
                </div>
                <p className="text-gray-500">Loading chat...</p>
              </div>
            ) : (
              <>
                {messages.map((message) => (
                  <div key={message.id}>
                    <Message message={message} />
                    {message.toolResult && !message.isStreaming && (
                      <Dashboard data={message.toolResult} />
                    )}
                  </div>
                ))}
                {isStreaming && (
                  <div className="flex justify-start mb-4">
                    <div className="flex-1 max-w-5xl">
                      <div className="inline-block px-4 py-3 max-w-full text-gray-800">
                        <div className="typing-indicator">
                          <div className="typing-dot"></div>
                          <div className="typing-dot" style={{ animationDelay: '0.2s' }}></div>
                          <div className="typing-dot" style={{ animationDelay: '0.4s' }}></div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Area - Similar to griev_ui2 */}
        <div className="flex-shrink-0 bg-white border-t border-gray-200 px-4 py-3 sm:pb-4 sm:px-6 z-10">
          <div className="max-w-4xl mx-auto">
            <form onSubmit={handleSubmit}>
              <div 
                className="bg-white border border-[#D6DCE1] cursor-text transition-all duration-200 flex items-center rounded-full px-3 sm:px-4 py-2 sm:py-3 gap-2 sm:gap-3"
                onClick={() => inputRef.current?.focus()}
              >
                <Search className="w-4 h-4 sm:w-5 sm:h-5 text-black flex-shrink-0" />
                <input
                  ref={inputRef}
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder="Type your query here..."
                  className="flex-1 min-w-0 text-xs sm:text-base text-[#626262] placeholder-[#626262] focus:outline-none bg-transparent"
                  disabled={isStreaming}
                />
                <button
                  type="submit"
                  disabled={!inputValue.trim() || isStreaming}
                  className={`py-2 sm:py-3 px-4 sm:px-6 rounded-full hover:shadow-lg transition-all duration-200 flex items-center justify-center font-medium text-xs sm:text-sm text-white overflow-hidden ${
                    !inputValue.trim() || isStreaming
                      ? 'bg-gray-300 cursor-not-allowed' 
                      : 'bg-gradient-to-r from-[#E55C11] to-[#F47920]'
                  }`}
                >
                  {isStreaming ? (
                    <div className="w-4 h-4 sm:w-5 sm:h-5 flex items-center justify-center">
                      <div className="typing-indicator">
                        <div className="typing-dot" style={{ width: '4px', height: '4px', backgroundColor: 'white' }}></div>
                        <div className="typing-dot" style={{ width: '4px', height: '4px', backgroundColor: 'white', animationDelay: '0.2s' }}></div>
                        <div className="typing-dot" style={{ width: '4px', height: '4px', backgroundColor: 'white', animationDelay: '0.4s' }}></div>
                      </div>
                    </div>
                  ) : (
                    <Send className="w-4 h-4 sm:w-5 sm:h-5 text-white -ml-0.5" />
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ChatHome
