import { useState, useRef, useEffect, forwardRef, useImperativeHandle } from 'react'
import ReactMarkdown from 'react-markdown'
import api from '../services/api'
import './ChatBot.css'

const WELCOME = "Hi, I'm Stella — your fashion trend expert. Ask me anything about the trends you're seeing, or ask me to explain a chart, compare keywords, or spot opportunities."

const ChatBot = forwardRef(function ChatBot({ context }, ref) {
  const [open, setOpen] = useState(false)

  useImperativeHandle(ref, () => ({
    open: () => setOpen(true),
  }))
  const [messages, setMessages] = useState([])
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  // Load history once on mount
  useEffect(() => {
    api.get('/chat/history').then(res => {
      const history = res.data.messages || []
      setMessages(history.length > 0 ? history : [{ role: 'assistant', content: WELCOME }])
    }).catch(() => {
      setMessages([{ role: 'assistant', content: WELCOME }])
    }).finally(() => setHistoryLoaded(true))
  }, [])

  useEffect(() => {
    if (open) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [open, messages])

  const handleClearHistory = async () => {
    await api.delete('/chat/history').catch(() => {})
    setMessages([{ role: 'assistant', content: WELCOME }])
  }

  const send = async () => {
    const text = input.trim()
    if (!text || loading) return

    const userMsg = { role: 'user', content: text }
    const nextMessages = [...messages, userMsg]
    setMessages(nextMessages)
    setInput('')
    setLoading(true)

    try {
      const res = await api.post('/chat', {
        messages: nextMessages.map(m => ({ role: m.role, content: m.content })),
        context,
      })
      setMessages(prev => [...prev, { role: 'assistant', content: res.data.reply }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: "Sorry, I couldn't connect right now. Try again in a moment." }])
    } finally {
      setLoading(false)
    }
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <>
      {/* Floating button */}
      <button
        className={`chatbot-fab ${open ? 'chatbot-fab--open' : ''}`}
        onClick={() => setOpen(v => !v)}
        title="Ask Stella"
      >
        {open ? '✕' : '✦'}
        {!open && <span className="chatbot-fab__label">Ask Stella</span>}
      </button>

      {/* Chat panel */}
      {open && (
        <div className="chatbot-panel">
          <div className="chatbot-header">
            <div className="chatbot-header__info">
              <span className="chatbot-header__avatar">✦</span>
              <div>
                <div className="chatbot-header__name">Stella</div>
                <div className="chatbot-header__role">Fashion Trend Expert</div>
              </div>
            </div>
            <div className="chatbot-header__actions">
              <button className="chatbot-header__clear" onClick={handleClearHistory} title="Clear chat history">Clear</button>
              <button className="chatbot-header__close" onClick={() => setOpen(false)}>✕</button>
            </div>
          </div>

          <div className="chatbot-messages">
            {messages.map((msg, i) => (
              <div key={i} className={`chatbot-msg chatbot-msg--${msg.role}`}>
                <div className="chatbot-msg__bubble">
                  {msg.role === 'assistant' ? (
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  ) : (
                    msg.content.split('\n').map((line, j) => (
                      <span key={j}>{line}{j < msg.content.split('\n').length - 1 && <br />}</span>
                    ))
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="chatbot-msg chatbot-msg--assistant">
                <div className="chatbot-msg__bubble chatbot-msg__bubble--typing">
                  <span /><span /><span />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="chatbot-input-row">
            <textarea
              ref={inputRef}
              className="chatbot-input"
              placeholder="Ask about trends, charts, suggestions..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKey}
              rows={1}
              disabled={loading}
            />
            <button
              className="chatbot-send"
              onClick={send}
              disabled={!input.trim() || loading}
            >
              ↑
            </button>
          </div>
        </div>
      )}
    </>
  )
})

export default ChatBot
