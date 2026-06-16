import { useState } from 'react'
import {
  Bot,
  MessageSquare,
  RefreshCw,
  Search,
  ThumbsDown,
  ThumbsUp,
  Timer,
  Trash2,
} from 'lucide-react'
import { getChatHistory, deleteSession, ChatSession } from '../../api/chatHistory'
import { useData } from '../../hooks/useData'
import { IconHeading, IconText } from '../ui/IconText'

type SortOption = 'newest' | 'oldest' | 'last_updated' | 'oldest_updated' | 'title_asc' | 'title_desc'

function toMs(ts: string | null): number {
  if (!ts) return 0
  const safe = ts.includes('Z') || ts.includes('+') ? ts : ts.replace(' ', 'T') + 'Z'
  const ms = new Date(safe).getTime()
  return isNaN(ms) ? 0 : ms
}

function sortSessions(sessions: ChatSession[], sort: SortOption): ChatSession[] {
  const list = [...sessions]
  switch (sort) {
    case 'newest':         return list.sort((a, b) => toMs(b.start_time) - toMs(a.start_time))
    case 'oldest':         return list.sort((a, b) => toMs(a.start_time) - toMs(b.start_time))
    case 'last_updated':   return list.sort((a, b) => toMs(b.last_message_time ?? b.start_time) - toMs(a.last_message_time ?? a.start_time))
    case 'oldest_updated': return list.sort((a, b) => toMs(a.last_message_time ?? a.start_time) - toMs(b.last_message_time ?? b.start_time))
    case 'title_asc':      return list.sort((a, b) => a.title.localeCompare(b.title))
    case 'title_desc':     return list.sort((a, b) => b.title.localeCompare(a.title))
  }
}

function formatTime(ts: string | null): string {
  if (!ts) return '—'
  const safeTs = ts.includes('Z') || ts.includes('+') ? ts : ts.replace(' ', 'T') + 'Z'
  try { return new Date(safeTs).toLocaleString('ar-SA', { timeZone: 'Asia/Hebron' }) } catch { return ts }
}

