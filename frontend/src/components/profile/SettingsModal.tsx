import { Moon, Sun, Info, Sparkles } from "lucide-react";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "../ui/dialog";
import { useChatStore } from "../../store/chatStore";
import { useAuthStore } from "../../store/authStore";

interface SettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SettingsModal({ open, onOpenChange }: SettingsModalProps) {
  const theme = useChatStore((state) => state.theme);
  const toggleTheme = useChatStore((state) => state.toggleTheme);

  const user = useAuthStore((state) => state.user);
  const anonSessions = useAuthStore((state) => state.anonSessionsRemaining);
  const anonMessages = useAuthStore((state) => state.anonMessagesRemainingPerSession);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogTitle className="text-lg font-semibold">设置</DialogTitle>
        <DialogDescription className="mt-1 text-sm text-neutral-500">外观、账号权益等偏好设置</DialogDescription>

        <div className="mt-5 space-y-5">
          {/* 主题切换 */}
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-neutral-700 dark:text-neutral-300">
              {theme === "dark" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
              外观主题
            </div>
            <div className="grid grid-cols-2 gap-2">
              {(["light", "dark"] as const).map((t) => (
                <button
                  key={t}
                  onClick={toggleTheme}
                  className={`flex items-center justify-center gap-2 rounded-lg border p-3 text-sm transition-colors ${
                    theme === t
                      ? "border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-400 dark:bg-blue-900/20 dark:text-blue-300"
                      : "border-neutral-200 text-neutral-600 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-400 dark:hover:bg-neutral-800"
                  }`}
                >
                  {t === "light" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
                  {t === "light" ? "浅色" : "深色"}
                </button>
              ))}
            </div>
          </div>

          {/* 权益说明 */}
          <div className="rounded-xl border border-neutral-200 bg-neutral-50/60 p-4 dark:border-neutral-700 dark:bg-neutral-800/40">
            <div className="flex items-center gap-2 text-sm font-medium text-neutral-700 dark:text-neutral-300">
              <Sparkles className="h-4 w-4 text-amber-500" />
              使用权益
            </div>
            {user ? (
              <div className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
                你已登录，可创建 <span className="font-medium text-neutral-900 dark:text-neutral-100">无限会话</span>，
                单会话 <span className="font-medium text-neutral-900 dark:text-neutral-100">无限轮对话</span>。
              </div>
            ) : (
              <div className="mt-2 space-y-1.5 text-sm text-neutral-600 dark:text-neutral-400">
                <div className="flex justify-between">
                  <span>剩余会话数</span>
                  <span className="font-medium text-neutral-900 dark:text-neutral-100">{anonSessions}</span>
                </div>
                <div className="flex justify-between">
                  <span>单会话限额</span>
                  <span className="font-medium text-neutral-900 dark:text-neutral-100">{anonMessages} 轮</span>
                </div>
                <p className="mt-1 text-xs text-neutral-400">
                  登录后即可解锁全部功能，无需再受会话/轮数限制。
                </p>
              </div>
            )}
          </div>

          {/* 版本 */}
          <div className="rounded-xl border border-neutral-200 bg-neutral-50/60 p-4 dark:border-neutral-700 dark:bg-neutral-800/40">
            <div className="flex items-center gap-2 text-sm font-medium text-neutral-700 dark:text-neutral-300">
              <Info className="h-4 w-4" />
              关于
            </div>
            <div className="mt-2 space-y-1 text-xs text-neutral-500">
              <div className="flex justify-between"><span>产品</span><span>数据分析 Agent</span></div>
              <div className="flex justify-between"><span>版本</span><span>0.1.0</span></div>
              <div className="flex justify-between"><span>模型</span><span>deepseek-chat</span></div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
