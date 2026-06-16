import { useState, useEffect, type ReactNode } from 'react'
import {
  BarChart3,
  Bot,
  Calendar,
  Clock,
  MessageSquare,
  Pin,
  Search,
  Star,
  ThumbsDown,
  ThumbsUp,
  Timer,
  User,
  Users,
  FileText,
} from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { getAnalytics } from '../../api/analytics'
import { getChatHistory, ChatSession } from '../../api/chatHistory'
import { useData } from '../../hooks/useData'
import { IconHeading, IconText } from '../ui/IconText'

// GMT+3 Palestine timezone formatter
function formatGMT3Date(dateString: string, compact?: boolean): string {
  try {
    const d = new Date(dateString)
    d.setTime(d.getTime() + 3 * 60 * 60 * 1000)
    const day = String(d.getUTCDate()).padStart(2, '0')
    const month = String(d.getUTCMonth() + 1).padStart(2, '0')
    const year = d.getUTCFullYear()
    return compact ? `${day}/${month}` : `${day}/${month}/${year}`
  } catch {
    return dateString
  }
}

/** Narrow viewports: tilt/shorter axis labels so daily chart ticks don’t collide */
function useMobileChartLayout(breakpointPx = 640) {
  const [compact, setCompact] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${breakpointPx - 1}px)`)
    const apply = () => setCompact(mq.matches)
    apply()
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [breakpointPx])
  return compact
}

function MetricCard({ icon, label, value }: { icon: ReactNode; label: string; value: ReactNode }) {
  const valueEl =
    typeof value === 'string' || typeof value === 'number' ? (
      <span className="text-2xl font-bold text-gray-900 tabular-nums leading-tight break-words">{value}</span>
    ) : (
      value
    )

  return (
    <div className="card flex items-start gap-4">
      <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center text-primary flex-shrink-0">
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-gray-500 leading-snug">{label}</p>
        <div className="mt-1 min-w-0 leading-tight">{valueEl}</div>
      </div>
    </div>
  )
}

type FeedbackFilter = 'dislike' | 'like'
type FeedbackSort = 'newest' | 'oldest' | 'session_asc' | 'session_desc'

function previewFeedbackLine(text: string, max = 72): string {
  const t = text.trim()
  if (t.length <= max) return t
  return `${t.slice(0, max)}…`
}

function FeedbackReview({ sessions }: { sessions: ChatSession[] }) {
  const [filter, setFilter] = useState<FeedbackFilter>('dislike')
  const [sort, setSort] = useState<FeedbackSort>('newest')
  const [expandedKey, setExpandedKey] = useState<string | null>(null)

  type FeedbackItem = {
    rowKey: string
    userMsg: string
    botMsg: string
    title: string
    tsRaw: string
    tsDisplay: string
    genTime: number | null
    feedback: string
  }

  const items: FeedbackItem[] = []
  for (const s of sessions) {
    for (let i = 0; i < s.messages.length; i++) {
      const msg = s.messages[i]
      if (msg.role !== 'bot' || msg.feedback !== filter) continue
      const userMsg = i > 0 && s.messages[i - 1].role === 'user' ? s.messages[i - 1].content : 'غير متوفر'
      const tsRaw = msg.timestamp || ''
      const tsDisplay = tsRaw ? tsRaw.slice(0, 16).replace('T', ' ') : '—'
      items.push({
        rowKey: `${s.session_id}:${msg.id}`,
        userMsg,
        botMsg: msg.content,
        title: s.title || s.session_id.slice(0, 15),
        tsRaw,
        tsDisplay,
        genTime: msg.generation_time,
        feedback: msg.feedback ?? '',
      })
    }
  }

  useEffect(() => {
    setExpandedKey(null)
  }, [filter, sort])

  const sorted = [...items].sort((a, b) => {
    if (sort === 'newest') return b.tsRaw.localeCompare(a.tsRaw)
    if (sort === 'oldest') return a.tsRaw.localeCompare(b.tsRaw)
    if (sort === 'session_asc') return a.title.localeCompare(b.title)
    return b.title.localeCompare(a.title)
  })

  return (
    <div>
      <IconHeading as="h3" icon={Search} className="text-base font-semibold text-gray-800 mb-3">
        مراجعة الإجابات المقيمة
      </IconHeading>
      <div className="flex flex-wrap gap-3 mb-4">
        <div className="flex rounded-lg overflow-hidden border border-gray-300">
          <button
            className={`px-4 py-2 text-sm font-medium inline-flex items-center gap-1.5 ${filter === 'dislike' ? 'bg-red-600 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'}`}
            onClick={() => setFilter('dislike')}
          >
            <ThumbsDown className="w-4 h-4" aria-hidden="true" />
            سلبية
          </button>
          <button
            className={`px-4 py-2 text-sm font-medium inline-flex items-center gap-1.5 ${filter === 'like' ? 'bg-green-600 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'}`}
            onClick={() => setFilter('like')}
          >
            <ThumbsUp className="w-4 h-4" aria-hidden="true" />
            إيجابية
          </button>
        </div>
        <select
          className="input text-sm w-auto"
          value={sort}
          onChange={(e) => setSort(e.target.value as FeedbackSort)}
        >
          <option value="newest">الأحدث أولاً</option>
          <option value="oldest">الأقدم أولاً</option>
          <option value="session_asc">حسب المحادثة (أ–ي)</option>
          <option value="session_desc">حسب المحادثة (ي–أ)</option>
        </select>
      </div>

      {sorted.length === 0 ? (
        <p className="text-gray-400 text-center py-6">لا توجد تقييمات مطابقة.</p>
      ) : (
        <div className="space-y-2">
          {sorted.map((item) => {
            const isOpen = expandedKey === item.rowKey
            const borderTone =
              filter === 'dislike' ? 'border-red-200' : 'border-green-200'
            const headerTone =
              filter === 'dislike' ? 'hover:bg-red-50/80' : 'hover:bg-green-50/80'
            const panelTone =
              filter === 'dislike' ? 'bg-red-50/60' : 'bg-green-50/60'
            return (
              <div
                key={item.rowKey}
                className={`border rounded-lg overflow-hidden bg-white ${borderTone}`}
              >
                <button
                  type="button"
                  onClick={() => setExpandedKey(isOpen ? null : item.rowKey)}
                  className={`w-full text-right p-4 flex items-center justify-between gap-3 transition-colors ${headerTone}`}
                >
                  <div className="flex-1 min-w-0 text-right">
                    <p className="text-sm font-medium text-gray-800 truncate inline-flex items-center gap-1.5">
                      <User className="w-4 h-4 text-gray-500 shrink-0" aria-hidden="true" />
                      {previewFeedbackLine(item.userMsg, 88)}
                    </p>
                    <div className="flex flex-wrap gap-2 mt-1 justify-end text-xs text-gray-500">
                      <span className="inline-flex items-center gap-1"><Pin className="w-3.5 h-3.5" aria-hidden="true" />{item.title}</span>
                      <span className="inline-flex items-center gap-1"><Clock className="w-3.5 h-3.5" aria-hidden="true" />{item.tsDisplay}</span>
                      {item.genTime != null && (
                        <span className="inline-flex items-center gap-1">
                          <Timer className="w-3.5 h-3.5" aria-hidden="true" />
                          {item.genTime}ث
                        </span>
                      )}
                      {filter === 'dislike' ? (
                        <ThumbsDown className="w-3.5 h-3.5" aria-label="سلبي" />
                      ) : (
                        <ThumbsUp className="w-3.5 h-3.5" aria-label="إيجابي" />
                      )}
                    </div>
                  </div>
                  <span className="text-gray-400 flex-shrink-0 mr-2">{isOpen ? '▼' : '◀'}</span>
                </button>
                {isOpen && (
                  <div className={`border-t border-gray-100 p-4 space-y-3 ${panelTone}`}>
                    <div>
                      <p className="text-xs font-semibold text-gray-500 mb-1 inline-flex items-center gap-1">
                        <User className="w-3.5 h-3.5" aria-hidden="true" />
                        السؤال
                      </p>
                      <p className="text-sm text-gray-800 whitespace-pre-wrap break-words">{item.userMsg}</p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-gray-500 mb-1 inline-flex items-center gap-1">
                        <Bot className="w-3.5 h-3.5" aria-hidden="true" />
                        {filter === 'dislike' ? (
                          <span className="inline-flex items-center gap-1">الإجابة (<ThumbsDown className="w-3 h-3" aria-hidden="true" />)</span>
                        ) : (
                          <span className="inline-flex items-center gap-1">الإجابة (<ThumbsUp className="w-3 h-3" aria-hidden="true" />)</span>
                        )}
                      </p>
                      <p className="text-sm text-gray-700 whitespace-pre-wrap break-words">{item.botMsg}</p>
                    </div>
                    <div className="flex flex-wrap gap-3 text-xs text-gray-500">
                      <span className="inline-flex items-center gap-1"><Pin className="w-3.5 h-3.5" aria-hidden="true" />{item.title}</span>
                      <span className="inline-flex items-center gap-1"><Clock className="w-3.5 h-3.5" aria-hidden="true" />{item.tsDisplay}</span>
                      {item.genTime != null && (
                        <span className="inline-flex items-center gap-1">
                          <Timer className="w-3.5 h-3.5" aria-hidden="true" />
                          {item.genTime}ث
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function KPIDashboard() {
  const { data: analytics, loading: aLoading, error: aError } = useData(getAnalytics)
  const { data: sessions, loading: sLoading } = useData(getChatHistory)
  const chartCompact = useMobileChartLayout(640)

  const csat = analytics
    ? analytics.likes + analytics.dislikes > 0
      ? Math.round((analytics.likes / (analytics.likes + analytics.dislikes)) * 100)
      : 0
    : 0

  const dailyChartData = analytics
    ? Object.entries(analytics.daily_chats)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([date, count]) => ({ date, count }))
    : []

  return (
    <div className="space-y-6">
      {aLoading && <p className="text-gray-500 text-center py-8">جاري تحميل المؤشرات...</p>}
      {aError && <p className="text-red-600 text-center py-4">تعذر جلب بيانات المؤشرات.</p>}

      {analytics && (
        <>
          {/* KPI cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
            <MetricCard icon={<MessageSquare className="w-6 h-6" aria-hidden="true" />} label="إجمالي المحادثات" value={analytics.total_sessions} />
            <MetricCard icon={<FileText className="w-6 h-6" aria-hidden="true" />} label="إجمالي الرسائل" value={analytics.total_messages} />
            <MetricCard
              icon={<Users className="w-6 h-6" aria-hidden="true" />}
              label="المستخدمون النشطون"
              value={analytics.unique_users ?? 0}
            />
            <MetricCard
              icon={<Star className="w-6 h-6" aria-hidden="true" />}
              label="نسبة الرضا"
              value={
                <span className="flex flex-nowrap items-center gap-x-1.5 text-gray-900 min-w-0">
                  <span className="text-lg sm:text-xl font-bold tabular-nums shrink-0">{csat}%</span>
                  <span className="text-[11px] sm:text-xs font-semibold text-gray-700 tabular-nums whitespace-nowrap shrink min-w-0">
                    {analytics.likes} <ThumbsUp className="w-3.5 h-3.5 inline" aria-hidden="true" />{' '}
                    <span className="mx-0.5 font-normal text-gray-400">|</span>{' '}
                    {analytics.dislikes} <ThumbsDown className="w-3.5 h-3.5 inline" aria-hidden="true" />
                  </span>
                </span>
              }
            />
            <MetricCard icon={<Timer className="w-6 h-6" aria-hidden="true" />} label="متوسط الاستجابة (ث)" value={analytics.avg_response_time} />
          </div>

          {/* Professional bar chart with GMT+3 dates */}
          <div className="card">
            <IconHeading as="h3" icon={BarChart3} className="text-base font-semibold text-gray-800 mb-4">
              عدد المحادثات اليومية
            </IconHeading>
            {dailyChartData.length === 0 ? (
              <p className="text-gray-400 text-center py-6">لا توجد بيانات كافية لعرض الرسم البياني.</p>
            ) : (
              <ResponsiveContainer width="100%" height={chartCompact ? 380 : 400}>
                <BarChart
                  data={dailyChartData}
                  margin={{
                    top: 12,
                    right: chartCompact ? 6 : 30,
                    left: 0,
                    bottom: chartCompact ? 44 : 60,
                  }}
                >
                  <defs>
                    <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#059669" stopOpacity={1}/>
                      <stop offset="100%" stopColor="#047857" stopOpacity={1}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tick={{
                      fontSize: chartCompact ? 10 : 13,
                      fill: '#374151',
                      fontWeight: 600,
                    }}
                    angle={0}
                    textAnchor="middle"
                    height={chartCompact ? 56 : 80}
                    tickMargin={chartCompact ? 10 : 10}
                    minTickGap={chartCompact ? 30 : 12}
                    interval={
                      chartCompact ? 'preserveStartEnd' : Math.max(0, Math.ceil(dailyChartData.length / 6) - 1)
                    }
                    tickFormatter={(value) => formatGMT3Date(`${value}T00:00:00`, chartCompact)}
                    axisLine={{ stroke: '#d1d5db' }}
                  />
                  <YAxis
                    tick={{ fontSize: chartCompact ? 10 : 12, fill: '#6b7280', fontWeight: 500 }}
                    allowDecimals={false}
                    axisLine={false}
                    tickLine={false}
                    width={chartCompact ? 28 : 40}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'rgba(255, 255, 255, 0.98)',
                      border: '2px solid #059669',
                      borderRadius: '10px',
                      boxShadow: '0 8px 24px rgba(0, 0, 0, 0.12)',
                      padding: '10px 14px'
                    }}
                    formatter={(value) => [`${value} محادثة`, 'العدد']}
                    labelFormatter={(label) => formatGMT3Date(`${label}T00:00:00`, false)}
                    cursor={{ fill: 'rgba(5, 150, 105, 0.1)' }}
                  />
                  <Legend wrapperStyle={{ paddingTop: chartCompact ? '8px' : '20px' }} />
                  <Bar
                    dataKey="count"
                    fill="url(#barGradient)"
                    radius={[8, 8, 0, 0]}
                    isAnimationActive={true}
                    animationDuration={1000}
                    name="المحادثات اليومية"
                    maxBarSize={chartCompact ? 28 : 40}
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </>
      )}

      {/* Feedback review */}
      <div className="card">
        {sLoading ? (
          <p className="text-gray-500 text-center py-6">جاري تحميل التقييمات...</p>
        ) : sessions ? (
          <FeedbackReview sessions={sessions} />
        ) : (
          <p className="text-red-600 text-center py-4">تعذر جلب بيانات التقييمات.</p>
        )}
      </div>
    </div>
  )
}