function formatShortTime(ts: string | null): string {
  if (!ts) return ''
  const safeTs = ts.includes('Z') || ts.includes('+') ? ts : ts.replace(' ', 'T') + 'Z'
  try { return new Date(safeTs).toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Hebron' }) } catch { return ts }
}

export default function ChatHistory() {
  const { data: sessions, loading, error, refresh } = useData(getChatHistory)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<SortOption>('newest')
  const [selected, setSelected] = useState<ChatSession | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteMsg, setDeleteMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const q = search.trim().toLowerCase()
  const filtered = sortSessions(
    (sessions ?? []).filter((s) =>
      !q ||
      s.title.toLowerCase().includes(q) ||
      s.session_id.toLowerCase().includes(q) ||
      s.messages.slice(0, 20).some((m) => m.content.toLowerCase().includes(q))
    ),
    sort
  )

  const handleDelete = async () => {
    if (!selected) return
    setDeleting(true)
    try {
      await deleteSession(selected.session_id)
      setDeleteMsg({ type: 'success', text: 'تم حذف المحادثة بنجاح.' })
      setSelected(null)
      refresh()
    } catch {
      setDeleteMsg({ type: 'error', text: 'تعذر حذف المحادثة.' })
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="space-y-5">
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <IconHeading icon={MessageSquare} className="text-lg font-semibold text-gray-800">
            سجل المحادثات
          </IconHeading>
          <button onClick={refresh} className="btn-secondary text-sm py-1.5 px-3 inline-flex items-center gap-1.5">
            <RefreshCw className="w-4 h-4" aria-hidden="true" />
            تحديث
          </button>
        </div>

        {/* Search & sort */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
          <div className="relative">
            <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" aria-hidden="true" />
            <input
              type="text"
              className="input text-sm pr-9"
              placeholder="بحث في المحادثات..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select className="input text-sm" value={sort} onChange={(e) => setSort(e.target.value as SortOption)}>
            <option value="newest">الأحدث إنشاءً</option>
            <option value="oldest">الأقدم إنشاءً</option>
            <option value="last_updated">أحدث نشاط</option>
            <option value="oldest_updated">أقدم نشاط</option>
            <option value="title_asc">حسب العنوان (أ–ي)</option>
            <option value="title_desc">حسب العنوان (ي–أ)</option>
          </select>
        </div>

        {loading && <p className="text-gray-500 text-center py-8">جاري التحميل...</p>}
        {error && <p className="text-red-600 text-center py-8">تعذر جلب سجل المحادثات.</p>}
        {!loading && !error && filtered.length === 0 && (
          <p className="text-gray-400 text-center py-8">لا توجد محادثات.</p>
        )}

        <div className="space-y-3 max-h-[700px] overflow-y-auto pr-2">
          {filtered.map((s) => {
            const isExpanded = selected?.session_id === s.session_id;
            return (
              <div key={s.session_id} className={`border rounded-xl transition-all ${isExpanded ? 'border-primary shadow-sm bg-white' : 'border-gray-200 bg-white hover:bg-gray-50'}`}>
                <button
                  onClick={() => {
                    if (isExpanded) {
                      setSelected(null);
                    } else {
                      setSelected(s);
                      setDeleteMsg(null);
                    }
                  }}
                  className="w-full text-right p-4 flex items-center justify-between"
                >
                  <div>
                    <p className="font-medium text-gray-800 text-sm truncate">{s.title || s.session_id}</p>
                    <p className="text-xs text-gray-500 mt-1">{formatTime(s.start_time)} · {s.messages.length} رسالة</p>
                  </div>
                  <span className={`transform transition-transform text-gray-400 text-xs ${isExpanded ? 'rotate-180' : ''}`}>
                    ▼
                  </span>
                </button>

                {isExpanded && (
                  <div className="border-t border-gray-100 p-4 bg-gray-50/50 rounded-b-xl">
                    <div className="flex justify-end mb-4">
                      <button
                        onClick={handleDelete}
                        disabled={deleting}
                        className="btn-danger text-xs py-1 px-2 inline-flex items-center gap-1"
                      >
                        {deleting ? 'جاري الحذف...' : <IconText icon={Trash2} iconClassName="w-3.5 h-3.5">حذف المحادثة</IconText>}
                      </button>
                    </div>

                    {deleteMsg && (
                      <div className={`mb-4 px-4 py-2 rounded-lg text-sm ${
                        deleteMsg.type === 'success' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'
                      }`}>
                        {deleteMsg.text}
                      </div>
                    )}

                    <div className="space-y-4 max-h-[400px] overflow-y-auto pr-1">
                      {[...s.messages].sort((a, b) => a.id - b.id).map((msg) => (
                        <div
                          key={msg.id}
                          className={`flex items-end gap-2 ${msg.role === 'user' ? 'justify-start' : 'justify-end'}`}
                        >
                          {/* Bot avatar on left - only for bot messages */}
                          {msg.role === 'bot' && (
                            <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 order-last">
                              <Bot className="w-4 h-4 text-primary" aria-hidden="true" />
                            </div>
                          )}
                          
                          {/* Message bubble */}
                          <div className={`max-w-[75%] px-4 py-3 rounded-2xl text-sm ${
                            msg.role === 'user'
                              ? 'bg-primary text-white rounded-br-none'
                              : 'bg-white border border-gray-100 text-gray-800 rounded-bl-none shadow-sm'
                          }`}>
                            <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                            <div className={`flex items-center gap-2 mt-1.5 text-xs opacity-70 flex-wrap ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                              {msg.timestamp && <span>{formatShortTime(msg.timestamp)}</span>}
                              {msg.generation_time != null && (
                                <span className="inline-flex items-center gap-1">
                                  <Timer className="w-3.5 h-3.5" aria-hidden="true" />
                                  {msg.generation_time}ث
                                </span>
                              )}
                              {msg.feedback === 'like' && <ThumbsUp className="w-3.5 h-3.5" aria-label="إيجابي" />}
                              {msg.feedback === 'dislike' && <ThumbsDown className="w-3.5 h-3.5" aria-label="سلبي" />}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  )
}
