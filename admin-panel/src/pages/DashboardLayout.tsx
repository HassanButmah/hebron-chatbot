import { useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  BarChart3,
  Bot,
  Brain,
  FolderOpen,
  HelpCircle,
  LogOut,
  Menu,
  MessageSquare,
  Puzzle,
  Radio,
  Settings,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import FileManager from "../components/files/FileManager";
import StaleDocuments from "../components/files/StaleDocuments";
import KPIDashboard from "../components/dashboard/KPIDashboard";
import ChatHistory from "../components/chat/ChatHistory";
import FAQManager from "../components/faqs/FAQManager";
import UnansweredQueries from "../components/unanswered/UnansweredQueries";
import OverrideManager from "../components/overrides/OverrideManager";
import AISettings from "../components/settings/AISettings";
import LLMSettings from "../components/settings/LLMSettings";
import DynamicSourcesManager from "../components/dynamic/DynamicSourcesManager";

const TABS: { id: TabId; label: string; Icon: LucideIcon }[] = [
  { id: "files", label: "إدارة الملفات", Icon: FolderOpen },
  { id: "stale", label: "مستندات تحتاج مراجعة", Icon: AlertTriangle },
  { id: "dynamic", label: "البيانات الحية", Icon: Radio },
  { id: "dashboard", label: "لوحة المؤشرات", Icon: BarChart3 },
  { id: "history", label: "سجل المحادثات", Icon: MessageSquare },
  { id: "faqs", label: "الأسئلة الشائعة", Icon: HelpCircle },
  { id: "unanswered", label: "الأسئلة غير المجابة", Icon: Puzzle },
  { id: "overrides", label: "الإجابات المخصصة", Icon: Settings },
  { id: "settings", label: "إعدادات الذكاء الاصطناعي", Icon: Bot },
  { id: "llm", label: "إعدادات النموذج", Icon: Brain },
];

type TabId =
  | "files"
  | "stale"
  | "dynamic"
  | "dashboard"
  | "history"
  | "faqs"
  | "unanswered"
  | "overrides"
  | "settings"
  | "llm";

export default function DashboardLayout() {
  const { user, logout } = useAuth();
  const [activeTab, setActiveTab] = useState<TabId>("files");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const renderTab = () => {
    switch (activeTab) {
      case "files":
        return <FileManager />;
      case "stale":
        return <StaleDocuments />;
      case "dynamic":
        return <DynamicSourcesManager />;
      case "dashboard":
        return <KPIDashboard />;
      case "history":
        return <ChatHistory />;
      case "faqs":
        return <FAQManager />;
      case "unanswered":
        return <UnansweredQueries />;
      case "overrides":
        return <OverrideManager />;
      case "settings":
        return <AISettings />;
      case "llm":
        return <LLMSettings />;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-row">
      {/* Sidebar */}
      <aside
        className={`
          fixed inset-y-0 right-0 z-30 w-64 bg-white shadow-lg border-l border-gray-200
          transform transition-transform duration-200
          ${sidebarOpen ? "translate-x-0" : "translate-x-full"}
          lg:sticky lg:top-0 lg:translate-x-0 lg:flex lg:flex-col lg:w-64 lg:h-screen lg:right-auto lg:border-l-0 lg:border-r lg:border-gray-200
        `}
      >
        {/* Logo / Header */}
        <div className="p-5 border-b border-gray-100 bg-primary">
          <h2 className="text-white font-bold text-lg leading-tight">
            لوحة الإدارة
          </h2>
          <p className="text-green-200 text-xs mt-0.5">
            جامعة الخليل — شات بوت
          </p>
        </div>

        {/* User info */}
        <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
          <p className="text-sm text-gray-600">مرحباً،</p>
          <p className="font-semibold text-gray-800 truncate">
            {user?.username}
          </p>
          <span className="badge-success mt-1">{user?.role}</span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-3">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id);
                setSidebarOpen(false);
              }}
              className={`
                w-full flex items-center gap-3 px-4 py-3 text-right text-sm font-medium
                transition-colors hover:bg-green-50
                ${
                  activeTab === tab.id
                    ? "bg-green-50 text-primary border-r-4 border-primary"
                    : "text-gray-700"
                }
              `}
            >
              <tab.Icon className="w-4 h-4 shrink-0" aria-hidden="true" />
              <span>{tab.label}</span>
            </button>
          ))}
        </nav>

        {/* Logout */}
        <div className="p-4 border-t border-gray-100">
          <button
            onClick={logout}
            className="w-full btn-secondary flex items-center justify-center gap-2"
          >
            <span>تسجيل الخروج</span>
            <LogOut className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
      </aside>

      {/* Overlay for mobile */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="bg-white border-b border-gray-200 px-4 lg:px-6 py-3 flex items-center justify-between">
          <button
            className="lg:hidden p-2 rounded-lg hover:bg-gray-100"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="w-5 h-5" aria-hidden="true" />
          </button>
          {(() => {
            const tab = TABS.find((t) => t.id === activeTab);
            if (!tab) return null;
            const { Icon, label } = tab;
            return (
              <h1 className="font-bold text-gray-800 text-lg flex items-center gap-2">
                <Icon className="w-5 h-5 shrink-0" aria-hidden="true" />
                {label}
              </h1>
            );
          })()}
          <div className="hidden lg:block text-sm text-gray-500">
            شات بوت جامعة الخليل
          </div>
        </header>

        {/* Tab content */}
        <main className="flex-1 p-4 lg:p-6 overflow-y-auto">{renderTab()}</main>
      </div>
    </div>
  );
}
