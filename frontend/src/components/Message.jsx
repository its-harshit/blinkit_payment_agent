import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const Message = ({ message }) => {
  const isHuman = message.isHuman
  const isStreaming = message.isStreaming

  return (
    <div className={`flex ${isHuman ? 'justify-end' : 'justify-start'} mb-3 px-4 sm:px-0`}>
      <div className={`flex-1 max-w-3xl sm:max-w-5xl ${isHuman ? 'text-right' : ''}`}>
        <div className={`inline-block rounded-2xl px-3 sm:px-4 py-2.5 sm:py-3 max-w-full ${
          isHuman
            ? 'bg-gray-100 text-gray-900 text-lg font-bold'
            : 'bg-white border border-[#D6D6D6] text-gray-900'
        }`}>
          {isStreaming ? (
            <div className="flex items-center gap-2">
              <div className="prose prose-sm max-w-none text-base sm:text-base font-semibold text-gray-900">
                <ReactMarkdown 
                  remarkPlugins={[remarkGfm]}
                  components={{
                    p: ({ children }) => <span className="whitespace-pre-wrap">{children}</span>,
                    strong: ({ children }) => <strong className="font-bold">{children}</strong>,
                    em: ({ children }) => <em className="italic">{children}</em>,
                    code: ({ children }) => <code className="bg-gray-100 px-1 py-0.5 rounded text-sm">{children}</code>,
                    ul: ({ children }) => <ul className="list-disc list-inside my-2">{children}</ul>,
                    ol: ({ children }) => <ol className="list-decimal list-inside my-2">{children}</ol>,
                    li: ({ children }) => <li className="my-1">{children}</li>,
                  }}
                >
                  {message.content}
                </ReactMarkdown>
              </div>
              <span className="streaming-cursor inline-block w-2 h-4 bg-[#26387E]"></span>
            </div>
          ) : (
            <div className="prose prose-sm max-w-none text-base sm:text-base font-semibold text-gray-900">
              <ReactMarkdown 
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ children }) => <p className="whitespace-pre-wrap my-1">{children}</p>,
                  strong: ({ children }) => <strong className="font-bold">{children}</strong>,
                  em: ({ children }) => <em className="italic">{children}</em>,
                  code: ({ children }) => <code className="bg-gray-100 px-1 py-0.5 rounded text-sm font-mono">{children}</code>,
                  pre: ({ children }) => <pre className="bg-gray-100 p-2 rounded overflow-x-auto my-2">{children}</pre>,
                  ul: ({ children }) => <ul className="list-disc list-inside my-2 space-y-1">{children}</ul>,
                  ol: ({ children }) => <ol className="list-decimal list-inside my-2 space-y-1">{children}</ol>,
                  li: ({ children }) => <li className="my-1">{children}</li>,
                  h1: ({ children }) => <h1 className="text-xl font-bold my-2">{children}</h1>,
                  h2: ({ children }) => <h2 className="text-lg font-bold my-2">{children}</h2>,
                  h3: ({ children }) => <h3 className="text-base font-bold my-1">{children}</h3>,
                  blockquote: ({ children }) => <blockquote className="border-l-4 border-gray-300 pl-3 my-2 italic">{children}</blockquote>,
                  table: ({ children }) => <div className="overflow-x-auto my-2"><table className="min-w-full border-collapse border border-gray-300">{children}</table></div>,
                  thead: ({ children }) => <thead className="bg-gray-100">{children}</thead>,
                  tbody: ({ children }) => <tbody>{children}</tbody>,
                  tr: ({ children }) => <tr className="border-b border-gray-200">{children}</tr>,
                  th: ({ children }) => <th className="border border-gray-300 px-2 py-1 text-left font-bold">{children}</th>,
                  td: ({ children }) => <td className="border border-gray-300 px-2 py-1">{children}</td>,
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          )}
          <div className={`text-sm mt-2 ${isHuman ? 'text-right text-gray-500' : 'text-gray-500'}`}>
            {message.timestamp && new Date(message.timestamp).toLocaleTimeString('en-US', { 
              hour: '2-digit', 
              minute: '2-digit' 
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

export default Message
